"""투구 단위 연습경기 엔진을 대량 실행해 분포를 검증한다.

게임 결과 로직은 ``PracticeGameService.advance_live_pitch``를 그대로 사용한다.
대량 검증에서 결과와 무관한 매 투구 SQLite 직렬화만 메모리 저장으로 대체한다.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import tempfile
from collections import defaultdict
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


class InMemoryLivePracticeGameService(PracticeGameService):
    """결과 로직은 유지하고 투구별 DB 입출력만 생략하는 검증 서비스."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._validation_states = {}
        self._validation_contexts = {}

    def load_live_state(self, game_id):
        return self._validation_states.get(int(game_id))

    def _save_live_state(self, game_id, state):
        self._validation_states[int(game_id)] = state

    def _live_context(self, game_id, state):
        game_id = int(game_id)
        if game_id not in self._validation_contexts:
            game = self.game_details(game_id)
            teams = (self.managed_team, game["opponent_team"])
            maps = {
                team: {
                    int(player["id"]): player
                    for player in self.available_players(team)
                }
                for team in teams
            }
            self._validation_contexts[game_id] = (game, maps)
        return self._validation_contexts[game_id]

    def _complete_live_game(self, state, game):
        offense = state["offense_team"]
        if int(state["outs"]) >= 3:
            inning_runs = (
                int(state["scores"][offense]) - int(state["half_start_score"])
            )
            if len(state["line_score"][offense]) < int(state["inning"]):
                state["line_score"][offense].append(inning_runs)
        state["status"] = "completed"


def _correlation(pairs):
    if len(pairs) < 2:
        return 0.0
    left = [float(pair[0]) for pair in pairs]
    right = [float(pair[1]) for pair in pairs]
    if len(set(left)) < 2 or len(set(right)) < 2:
        return 0.0
    return round(statistics.correlation(left, right), 4)


def _offensive_ability(player):
    return (
        float(player.get("contact") or player.get("con") or 10) * 1.35
        + float(player.get("power") or player.get("pow") or 10)
        + float(player.get("plate_discipline") or player.get("eye") or 10) * .7
    ) / 3.05


