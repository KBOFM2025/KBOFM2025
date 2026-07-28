"""화면 전체에서 공유하는 선수 핵심 능력치와 종합 산식."""

HITTER_CORE_RATINGS = (
    "contact", "power", "plate_discipline", "bat_control", "timing",
)
PITCHER_CORE_RATINGS = (
    "pitcher_stuff", "pitcher_command", "pitcher_movement",
    "pitcher_stamina", "pitcher_pitchability",
)


def _legacy_rating(value):
    if value is None:
        return None
    value = int(value)
    return max(1, min(20, round(value / 5))) if value > 20 else value


def core_rating_values(player, is_pitcher=None):
    """타자와 투수를 각각 핵심 5개 능력치로 동일하게 비교한다."""
    if is_pitcher is None:
        is_pitcher = (
            player.get("position_group") == "P" or player.get("pos") == "P"
        )
    columns = PITCHER_CORE_RATINGS if is_pitcher else HITTER_CORE_RATINGS
    detailed = [
        int(player[column]) for column in columns
        if player.get(column) is not None
    ]
    if detailed:
        return detailed
    return [
        rating for rating in (
            _legacy_rating(player.get(column))
            for column in ("con", "pow", "eye", "def")
        )
        if rating is not None
    ]


def overall_rating(player, is_pitcher=None):
    values = core_rating_values(player, is_pitcher)
    return round(sum(values) / len(values), 1) if values else 0
