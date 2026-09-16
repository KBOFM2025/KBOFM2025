"""Run a deterministic smoke calibration against 2024/25 KBO distributions."""

from __future__ import annotations

import json
import argparse
import statistics
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config.teams import TEAM_INFO
from app.services.kbo_game_calibration import load_game_calibration
from app.services.practice_games import PracticeGameService
from database.paths import PLAYERS_DB_PATH
from database.save_database import SaveDatabase


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repeats", type=int, default=4)
    args = parser.parse_args()
    calibration_data = load_game_calibration()
    scores = []
    run_differences = []
    favorite_games = 0
    favorite_losses = 0
    strong_favorite_games = 0
    strong_favorite_losses = 0
    with tempfile.TemporaryDirectory() as temporary:
        saves = SaveDatabase(Path(temporary) / "validation.db")
        teams = list(TEAM_INFO)
        for repeat in range(args.repeats):
            for team_index, managed_team in enumerate(teams):
                save_id = saves.create_save(
                    f"calibration-{repeat}-{team_index}",
                    managed_team,
                    current_date="2025-11-01",
                    is_debug=True,
                )
                service = PracticeGameService(
                    saves.db_path, PLAYERS_DB_PATH, save_id, managed_team
                )
                for day_offset in range(5):
                    opponent = teams[
                        (team_index + day_offset + repeat + 1) % len(teams)
                    ]
                    game_id = service.schedule_game(
                        date(2026, 2, 24) + timedelta(days=day_offset),
                        opponent,
                        innings=9,
                    )
                    hitters, starter = service.suggest_lineup("first")
                    opponent_hitters, opponent_starter = service.suggest_lineup(
                        "first", opponent
                    )
                    managed_strength = (
                        statistics.fmean(player["rating"] for player in hitters)
                        + float(starter["rating"]) * 0.65
                    )
                    opponent_strength = (
                        statistics.fmean(
                            player["rating"] for player in opponent_hitters
                        )
                        + float(opponent_starter["rating"]) * 0.65
                    )
                    service.save_lineup(
                        game_id,
                        [player["id"] for player in hitters],
                        starter["id"],
                        [player["defensive_position"] for player in hitters],
                    )
                    result = service.simulate_game(game_id)["result"]
                    managed_score = int(result["managed_score"])
                    opponent_score = int(result["opponent_score"])
                    scores.extend((managed_score, opponent_score))
                    run_differences.append(abs(managed_score - opponent_score))
                    strength_gap = abs(managed_strength - opponent_strength)
                    if strength_gap >= 0.10 and managed_score != opponent_score:
                        favorite_games += 1
                        managed_is_favorite = (
                            managed_strength > opponent_strength
                        )
                        managed_won = managed_score > opponent_score
                        favorite_losses += managed_is_favorite != managed_won
                        if strength_gap >= 0.75:
                            strong_favorite_games += 1
                            strong_favorite_losses += managed_is_favorite != managed_won

    calibration = calibration_data["combined"]
    observed = {
        "games": len(run_differences),
        "runs_per_team_game": round(statistics.fmean(scores), 4),
        "runs_stddev": round(statistics.pstdev(scores), 4),
        "one_run_game_rate": round(
            sum(difference == 1 for difference in run_differences)
            / len(run_differences),
            4,
        ),
        "draw_rate": round(
            sum(difference == 0 for difference in run_differences)
            / len(run_differences),
            4,
        ),
        "shutout_team_game_rate": round(
            sum(score == 0 for score in scores) / len(scores), 4
        ),
        "favorite_games": favorite_games,
        "favorite_loss_rate": round(
            favorite_losses / favorite_games if favorite_games else 0.0,
            4,
        ),
        "strong_favorite_games": strong_favorite_games,
        "strong_favorite_loss_rate": round(
            strong_favorite_losses / strong_favorite_games
            if strong_favorite_games else 0.0,
            4,
        ),
    }
    comparison = {
        key: {
            "historical": calibration[key],
            "simulated": observed[key],
        }
        for key in (
            "runs_per_team_game",
            "runs_stddev",
            "one_run_game_rate",
            "draw_rate",
            "shutout_team_game_rate",
            "favorite_loss_rate",
            "strong_favorite_loss_rate",
        )
    }
    print(json.dumps({"observed": observed, "comparison": comparison}, indent=2))
    tolerances = {
        "runs_per_team_game": 0.50,
        "runs_stddev": 0.60,
        "one_run_game_rate": 0.08,
        "draw_rate": 0.04,
        "shutout_team_game_rate": 0.04,
        "favorite_loss_rate": 0.10,
        "strong_favorite_loss_rate": 0.12,
    }
    failures = [
        key
        for key, tolerance in tolerances.items()
        if abs(observed[key] - float(calibration[key])) > tolerance
    ]
    if failures:
        raise SystemExit(
            "Simulation distribution is outside tolerance: "
            + ", ".join(failures)
        )


if __name__ == "__main__":
    main()
