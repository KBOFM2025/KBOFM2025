"""Historical KBO calibration for the pitch-by-pitch game engine.

The calibration intentionally changes probabilities, never outcomes directly.
Player ability remains meaningful while game-day form, run support, defense and
bullpen variance prevent a high rating from becoming a guaranteed win.
"""

from __future__ import annotations

import json
import math
import random
from functools import lru_cache
from pathlib import Path


CALIBRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "config"
    / "kbo_game_engine_calibration.json"
)

FALLBACK_COMBINED = {
    "runs_per_team_game": 5.0,
    "runs_stddev": 3.5,
    "home_win_pct": 0.515,
    "draw_rate": 0.014,
    "one_run_game_rate": 0.21,
    "shutout_team_game_rate": 0.06,
    "favorite_loss_rate": 0.40,
    "strong_favorite_loss_rate": 0.30,
    "day_form_rating_sd": 1.7,
    "shared_run_environment_sd": 0.10,
}


def _clamp(value, lower, upper):
    return max(lower, min(upper, value))


@lru_cache(maxsize=4)
def load_game_calibration(path=None):
    calibration_path = Path(path) if path else CALIBRATION_PATH
    try:
        with calibration_path.open(encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, ValueError, TypeError):
        return {"combined": dict(FALLBACK_COMBINED), "seasons": {}}
    combined = dict(FALLBACK_COMBINED)
    combined.update(payload.get("combined") or {})
    payload["combined"] = combined
    return payload


def _weighted_team_profile(calibration, team):
    weights = calibration["combined"].get("season_weights") or {
        "2024": 0.4,
        "2025": 0.6,
    }
    values = {
        "runs_for_per_game": 0.0,
        "runs_against_per_game": 0.0,
        "runs_scored_stddev": 0.0,
    }
    used_weight = 0.0
    for season, weight in weights.items():
        profile = (
            calibration.get("seasons", {})
            .get(str(season), {})
            .get("teams", {})
            .get(team)
        )
        if not profile:
            continue
        weight = float(weight)
        used_weight += weight
        for key in values:
            values[key] += float(profile[key]) * weight
    if not used_weight:
        league = calibration["combined"]
        return {
            "runs_for_per_game": float(league["runs_per_team_game"]),
            "runs_against_per_game": float(league["runs_per_team_game"]),
            "runs_scored_stddev": float(league["runs_stddev"]),
        }
    return {key: value / used_weight for key, value in values.items()}


def build_game_environment(save_id, game_id, teams, home_team):
    """Return reproducible latent factors for one game.

    Historical team strength is deliberately shrunk toward league average. It
    informs the baseline without freezing a 2026 roster to its 2024/25 result.
    """
    calibration = load_game_calibration()
    league = calibration["combined"]
    league_runs = float(league["runs_per_team_game"])
    day_sd = float(league["day_form_rating_sd"])
    shared_sd = float(league["shared_run_environment_sd"])
    rng = random.Random(f"kbo-environment:{int(save_id)}:{int(game_id)}")
    shared_run_environment = math.exp(rng.gauss(-(shared_sd ** 2) / 2.0, shared_sd))
    home_edge = _clamp((float(league["home_win_pct"]) - 0.5) * 8.0, -0.35, 0.35)
    team_factors = {}
    for team in teams:
        profile = _weighted_team_profile(calibration, team)
        offense_history = math.log(
            max(0.65, profile["runs_for_per_game"] / league_runs)
        ) * 2.5
        pitching_history = math.log(
            max(0.65, league_runs / profile["runs_against_per_game"])
        ) * 2.5
        team_factors[team] = {
            "historical_offense": _clamp(offense_history, -0.65, 0.65),
            "historical_pitching": _clamp(pitching_history, -0.65, 0.65),
            "offense_form": _clamp(rng.gauss(0.0, day_sd), -3.2, 3.2),
            "defense_form": _clamp(rng.gauss(0.0, day_sd * 0.45), -1.6, 1.6),
            "bullpen_form": _clamp(rng.gauss(0.0, day_sd * 0.75), -2.4, 2.4),
            "home_edge": home_edge if team == home_team else 0.0,
            "historical_runs_stddev": profile["runs_scored_stddev"],
        }
    return {
        "model": "KBO_2024_2025_GAME_DISTRIBUTION_V1",
        "shared_run_environment": round(shared_run_environment, 5),
        "day_form_rating_sd": day_sd,
        "target_runs_per_team_game": league_runs,
        "historical_favorite_loss_rate": float(league["favorite_loss_rate"]),
        "historical_one_run_game_rate": float(league["one_run_game_rate"]),
        "teams": team_factors,
        "pitcher_forms": {},
    }


def pitcher_day_form(environment, save_id, game_id, team, player_id, is_reliever=False):
    key = f"{team}|{int(player_id)}"
    forms = environment.setdefault("pitcher_forms", {})
    if key not in forms:
        sd = float(environment.get("day_form_rating_sd", 1.7))
        rng = random.Random(
            f"kbo-pitcher-form:{int(save_id)}:{int(game_id)}:{team}:{int(player_id)}"
        )
        value = rng.gauss(0.0, sd)
        if is_reliever:
            value += float(environment["teams"][team].get("bullpen_form", 0.0))
        forms[key] = round(_clamp(value, -3.5, 3.5), 4)
    return float(forms[key])


def matchup_adjustments(environment, offense, defense, pitcher_form):
    offense_factors = environment["teams"][offense]
    defense_factors = environment["teams"][defense]
    run_environment_rating = math.log(
        float(environment.get("shared_run_environment", 1.0))
    ) * 4.0
    offense_adjustment = (
        float(offense_factors["historical_offense"])
        + float(offense_factors["offense_form"])
        + float(offense_factors["home_edge"])
        + run_environment_rating
    )
    pitching_adjustment = (
        float(defense_factors["historical_pitching"])
        + float(defense_factors["defense_form"]) * 0.30
        + float(pitcher_form)
    )
    return {
        "offense": _clamp(offense_adjustment, -4.0, 4.0),
        "pitching": _clamp(pitching_adjustment, -4.0, 4.0),
    }
