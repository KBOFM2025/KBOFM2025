"""선수 DB에 잠재 프로필만 저장. 백업 및 전 선수 범위/현재 능력 보존 검증."""
import sys
import sqlite3
import json
from pathlib import Path
from datetime import datetime
from contextlib import closing
from collections import Counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.services.player_potential import populate_potentials, profile_for, HITTER, PITCHER, PITCHES


def main():
    backup_path = ROOT / "tmp" / f"players-before-potential-{datetime.now():%Y%m%d-%H%M%S}.db"
    with closing(sqlite3.connect(ROOT / "data/players.db")) as connection:
        connection.row_factory = sqlite3.Row
        with closing(sqlite3.connect(backup_path)) as backup:
            connection.backup(backup)
        before = {r["id"]: dict(r) for r in connection.execute("SELECT * FROM players")}
        with connection:
            changed = populate_potentials(connection)
            after = [dict(r) for r in connection.execute("SELECT * FROM players")]
            profiles = []
            changes = []
            for player in after:
                for key, value in before[player["id"]].items():
                    if key != "potential_profile_json":
                        assert player[key] == value, (player["id"], key)
                profile = profile_for(player)
                assert profile["caps"], player["name"]
                assert profile["current_rating"] <= profile["rating"] <= 200
                assert all(player[k] <= v <= 20 for k, v in profile["caps"].items())
                profiles.append(dict(id=player["id"], name=player["name"], team=player["team"], **profile))
                try:
                    old = json.loads(before[player["id"]].get("potential_profile_json") or "{}")
                except (ValueError, TypeError):
                    old = {}
                changes.append(dict(name=player["name"], team=player["team"],
                                    previous=old.get("rating"), revised=profile["rating"],
                                    confidence=profile["confidence"],
                                    records=len(profile.get("evidence", {}).get("records", []))))
        report = dict(players=len(profiles), updated=changed,
                      roles=dict(Counter(p["role"] for p in profiles)),
                      confidence=dict(Counter(p["confidence"] for p in profiles)),
                      potential_bands=dict(Counter("180+" if p["rating"] >= 180 else "160–179" if p["rating"] >= 160 else "140–159" if p["rating"] >= 140 else "140 미만" for p in profiles)),
                      linked_players=sum(bool(p.get("evidence", {}).get("records")) for p in profiles),
                      two_year_first_team=sum(p.get("evidence", {}).get("seasons", 0) == 2 for p in profiles),
                      lifecycle_states=dict(Counter(p.get('lifecycle', {}).get('state', 'legacy') for p in profiles)),
                      missing_season_level_records=sum(len(p.get('lifecycle', {}).get('missing_records', [])) for p in profiles),
                      backup=str(backup_path), changes=changes, profiles=profiles)
        output = ROOT / "tmp/player-potential-audit.json"
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({k: v for k, v in report.items() if k not in ("profiles", "changes")}, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
