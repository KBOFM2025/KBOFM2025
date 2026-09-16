"""원본 DB를 건드리지 않고 임시 사본에서 실제 11월 일일 엔진 30회 실행."""
import sys
import json
import shutil
import sqlite3
import tempfile
import io
import argparse
import hashlib
from pathlib import Path
from datetime import date, timedelta
from collections import Counter
from contextlib import closing, redirect_stdout

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "venv/Lib/site-packages")]
from database.save_database import SaveDatabase
from app.services.league_simulation import LeagueSimulationService
from app.services.training import TrainingService
from app.services.player_development import age_on
from app.config.teams import TEAM_INFO


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--all-clubs', action='store_true')
    args = parser.parse_args()
    source_hash = hashlib.sha256((ROOT / 'data/players.db').read_bytes()).hexdigest()
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
        root = Path(directory)
        players_path = root / "players.db"
        shutil.copy2(ROOT / "data/players.db", players_path)
        saves = SaveDatabase(root / "save.db")
        save_id = saves.create_save("성장 검증", "KIA 타이거즈", current_date="2025-11-01")
        coaching_setup = []
        for team in (TEAM_INFO if args.all_clubs else ('KIA 타이거즈',)):
            training = TrainingService(saves.db_path, players_path, save_id, team)
            chief = next(c for c in training.coaches("hired") if c["team"] == training.team and "수석" in c["role"])
            duties = training.recommended_coaching_structure()
            training.save_coaching_structure(duties, chief["id"])
            training.set_management_policy(True, True)
            coaching_setup.append(dict(team=team, head_coach=chief['name'],
                                       duties={str(key): sorted(value) for key, value in duties.items()}))
        with closing(sqlite3.connect(players_path)) as conn:
            conn.row_factory = sqlite3.Row
            before = {r["id"]: dict(r) for r in conn.execute("SELECT * FROM players")}
        engine = LeagueSimulationService(saves, save_id, players_path, "KIA 타이거즈")
        for offset in range(30):
            day = date(2025, 11, 1) + timedelta(days=offset)
            with redirect_stdout(io.StringIO()):
                engine.simulate_day(day)
            print(f"TRAINING AUDIT {offset + 1}/30", flush=True)
        with closing(sqlite3.connect(saves.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            changes = [dict(r) for r in conn.execute("SELECT * FROM player_development_events")]
            partial = conn.execute("SELECT COUNT(DISTINCT player_id) FROM player_attribute_development WHERE progress>0").fetchone()[0]
            completed = conn.execute("SELECT COUNT(*) FROM simulation_runs WHERE status='completed'").fetchone()[0]
            rating_summary = dict(conn.execute('''SELECT COUNT(*) AS recorded_days,
                COUNT(rating) AS evaluated_days, COUNT(DISTINCT player_id) AS players,
                ROUND(AVG(rating),2) AS average, MIN(rating) AS minimum, MAX(rating) AS maximum
                FROM player_training_ratings''').fetchone())
            assert rating_summary['players'] == len(before)
            assert 1 <= rating_summary['minimum'] <= rating_summary['maximum'] <= 10
            assert conn.execute('''SELECT COUNT(*) FROM player_training_ratings
                WHERE participation != '훈련 참여' AND rating IS NOT NULL''').fetchone()[0] == 0
            ratings = [dict(r) for r in conn.execute('SELECT * FROM player_training_ratings')]
            states = {r['player_id']: dict(r) for r in conn.execute('SELECT * FROM player_simulation_states')}
            injuries = [dict(r) for r in conn.execute('SELECT * FROM player_injury_events')]
            assert len(ratings) == len(before) * 30
            assert len({(r['player_id'], r['training_date']) for r in ratings}) == len(ratings)
        buckets = {}
        for row in before.values():
            age = age_on(row, date(2025, 11, 1))
            bucket = "24세 이하" if age <= 24 else "25–29세" if age <= 29 else "30–34세" if age <= 34 else "35세 이상"
            buckets.setdefault(bucket, dict(players=0, improved=set(), declined=set()))["players"] += 1
        for change in changes:
            p = before.get(change["player_id"])
            if not p:
                continue
            age = age_on(p, date(2025, 11, 1))
            bucket = "24세 이하" if age <= 24 else "25–29세" if age <= 29 else "30–34세" if age <= 34 else "35세 이상"
            buckets[bucket]["improved" if change["new_value"] > change["old_value"] else "declined"].add(p["id"])
            change["name"] = p["name"]
            change["team"] = p["team"]
        improved = {c["player_id"] for c in changes if c["new_value"] > c["old_value"]}
        declined = {c["player_id"] for c in changes if c["new_value"] < c["old_value"]}
        club_results = []
        for team in TEAM_INFO:
            ids = {p['id'] for p in before.values() if p['team'] == team}
            daily = [r for r in ratings if r['player_id'] in ids]
            scored = [r['rating'] for r in daily if r['rating'] is not None]
            final = [states[i] for i in ids]
            club_results.append(dict(team=team, players=len(ids), evaluated_days=len(scored),
                average_rating=round(sum(scored)/len(scored), 2) if scored else None,
                rating_min=min(scored) if scored else None, rating_max=max(scored) if scored else None,
                rating_below_6=sum(s < 6 for s in scored), rating_at_least_8=sum(s >= 8 for s in scored),
                participation=dict(Counter(r['participation'] for r in daily)),
                improved=len(ids & improved), declined=len(ids & declined),
                both=len(ids & improved & declined), unchanged=len(ids - improved - declined),
                condition_end=round(sum(s['condition'] for s in final)/len(final), 1),
                fatigue_end=round(sum(s['fatigue'] for s in final)/len(final), 1),
                high_fatigue_end=sum(s['fatigue'] >= 50 for s in final),
                injury_events=sum(r['player_id'] in ids for r in injuries),
                injured_end=sum(s['injury_days'] > 0 for s in final)))
        player_results = []
        for identifier, player in before.items():
            personal = [r for r in ratings if r['player_id'] == identifier and r['rating'] is not None]
            player_results.append(dict(id=identifier, name=player['name'], team=player['team'],
                age=age_on(player, date(2025,11,1)), evaluated_days=len(personal),
                average_rating=round(sum(r['rating'] for r in personal)/len(personal),2) if personal else None,
                improved=identifier in improved, declined=identifier in declined,
                condition_end=states[identifier]['condition'], fatigue_end=states[identifier]['fatigue']))
        report = dict(completed_days=completed, initial_players=len(before), improved_players=len(improved),
                      training_ratings=rating_summary,
                      declined_players=len(declined), unchanged_players=len(set(before) - improved - declined),
                      players_with_fractional_progress=partial,
                      age_groups={k: {f: len(v) if isinstance(v, set) else v for f, v in group.items()} for k, group in buckets.items()},
                      changes=changes,
                      clubs=club_results, players=player_results, coaching_setup=coaching_setup,
                      scope=("실제 일일 엔진 30일. 10구단 코치 배정·팀/개인 위임." if args.all_clubs else "실제 일일 엔진 30일. KIA 팀·개인 위임, 타 구단 기본 훈련.") + " 필수 의사결정 업무를 해결하는 플레이스루는 아님.")
        assert completed == 30
        assert len(improved) < len(before)
        report['source_db_unchanged'] = hashlib.sha256((ROOT / 'data/players.db').read_bytes()).hexdigest() == source_hash
        assert report['source_db_unchanged']
        output = ROOT / ('tmp/training-month-all-clubs-report.json' if args.all_clubs else 'tmp/training-month-report.json')
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({k: v for k, v in report.items() if k not in ('changes','players','coaching_setup')}, ensure_ascii=True, indent=2))
        print(f"REPORT: {output}")


if __name__ == "__main__":
    main()
