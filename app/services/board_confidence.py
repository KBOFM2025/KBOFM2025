"""이사회·단장 관계도의 공통 범위와 합산 규칙."""


INITIAL_BOARD_CONFIDENCE = 75
INITIAL_GM_RELATIONSHIP = 70


def clamp_relationship(value):
    return max(0, min(100, int(round(value))))


def relationship_label(value):
    if value >= 85:
        return "매우 강함"
    if value >= 70:
        return "양호"
    if value >= 55:
        return "보통"
    if value >= 40:
        return "불안"
    return "위기"