def _pitching_ability(player):
    return statistics.fmean(
        (
            float(player.get("pitcher_stuff") or 10),
            float(player.get("pitcher_command") or 10),
            float(player.get("pitcher_movement") or 10),
        )
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--games", type=int, default=100)
    parser.add_argument("--max-pitches", type=int, default=2000)
    args = parser.parse_args()
    if args.games < 1:
        raise SystemExit("--games must be positive")

    teams = list(TEAM_INFO)
    scores = []
    hits = []
    differences = []
    starter_pitches = []
    starter_outs = []
    total_pitches = []
    innings_played = []
    walks = []
    home_runs = []
    doubles = []
    strikeouts = []
    plate_appearances = []
    reached_on_errors = []
    team_offense_samples = []
    starter_pitching_samples = []
    batter_totals = defaultdict(
        lambda: {
            "ability": 0.0, "contact": 0.0, "power": 0.0, "eye": 0.0,
            "pa": 0, "ab": 0, "hits": 0, "walks": 0, "doubles": 0,
            "triples": 0, "home_runs": 0,
        }
    )

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temporary:
        database = SaveDatabase(Path(temporary) / "live-validation.db")
        for game_index in range(args.games):
            managed_team = teams[game_index % len(teams)]
            opponent = teams[(game_index // len(teams) + game_index + 1) % len(teams)]
            if opponent == managed_team:
                opponent = teams[(teams.index(opponent) + 1) % len(teams)]
            save_id = database.create_save(
                f"live-calibration-{game_index}", managed_team,
                current_date="2025-11-01", is_debug=True,
            )
            service = InMemoryLivePracticeGameService(
                database.db_path, PLAYERS_DB_PATH, save_id, managed_team
            )
            game_id = service.schedule_game(
                date(2026, 2, 24) + timedelta(days=game_index % 5),
                opponent,
                innings=9,
                pitching_plan="정규 선발 운용",
            )
            hitters, starter = service.suggest_lineup("first")
            service.save_lineup(
                game_id,
                [player["id"] for player in hitters],
                starter["id"],
                [player["defensive_position"] for player in hitters],
            )
            state = service.start_live_game(game_id)
            for _ in range(args.max_pitches):
                if state["status"] == "completed":
                    break
                state = service.advance_live_pitch(game_id)["state"]
            if state["status"] != "completed":
                raise RuntimeError(
                    f"game {game_index + 1} exceeded {args.max_pitches} pitches"
                )

            game_scores = [
                int(state["scores"][managed_team]),
                int(state["scores"][opponent]),
            ]
            scores.extend(game_scores)
            differences.append(abs(game_scores[0] - game_scores[1]))
            innings_played.append(int(state["inning"]))
            total_pitches.append(int(state["pitch_no"]))
            _game, player_maps = service._live_context(game_id, state)
            for team in (managed_team, opponent):
                team_stats = [
                    stat for stat in state["stats"].values()
                    if stat["team"] == team
                ]
                team_hits = sum(int(stat["hits"]) for stat in team_stats)
                team_walks = sum(int(stat["walks"]) for stat in team_stats)
                team_home_runs = sum(int(stat["home_runs"]) for stat in team_stats)
                team_doubles = sum(int(stat["doubles"]) for stat in team_stats)
                team_strikeouts = sum(int(stat["strikeouts"]) for stat in team_stats)
                team_pa = sum(int(stat["plate_appearances"]) for stat in team_stats)
                hits.append(team_hits)
                walks.append(team_walks)
                home_runs.append(team_home_runs)
                doubles.append(team_doubles)
                strikeouts.append(team_strikeouts)
                plate_appearances.append(team_pa)
                reached_on_errors.append(
                    sum(
                        1 for play in state["plays"]
                        if play["offense_team"] == team
                        and play["result_code"] == "ROE"
                    )
                )

                batting_ids = [int(value) for value in state["batting_orders"][team]]
                batting_players = [player_maps[team][value] for value in batting_ids]
                team_offense_samples.append(
                    (
                        statistics.fmean(
                            _offensive_ability(player) for player in batting_players
                        ),
                        int(state["scores"][team]),
                    )
                )
                for player_id in batting_ids:
                    player = player_maps[team][player_id]
                    stat = state["stats"].get(f"{team}|{player_id}", {})
                    key = (team, player_id)
                    total = batter_totals[key]
                    total["ability"] = _offensive_ability(player)
                    total["contact"] = float(
                        player.get("contact") or player.get("con") or 10
                    )
                    total["power"] = float(
                        player.get("power") or player.get("pow") or 10
                    )
                    total["eye"] = float(
                        player.get("plate_discipline") or player.get("eye") or 10
                    )
                    for field in (
                        "plate_appearances", "at_bats", "hits", "walks",
                        "doubles", "triples", "home_runs",
                    ):
                        target = {
                            "plate_appearances": "pa", "at_bats": "ab"
                        }.get(field, field)
                        total[target] += int(stat.get(field, 0))

                starter_id = int(state["starting_pitcher_ids"][team])
                starter_stat = next(
                    stat for stat in team_stats
                    if int(stat["player_id"]) == starter_id
                )
                starter_pitches.append(int(starter_stat["pitches"]))
                starter_outs.append(int(starter_stat["innings_outs"]))
                starter = player_maps[team][starter_id]
                outs = max(1, int(starter_stat["innings_outs"]))
                starter_pitching_samples.append(
                    (
                        _pitching_ability(starter),
                        int(starter_stat["runs_allowed"]) * 27 / outs,
                    )
                )

    historical = load_game_calibration()["combined"]
    batter_records = []
    for total in batter_totals.values():
        if total["pa"] < 20 or total["ab"] < 15:
            continue
        singles = (
            total["hits"] - total["doubles"] - total["triples"]
            - total["home_runs"]
        )
        average = total["hits"] / total["ab"]
        on_base = (total["hits"] + total["walks"]) / total["pa"]
        slugging = (
            singles + total["doubles"] * 2 + total["triples"] * 3
            + total["home_runs"] * 4
        ) / total["ab"]
        batter_records.append(
            {
                **total,
                "average": average,
                "ops": on_base + slugging,
                "isolated_power": slugging - average,
                "walk_rate": total["walks"] / total["pa"],
            }
        )
    ordered_batters = sorted(batter_records, key=lambda row: row["ability"])
    quartile_size = max(1, len(ordered_batters) // 4)
    bottom_batters = ordered_batters[:quartile_size]
    top_batters = ordered_batters[-quartile_size:]

    result = {
        "games": args.games,
        "runs_per_team_game": round(statistics.fmean(scores), 4),
        "historical_runs_per_team_game": historical["runs_per_team_game"],
        "hits_per_team_game": round(statistics.fmean(hits), 4),
        "walks_per_team_game": round(statistics.fmean(walks), 4),
        "home_runs_per_team_game": round(statistics.fmean(home_runs), 4),
        "doubles_per_team_game": round(statistics.fmean(doubles), 4),
        "strikeouts_per_team_game": round(statistics.fmean(strikeouts), 4),
        "plate_appearances_per_team_game": round(
            statistics.fmean(plate_appearances), 4
        ),
        "reached_on_error_per_team_game": round(
            statistics.fmean(reached_on_errors), 4
        ),
        "baserunner_run_conversion": round(
            sum(scores) / max(1, sum(hits) + sum(walks)), 4
        ),
        "runs_stddev": round(statistics.pstdev(scores), 4),
        "one_run_game_rate": round(
            sum(value == 1 for value in differences) / args.games, 4
        ),
        "draw_rate": round(
            sum(value == 0 for value in differences) / args.games, 4
        ),
        "shutout_team_game_rate": round(
            sum(value == 0 for value in scores) / len(scores), 4
        ),
        "starter_pitch_average": round(statistics.fmean(starter_pitches), 2),
        "starter_pitch_min": min(starter_pitches),
        "starter_pitch_max": max(starter_pitches),
        "starter_innings_average": round(
            statistics.fmean(starter_outs) / 3, 2
        ),
        "pitches_per_game": round(statistics.fmean(total_pitches), 2),
        "extra_inning_game_rate": round(
            sum(value > 9 for value in innings_played) / args.games, 4
        ),
        "ability_diagnostics": {
            "qualified_batters": len(batter_records),
            "team_offense_to_runs_correlation": _correlation(
                team_offense_samples
            ),
            "batter_ability_to_ops_correlation": _correlation(
                [(row["ability"], row["ops"]) for row in batter_records]
            ),
            "contact_to_average_correlation": _correlation(
                [(row["contact"], row["average"]) for row in batter_records]
            ),
            "power_to_isolated_power_correlation": _correlation(
                [(row["power"], row["isolated_power"]) for row in batter_records]
            ),
            "eye_to_walk_rate_correlation": _correlation(
                [(row["eye"], row["walk_rate"]) for row in batter_records]
            ),
            "starter_ability_to_ra9_correlation": _correlation(
                starter_pitching_samples
            ),
            "bottom_quartile_batter_ops": round(
                statistics.fmean(row["ops"] for row in bottom_batters), 4
            ) if bottom_batters else None,
            "top_quartile_batter_ops": round(
                statistics.fmean(row["ops"] for row in top_batters), 4
            ) if top_batters else None,
        },
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
