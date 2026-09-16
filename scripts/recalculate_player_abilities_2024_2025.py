"""2024·2025 실제 기록으로 전체 선수 능력치를 재산정한다.

2025 기록은 62%, 2024 기록은 38%로 가중한다. 표본이 작은 선수는
리그 평균과 기존 트래킹/수비 평가로 회귀시키며, 기록이 없는 신인은
드래프트 원자료의 기존 1~20 평가를 포지션별 세부 능력으로 확장한다.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sqlite3
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data" / "source"
BASE_DATABASE = ROOT / "data" / "players.db"
SAVES_DATABASE = ROOT / "data" / "kbo_fm_saves.db"
FORMULA_VERSION = "kbo-player-abilities-2024-2025-v1"
SEASON_WEIGHTS = {2024: 0.38, 2025: 0.62}

HITTER_RATINGS = (
    "contact", "power", "plate_discipline", "bat_control", "timing",
    "bunt", "speed", "baserunning_judgment", "fielding_range", "catching",
    "throwing_power", "throwing_accuracy", "fielding_judgment", "composure",
    "leadership", "aggressiveness",
)
PITCHER_RATINGS = (
    "pitcher_velocity", "pitcher_stuff", "pitcher_command",
    "pitcher_movement", "pitcher_stamina", "pitcher_pitchability",
    "pitcher_strikeout", "pitcher_walk_control", "pitcher_composure",
    "pitch_four_seam", "pitch_sinker", "pitch_cutter", "pitch_changeup",
    "pitch_slider", "pitch_curve", "pitch_splitter", "pitch_sweeper",
    "pitch_knuckleball",
)
PITCH_COLUMNS = PITCHER_RATINGS[9:]


def number(value, default=0.0):
    try:
        if value is None or str(value).strip() in {"", "-", "N/A"}:
            return float(default)
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def integer(value, default=0):
    return int(round(number(value, default)))


def clamp(value, lower=1, upper=20):
    return max(lower, min(upper, int(round(value))))


def legacy_rating(value, default=9):
    value = number(value, default)
    return clamp(value / 5.0 if value > 20 else value)


def mean(values, default=10.0):
    usable = [float(value) for value in values if value is not None]
    return sum(usable) / len(usable) if usable else float(default)


def correlation(pairs):
    pairs = [(float(left), float(right)) for left, right in pairs]
    if len(pairs) < 2:
        return 0.0
    left_mean = mean(left for left, _right in pairs)
    right_mean = mean(right for _left, right in pairs)
    numerator = sum(
        (left - left_mean) * (right - right_mean) for left, right in pairs
    )
    left_variance = sum((left - left_mean) ** 2 for left, _right in pairs)
    right_variance = sum((right - right_mean) ** 2 for _left, right in pairs)
    denominator = math.sqrt(left_variance * right_variance)
    return round(numerator / denominator, 4) if denominator else 0.0


def read_csv(path):
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def by_id(rows):
    return {str(row.get("kbo_player_id") or ""): row for row in rows}


def percentile(values, target, higher_is_better=True):
    values = sorted(float(value) for value in values if math.isfinite(float(value)))
    if not values or not math.isfinite(float(target)):
        return 0.5
    below = sum(value < target for value in values)
    equal = sum(abs(value - target) < 1e-12 for value in values)
    result = (below + equal * 0.5) / len(values)
    return result if higher_is_better else 1.0 - result


def rating_from_percentile(value, reliability, level):
    regressed = 0.5 + (max(0.0, min(1.0, value)) - 0.5) * reliability
    center, spread = (11.0, 16.0) if level == "KBO" else (8.5, 12.0)
    return clamp(center + spread * (regressed - 0.5))


def blend(existing, calculated, calculated_weight):
    if existing is None:
        return clamp(calculated)
    return clamp(float(existing) * (1.0 - calculated_weight) + calculated * calculated_weight)


def deterministic_delta(key, span=2):
    digest = hashlib.sha256(str(key).encode("utf-8")).digest()[0]
    return digest % (span * 2 + 1) - span


def weighted_record(player_id, record_maps, fields, sample_field):
    chosen_level = "NONE"
    if any(number(record_maps[(season, "KBO")].get(player_id, {}).get(sample_field)) > 0
           for season in SEASON_WEIGHTS):
        chosen_level = "KBO"
    elif any(number(record_maps[(season, "FUTURES")].get(player_id, {}).get(sample_field)) > 0
             for season in SEASON_WEIGHTS):
        chosen_level = "FUTURES"
    totals = {field: 0.0 for field in fields}
    raw_sample = 0.0
    seasons = []
    if chosen_level == "NONE":
        return chosen_level, totals, raw_sample, seasons
    for season, weight in SEASON_WEIGHTS.items():
        row = record_maps[(season, chosen_level)].get(player_id)
        if not row or number(row.get(sample_field)) <= 0:
            continue
        seasons.append(season)
        raw_sample += number(row.get(sample_field))
        for field in fields:
            totals[field] += number(row.get(field)) * weight
    return chosen_level, totals, raw_sample, seasons


def hitter_metrics(totals):
    pa = max(1.0, totals["PA"])
    ab = max(1.0, totals["AB"])
    hits = totals["H"]
    walks = totals["BB"]
    strikeouts = totals["SO"]
    home_runs = totals["HR"]
    total_bases = totals["TB"]
    times_on_base = max(1.0, hits + walks + totals["HBP"])
    return {
        "avg": hits / ab,
        "babip": max(0.0, hits - home_runs)
        / max(1.0, ab - strikeouts - home_runs),
        "iso": max(0.0, total_bases - hits) / ab,
        "hr_rate": home_runs / pa,
        "xbh_rate": (totals["2B"] + totals["3B"] + home_runs) / ab,
        "bb_rate": walks / pa,
        "k_rate": strikeouts / pa,
        "bb_k": walks / max(1.0, strikeouts),
        "obp_gap": max(0.0, (hits + walks + totals["HBP"]) / pa - hits / ab),
        "gdp_rate": totals["GDP"] / ab,
        "attempt_rate": (totals["SB"] + totals["CS"]) / times_on_base,
        "sb_success": totals["SB"] / max(1.0, totals["SB"] + totals["CS"]),
    }


def pitcher_metrics(totals):
    tbf = max(1.0, totals["TBF"])
    outs = totals["IP_OUTS"]
    innings = max(1 / 3, outs / 3.0)
    games = max(1.0, totals["G"])
    raw_fip = (
        13 * totals["HR"] + 3 * (totals["BB"] + totals["HBP"])
        - 2 * totals["SO"]
    ) / innings
    return {
        "k_rate": totals["SO"] / tbf,
        "bb_rate": totals["BB"] / tbf,
        "hr_rate": totals["HR"] / tbf,
        "hit_rate": totals["H"] / tbf,
        "whip": (totals["H"] + totals["BB"]) / innings,
        "era": totals["ER"] * 9 / innings,
        "fip_raw": raw_fip,
        "ip_per_game": innings / games,
        "innings": innings,
    }


def prepare_models(players):
    hitter_fields = (
        "PA", "AB", "H", "2B", "3B", "HR", "TB", "BB", "HBP", "SO",
        "GDP", "SB", "CS",
    )
    pitcher_fields = (
        "TBF", "IP_OUTS", "G", "H", "HR", "BB", "HBP", "SO", "ER",
    )
    maps = {}
    for season in SEASON_WEIGHTS:
        maps[(season, "KBO", "H")] = by_id(
            read_csv(SOURCE / f"kbo_{season}_first_team_hitting.csv")
        )
        maps[(season, "FUTURES", "H")] = by_id(
            read_csv(SOURCE / f"kbo_{season}_futures_hitting.csv")
        )
        maps[(season, "KBO", "P")] = by_id(
            read_csv(SOURCE / f"kbo_{season}_first_team_pitching.csv")
        )
        maps[(season, "FUTURES", "P")] = by_id(
            read_csv(SOURCE / f"kbo_{season}_futures_pitching.csv")
        )
    baseline_hitters = by_id(read_csv(SOURCE / "kbo_2025_hitter_abilities.csv"))
    baseline_pitchers = by_id(read_csv(SOURCE / "kbo_2025_pitcher_abilities.csv"))
    hitters, pitchers = [], []
    for database_player in players:
        player = dict(database_player)
        player_id = str(player.get("kbo_player_id") or "")
        if player.get("position_group") == "P":
            baseline = baseline_pitchers.get(player_id, {})
            for column in PITCHER_RATINGS:
                if str(baseline.get(column) or "").strip():
                    player[column] = integer(baseline[column])
            record_maps = {
                (season, level): maps[(season, level, "P")]
                for season in SEASON_WEIGHTS for level in ("KBO", "FUTURES")
            }
            level, totals, sample, seasons = weighted_record(
                player_id, record_maps, pitcher_fields, "TBF"
            )
            pitchers.append({
                "player": player, "level": level, "totals": totals,
                "sample": sample, "seasons": seasons,
                "metrics": pitcher_metrics(totals) if level != "NONE" else {},
            })
        else:
            baseline = baseline_hitters.get(player_id, {})
            for column in HITTER_RATINGS:
                if str(baseline.get(column) or "").strip():
                    player[column] = integer(baseline[column])
            record_maps = {
                (season, level): maps[(season, level, "H")]
                for season in SEASON_WEIGHTS for level in ("KBO", "FUTURES")
            }
            level, totals, sample, seasons = weighted_record(
                player_id, record_maps, hitter_fields, "PA"
            )
            hitters.append({
                "player": player, "level": level, "totals": totals,
                "sample": sample, "seasons": seasons,
                "metrics": hitter_metrics(totals) if level != "NONE" else {},
            })
    return hitters, pitchers


def metric_percentile(model, models, key, higher=True):
    peers = [
        peer["metrics"][key] for peer in models
        if peer["level"] == model["level"] and key in peer["metrics"]
    ]
    return percentile(peers, model["metrics"][key], higher)


def rookie_hitter(player):
    contact = legacy_rating(player.get("con"), 9)
    power = legacy_rating(player.get("pow"), 9)
    eye = legacy_rating(player.get("eye"), 9)
    defense = legacy_rating(player.get("def"), 9)
    speed = clamp(10 + deterministic_delta(player["kbo_player_id"] + ":speed", 3))
    return {
        "contact": contact, "power": power, "plate_discipline": eye,
        "bat_control": clamp((contact * 2 + eye) / 3), "timing": contact,
        "bunt": clamp(7 + deterministic_delta(player["kbo_player_id"] + ":bunt")),
        "speed": speed, "baserunning_judgment": clamp((speed + eye) / 2),
        "fielding_range": defense, "catching": defense if player.get("position_group") == "C" else 5,
        "throwing_power": clamp(defense + deterministic_delta(player["kbo_player_id"] + ":arm")),
        "throwing_accuracy": defense, "fielding_judgment": defense,
        "composure": eye, "leadership": 7, "aggressiveness": clamp((power + speed) / 2),
    }


def rookie_pitcher(player):
    stuff = legacy_rating(player.get("con"), 9)
    command = legacy_rating(player.get("eye"), 9)
    movement = legacy_rating(player.get("def"), 9)
    stamina = legacy_rating(player.get("pow"), 9)
    result = {
        "pitcher_velocity": clamp(stuff + deterministic_delta(player["kbo_player_id"] + ":velo")),
        "pitcher_stuff": stuff, "pitcher_command": command,
        "pitcher_movement": movement, "pitcher_stamina": stamina,
        "pitcher_pitchability": clamp(mean((stuff, command, movement))),
        "pitcher_strikeout": stuff, "pitcher_walk_control": command,
        "pitcher_composure": clamp(mean((command, movement))),
    }
    repertoire = ("pitch_four_seam", "pitch_slider", "pitch_curve")
    for column in PITCH_COLUMNS:
        result[column] = None
    for column in repertoire:
        result[column] = clamp(stuff + deterministic_delta(player["kbo_player_id"] + column))
    return result


def rate_hitters(models):
    results = {}
    for model in models:
        player = model["player"]
        if model["level"] == "NONE":
            ratings = rookie_hitter(player)
        else:
            reliability = model["sample"] / (model["sample"] + 220.0)
            pct = lambda key, higher=True: metric_percentile(model, models, key, higher)
            contact_p = .50 * pct("avg") + .30 * pct("k_rate", False) + .20 * pct("babip")
            power_p = .45 * pct("iso") + .30 * pct("hr_rate") + .25 * pct("xbh_rate")
            eye_p = .50 * pct("bb_rate") + .25 * pct("bb_k") + .25 * pct("obp_gap")
            control_p = .45 * pct("k_rate", False) + .35 * pct("avg") + .20 * pct("gdp_rate", False)
            speed_p = .48 * pct("attempt_rate") + .32 * pct("sb_success") + .20 * pct("gdp_rate", False)
            calculated = {
                "contact": rating_from_percentile(contact_p, reliability, model["level"]),
                "power": rating_from_percentile(power_p, reliability, model["level"]),
                "plate_discipline": rating_from_percentile(eye_p, reliability, model["level"]),
                "bat_control": rating_from_percentile(control_p, reliability, model["level"]),
                "timing": rating_from_percentile(.60 * contact_p + .40 * control_p, reliability, model["level"]),
                "speed": rating_from_percentile(speed_p, reliability, model["level"]),
                "baserunning_judgment": rating_from_percentile(.55 * pct("sb_success") + .45 * pct("attempt_rate"), reliability, model["level"]),
            }
            weights = {
                "contact": .68, "power": .68, "plate_discipline": .68,
                "bat_control": .65, "timing": .55, "speed": .52,
                "baserunning_judgment": .55,
            }
            ratings = {}
            for column, calculated_value in calculated.items():
                ratings[column] = blend(player.get(column), calculated_value, weights[column])
            for column in HITTER_RATINGS:
                if column in ratings:
                    continue
                fallback = player.get(column)
                if fallback is None:
                    fallback = (
                        player.get("def") if column.startswith("fielding")
                        or column in {"catching", "throwing_power", "throwing_accuracy"}
                        else 8
                    )
                ratings[column] = clamp(fallback)
        results[str(player["kbo_player_id"])] = {
            **ratings,
            "ability_source_level": (
                f"{model['level']}_2024_2025" if model["level"] != "NONE"
                else "SCOUTING_PRIOR"
            ),
            "ability_formula_version": FORMULA_VERSION,
            "sample": int(round(model["sample"])),
            "seasons": "+".join(map(str, model["seasons"])) or "none",
        }
    return results


def rate_pitchers(models):
    results = {}
    for model in models:
        player = model["player"]
        if model["level"] == "NONE":
            ratings = rookie_pitcher(player)
        else:
            reliability = model["sample"] / (model["sample"] + 280.0)
            pct = lambda key, higher=True: metric_percentile(model, models, key, higher)
            k_p = pct("k_rate")
            bb_p = pct("bb_rate", False)
            hr_p = pct("hr_rate", False)
            hit_p = pct("hit_rate", False)
            whip_p = pct("whip", False)
            era_p = pct("era", False)
            fip_p = pct("fip_raw", False)
            stamina_p = .70 * pct("ip_per_game") + .30 * pct("innings")
            composites = {
                "pitcher_stuff": .50 * k_p + .30 * fip_p + .20 * hit_p,
                "pitcher_command": .55 * bb_p + .25 * whip_p + .20 * fip_p,
                "pitcher_movement": .55 * hr_p + .25 * hit_p + .20 * fip_p,
                "pitcher_stamina": stamina_p,
                "pitcher_pitchability": .28 * k_p + .25 * bb_p + .27 * fip_p + .20 * whip_p,
                "pitcher_strikeout": k_p,
                "pitcher_walk_control": bb_p,
                "pitcher_composure": .42 * era_p + .33 * whip_p + .25 * fip_p,
            }
            ratings = {}
            for column, composite in composites.items():
                calculated = rating_from_percentile(composite, reliability, model["level"])
                ratings[column] = blend(player.get(column), calculated, .64)
            ratings["pitcher_velocity"] = clamp(player.get("pitcher_velocity") or 8)
            for column in PITCH_COLUMNS:
                value = player.get(column)
                ratings[column] = clamp(value) if value is not None else None
        results[str(player["kbo_player_id"])] = {
            **ratings,
            "ability_source_level": (
                f"{model['level']}_2024_2025" if model["level"] != "NONE"
                else "SCOUTING_PRIOR"
            ),
            "ability_formula_version": FORMULA_VERSION,
            "pitcher_source_level": (
                f"{model['level']}_2024_2025" if model["level"] != "NONE"
                else "SCOUTING_PRIOR"
            ),
            "pitcher_formula_version": FORMULA_VERSION,
            "sample": int(round(model["sample"])),
            "seasons": "+".join(map(str, model["seasons"])) or "none",
        }
    return results


def database_players(path):
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    try:
        return [dict(row) for row in connection.execute("SELECT * FROM players")]
    finally:
        connection.close()


def write_outputs(players, hitter_ratings, pitcher_ratings):
    ability_path = SOURCE / "kbo_2024_2025_player_abilities.csv"
    changes_path = SOURCE / "kbo_2024_2025_player_ability_changes.csv"
    all_ratings = {**hitter_ratings, **pitcher_ratings}
    ability_fields = (
        "kbo_player_id", "team", "player_name", "position_group",
        "source_level", "sample", "seasons", *HITTER_RATINGS, *PITCHER_RATINGS,
        "formula_version",
    )
    with ability_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=ability_fields)
        writer.writeheader()
        for player in players:
            rating = all_ratings[str(player["kbo_player_id"])]
            row = {
                "kbo_player_id": player["kbo_player_id"], "team": player["team"],
                "player_name": player["name"],
                "position_group": player["position_group"],
                "source_level": rating["ability_source_level"],
                "sample": rating["sample"], "seasons": rating["seasons"],
                "formula_version": FORMULA_VERSION,
            }
            for column in (*HITTER_RATINGS, *PITCHER_RATINGS):
                row[column] = rating.get(column)
            writer.writerow(row)
    original_values = {}
    if changes_path.exists():
        for row in read_csv(changes_path):
            key = (str(row.get("kbo_player_id") or ""), str(row.get("column") or ""))
            value = row.get("before")
            original_values[key] = None if value in {None, ""} else integer(value)
    with changes_path.open("w", encoding="utf-8-sig", newline="") as handle:
        fields = (
            "kbo_player_id", "team", "player_name", "position_group", "column",
            "before", "after", "delta", "source_level", "formula_version",
        )
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for player in players:
            rating = all_ratings[str(player["kbo_player_id"])]
            columns = PITCHER_RATINGS if player["position_group"] == "P" else HITTER_RATINGS
            for column in columns:
                before = original_values.get(
                    (str(player["kbo_player_id"]), column), player.get(column)
                )
                after = rating.get(column)
                if before == after:
                    continue
                writer.writerow({
                    "kbo_player_id": player["kbo_player_id"], "team": player["team"],
                    "player_name": player["name"],
                    "position_group": player["position_group"], "column": column,
                    "before": before, "after": after,
                    "delta": "" if before is None or after is None else int(after) - int(before),
                    "source_level": rating["ability_source_level"],
                    "formula_version": FORMULA_VERSION,
                })
    return ability_path, changes_path


def update_database(path, hitter_ratings, pitcher_ratings):
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    updated = 0
    try:
        rows = connection.execute(
            "SELECT id,kbo_player_id,position_group FROM players"
        ).fetchall()
        with connection:
            for row in rows:
                ratings = (
                    pitcher_ratings if row["position_group"] == "P" else hitter_ratings
                ).get(str(row["kbo_player_id"]))
                if ratings is None:
                    continue
                columns = list(
                    PITCHER_RATINGS if row["position_group"] == "P" else HITTER_RATINGS
                )
                columns += ["ability_source_level", "ability_formula_version"]
                if row["position_group"] == "P":
                    columns += ["pitcher_source_level", "pitcher_formula_version"]
                values = [ratings.get(column) for column in columns]
                connection.execute(
                    f"UPDATE players SET {','.join(f'{column}=?' for column in columns)} WHERE id=?",
                    (*values, int(row["id"])),
                )
                updated += 1
        return updated
    finally:
        connection.close()


def existing_save_databases():
    if not SAVES_DATABASE.exists():
        return []
    connection = sqlite3.connect(SAVES_DATABASE)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            "SELECT player_db_path FROM game_saves WHERE player_db_path IS NOT NULL"
        ).fetchall()
    finally:
        connection.close()
    paths = []
    for row in rows:
        path = Path(row["player_db_path"])
        if path.exists() and path.resolve() != BASE_DATABASE.resolve():
            paths.append(path)
    return sorted(set(paths))


def summary(players, hitter_models, pitcher_models, hitter_ratings, pitcher_ratings):
    sources = defaultdict(int)
    for ratings in (*hitter_ratings.values(), *pitcher_ratings.values()):
        sources[ratings["ability_source_level"]] += 1
    qualified_hitters = [
        model for model in hitter_models
        if model["level"] == "KBO" and model["sample"] >= 100
    ]
    qualified_pitchers = [
        model for model in pitcher_models
        if model["level"] == "KBO" and model["sample"] >= 100
    ]
    return {
        "formula_version": FORMULA_VERSION,
        "season_weights": SEASON_WEIGHTS,
        "players": len(players),
        "hitters": len(hitter_models),
        "pitchers": len(pitcher_models),
        "sources": dict(sorted(sources.items())),
        "hitter_core_average": round(mean(
            mean(hitter_ratings[str(model["player"]["kbo_player_id"])][column]
                 for column in ("contact", "power", "plate_discipline", "bat_control", "timing"))
            for model in hitter_models
        ), 3),
        "pitcher_core_average": round(mean(
            mean(pitcher_ratings[str(model["player"]["kbo_player_id"])][column]
                 for column in ("pitcher_stuff", "pitcher_command", "pitcher_movement", "pitcher_stamina", "pitcher_pitchability"))
            for model in pitcher_models
        ), 3),
        "ability_to_record_correlations": {
            "qualified_hitters": len(qualified_hitters),
            "contact_to_average": correlation(
                (
                    hitter_ratings[str(model["player"]["kbo_player_id"])]["contact"],
                    model["metrics"]["avg"],
                ) for model in qualified_hitters
            ),
            "power_to_iso": correlation(
                (
                    hitter_ratings[str(model["player"]["kbo_player_id"])]["power"],
                    model["metrics"]["iso"],
                ) for model in qualified_hitters
            ),
            "discipline_to_walk_rate": correlation(
                (
                    hitter_ratings[str(model["player"]["kbo_player_id"])]["plate_discipline"],
                    model["metrics"]["bb_rate"],
                ) for model in qualified_hitters
            ),
            "qualified_pitchers": len(qualified_pitchers),
            "stuff_to_strikeout_rate": correlation(
                (
                    pitcher_ratings[str(model["player"]["kbo_player_id"])]["pitcher_stuff"],
                    model["metrics"]["k_rate"],
                ) for model in qualified_pitchers
            ),
            "command_to_inverse_walk_rate": correlation(
                (
                    pitcher_ratings[str(model["player"]["kbo_player_id"])]["pitcher_command"],
                    -model["metrics"]["bb_rate"],
                ) for model in qualified_pitchers
            ),
            "movement_to_inverse_home_run_rate": correlation(
                (
                    pitcher_ratings[str(model["player"]["kbo_player_id"])]["pitcher_movement"],
                    -model["metrics"]["hr_rate"],
                ) for model in qualified_pitchers
            ),
            "stamina_to_innings_per_game": correlation(
                (
                    pitcher_ratings[str(model["player"]["kbo_player_id"])]["pitcher_stamina"],
                    model["metrics"]["ip_per_game"],
                ) for model in qualified_pitchers
            ),
        },
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--include-saves", action="store_true")
    args = parser.parse_args()

    players = database_players(BASE_DATABASE)
    hitter_models, pitcher_models = prepare_models(players)
    hitter_ratings = rate_hitters(hitter_models)
    pitcher_ratings = rate_pitchers(pitcher_models)
    ability_path, changes_path = write_outputs(
        players, hitter_ratings, pitcher_ratings
    )
    report = summary(
        players, hitter_models, pitcher_models, hitter_ratings, pitcher_ratings
    )
    report.update({
        "ability_csv": str(ability_path.relative_to(ROOT)),
        "change_csv": str(changes_path.relative_to(ROOT)),
        "applied": bool(args.apply),
        "databases": {},
    })

    if args.apply:
        targets = [BASE_DATABASE]
        if args.include_saves:
            targets.extend(existing_save_databases())
        for path in targets:
            report["databases"][str(path)] = update_database(
                path, hitter_ratings, pitcher_ratings
            )

    report_path = SOURCE / "kbo_2024_2025_player_ability_report.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
