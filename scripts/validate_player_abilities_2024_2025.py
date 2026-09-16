"""2024·2025 통합 능력치의 DB 반영과 값 범위를 검증한다."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FORMULA_VERSION = "kbo-player-abilities-2024-2025-v1"
REPORT = ROOT / "data" / "source" / "kbo_2024_2025_player_ability_report.json"
BASE_DATABASE = ROOT / "data" / "players.db"
SAVES_DATABASE = ROOT / "data" / "kbo_fm_saves.db"
HITTER_CORE = ("contact", "power", "plate_discipline", "bat_control", "timing")
PITCHER_CORE = (
    "pitcher_stuff", "pitcher_command", "pitcher_movement",
    "pitcher_stamina", "pitcher_pitchability",
)


def save_databases():
    if not SAVES_DATABASE.exists():
        return []
    connection = sqlite3.connect(SAVES_DATABASE)
    try:
        rows = connection.execute(
            "SELECT player_db_path FROM game_saves WHERE player_db_path IS NOT NULL"
        ).fetchall()
    finally:
        connection.close()
    return sorted({Path(row[0]) for row in rows if Path(row[0]).exists()})


def validate_database(path):
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    try:
        total = connection.execute("SELECT COUNT(*) FROM players").fetchone()[0]
        if total != 682:
            raise AssertionError(f"{path}: players={total}, expected=682")
        rows = connection.execute("SELECT * FROM players").fetchall()
        for row in rows:
            columns = PITCHER_CORE if row["position_group"] == "P" else HITTER_CORE
            for column in columns:
                value = row[column]
                if value is None or not 1 <= int(value) <= 20:
                    raise AssertionError(
                        f"{path}: {row['kbo_player_id']} {column}={value}"
                    )
            if row["ability_formula_version"] != FORMULA_VERSION:
                raise AssertionError(
                    f"{path}: {row['kbo_player_id']} formula="
                    f"{row['ability_formula_version']}"
                )
            if row["position_group"] == "P" and (
                row["pitcher_formula_version"] != FORMULA_VERSION
            ):
                raise AssertionError(
                    f"{path}: {row['kbo_player_id']} pitcher formula mismatch"
                )
        return total
    finally:
        connection.close()


def main():
    report = json.loads(REPORT.read_text(encoding="utf-8"))
    if report.get("formula_version") != FORMULA_VERSION:
        raise AssertionError("ability report formula mismatch")
    if report.get("players") != 682:
        raise AssertionError("ability report player coverage mismatch")
    correlations = report["ability_to_record_correlations"]
    minimums = {
        "contact_to_average": .70,
        "power_to_iso": .70,
        "discipline_to_walk_rate": .65,
        "stuff_to_strikeout_rate": .65,
        "command_to_inverse_walk_rate": .65,
        "movement_to_inverse_home_run_rate": .60,
        "stamina_to_innings_per_game": .75,
    }
    for key, minimum in minimums.items():
        if float(correlations[key]) < minimum:
            raise AssertionError(
                f"ability correlation {key}={correlations[key]} < {minimum}"
            )

    databases = [BASE_DATABASE, *save_databases()]
    validated = {str(path): validate_database(path) for path in databases}
    print(json.dumps({
        "formula_version": FORMULA_VERSION,
        "validated_databases": validated,
        "correlations": correlations,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
