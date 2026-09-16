"""공식 기록 CSV를 선수 ID로 결합. 1군과 퓨처스 성적은 별도 기준으로 비교한다."""
import csv
from functools import lru_cache
from pathlib import Path
import sys


def numeric(value):
    try:
        return float(value or 0)
    except (ValueError, TypeError):
        return 0.


@lru_cache(maxsize=1)
def records():
    root = Path(__file__).resolve().parents[2] / "data/source"
    if not root.exists():
        root = Path(getattr(sys, "_MEIPASS", root)) / "data/source"
    result = {}
    reference = None
    available_years = sorted({int(p.name.split('_')[1]) for p in root.glob('kbo_*_*.csv')
                              if p.name.split('_')[1].isdigit()})
    for season in available_years:
        for level in ("first_team", "futures"):
            for role in ("hitting", "pitching"):
                path = root / f"kbo_{season}_{level}_{role}.csv"
                if not path.exists():
                    continue
                with path.open(encoding="utf-8-sig", newline="") as stream:
                    rows = [row for row in csv.DictReader(stream) if row.get("has_record") == "1"]
                sample_key = "PA" if role == "hitting" else "TBF"
                metrics = ("H", "AB", "TB", "BB", "SO", "HR", sample_key)
                totals = {key: sum(numeric(row.get(key)) for row in rows) for key in metrics}
                if season == 2024 and level == "first_team" and role == "pitching":
                    reference = totals
                for row in rows:
                    identifier = row.get("kbo_player_id")
                    if identifier and numeric(row.get(sample_key)) > 0:
                        result.setdefault((identifier, role), []).append((season, level, row, totals))
    # Lifetime tables supplement, never duplicate the existing season snapshots.
    career = root / 'kbo_potential_career_records.csv'
    if career.exists():
        groups = {}
        with career.open(encoding='utf-8-sig', newline='') as stream:
            for row in csv.DictReader(stream):
                groups.setdefault((int(row['season']), row['level'], row['role']), []).append(row)
        for (season, level, role), rows in groups.items():
            sample_key = 'PA' if role == 'hitting' else 'TBF'
            metrics = ('H', 'AB', 'TB', 'BB', 'SO', 'HR', sample_key)
            totals = {key: sum(numeric(row.get(key)) for row in rows) for key in metrics}
            existing_ids = {identifier for (identifier, existing_role), items in result.items()
                            if existing_role == role and any(item[0] == season and item[1] == level for item in items)}
            for row in rows:
                identifier = row['kbo_player_id']
                if identifier not in existing_ids and numeric(row.get(sample_key)) > 0:
                    result.setdefault((identifier, role), []).append((season, level, row, totals))
    historical = root / "kbo_potential_historical_pitching.csv"
    if historical.exists() and reference:
        with historical.open(encoding="utf-8-sig", newline="") as stream:
            for row in csv.DictReader(stream):
                key = (row["kbo_player_id"], "pitching")
                if not any(item[1] == "first_team" and (item[0] >= 2024 or item[0] == int(row['season'])) for item in result.get(key, [])):
                    result.setdefault(key, []).append((int(row["season"]), "historical", row, reference))
    return result


def evidence_for(player, as_of=None):
    from datetime import date
    day = date.fromisoformat(as_of) if isinstance(as_of, str) else as_of or date(2025, 11, 1)
    pitcher = (player.get("position_group") or player.get("pos")) == "P"
    identifier = str(player.get("kbo_player_id") or "")
    matched = records().get((identifier, "pitching" if pitcher else "hitting"), [])
    summaries = []
    contributions = {}
    first_sample = futures_sample = 0.
    for season, level, row, league in matched:
        # Annual aggregates cannot be used before that season's end.
        if season > day.year or season == day.year and day < date(day.year, 11, 1):
            continue
        sample = numeric(row.get("TBF" if pitcher else "PA"))
        recency = 1.  # Lifetime records are cumulative, not a two-year recency window.
        translation = .35 if level == "futures" else 1.
        if level == "first_team":
            first_sample += sample * recency
        elif level == "futures":
            futures_sample += sample * recency
        # Regression to the same season/level league rate prevents tiny samples dominating.
        def relative(numerator, denominator, scale, reverse=False):
            observed_n, observed_d = numerator(row), numeric(row.get(denominator))
            league_n, league_d = numerator(league), numeric(league.get(denominator))
            if observed_d <= 0 or league_d <= 0:
                return 0.
            baseline = league_n / league_d
            prior = 250 if pitcher else 300
            shrunk = (observed_n + baseline * prior) / (observed_d + prior)
            return max(-1., min(1., (shrunk - baseline) / scale * (-1 if reverse else 1)))
        if pitcher:
            k = relative(lambda r: numeric(r.get("SO")), "TBF", .12)
            walk = relative(lambda r: numeric(r.get("BB")), "TBF", .06, True)
            hr = relative(lambda r: numeric(r.get("HR")), "TBF", .02, True)
            signals = {"pitcher_stuff": k, "pitcher_strikeout": k,
                       "pitcher_command": walk, "pitcher_walk_control": walk,
                       "pitcher_movement": hr * .5 + k * .5,
                       "pitcher_pitchability": (k + walk + hr) / 3}
        else:
            average = relative(lambda r: numeric(r.get("H")), "AB", .07)
            k = relative(lambda r: numeric(r.get("SO")), "PA", .12, True)
            iso = relative(lambda r: numeric(r.get("TB")) - numeric(r.get("H")), "AB", .13)
            walk = relative(lambda r: numeric(r.get("BB")), "PA", .06)
            signals = {"contact": .65 * average + .35 * k, "bat_control": k,
                       "timing": average, "power": iso, "plate_discipline": walk}
        weight = sample * recency
        for key, value in signals.items():
            contributions.setdefault(key, []).append((value * translation, weight))
        summaries.append(dict(season=season, level=level, sample=sample, games=numeric(row.get("G")),
                              innings=numeric(row.get("IP_DECIMAL")),
                              source=row.get("source_url", ""), signals=signals))
    signals = {key: sum(value * weight for value, weight in values) / sum(weight for _, weight in values)
               for key, values in contributions.items()}
    # Confidence here describes the evidence supporting projection, not certainty of talent.
    seasons = len({row["season"] for row in summaries if row["level"] == "first_team"})
    confidence = "높음" if seasons >= 2 and first_sample >= 600 else "보통" if first_sample >= 180 else "낮음"
    return dict(records=summaries, signals=signals, first_team_sample=round(first_sample, 1),
                futures_sample=round(futures_sample, 1), seasons=seasons, confidence=confidence,
                identity="KBO ID" if summaries else "기록 연결 없음")
