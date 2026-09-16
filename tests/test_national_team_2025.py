from app.config.national_team_2025 import (
    NATIONAL_TEAM_PLAYER_NAMES,
    NATIONAL_TEAM_ROSTER_2025,
    is_national_team_player,
)


def test_final_roster_has_34_unique_players():
    assert len(NATIONAL_TEAM_ROSTER_2025) == 34
    assert len(NATIONAL_TEAM_PLAYER_NAMES) == 34


def test_national_team_marker_uses_final_roster_and_survives_transfer():
    assert is_national_team_player({"team": "NC 다이노스", "name": "김주원"})
    assert is_national_team_player({"team": "다른 구단", "name": "김주원"})
    assert not is_national_team_player({"team": "NC 다이노스", "name": "김영규"})
    assert not is_national_team_player({"team": "삼성 라이온즈", "name": "구자욱"})
