"""새 게임에서 선택할 수 있는 시즌 시작 기준점."""

from datetime import date

DEFAULT_START_POINT = "camp1_before"

START_POINTS = {
    "camp1_before": {
        "title": "스토브리그 시작",
        "month": 11,
        "day": 1,
        "description": "FA·보류선수·2차 드래프트 준비부터 2026시즌 구성을 시작합니다.",
    },
    "camp1_after": {
        "title": "2차 드래프트 이후",
        "month": 11,
        "day": 27,
        "description": "2차 드래프트 결과를 반영하고 보류선수 및 계약 대상을 정리합니다.",
    },
    "camp2_before": {
        "title": "계약·캠프 준비 단계",
        "month": 12,
        "day": 15,
        "description": "FA·외국인·연봉 협상을 마무리하며 1월 캠프 계획을 준비합니다.",
    },
}


def start_point_title(start_point):
    """저장된 시작 기준점 코드를 사용자 표시명으로 변환한다."""
    return START_POINTS.get(start_point, START_POINTS[DEFAULT_START_POINT])["title"]


def start_point_date(start_point, year=2025):
    """시작 기준점에 대응하는 게임 내 날짜를 반환한다."""
    info = START_POINTS.get(start_point, START_POINTS[DEFAULT_START_POINT])
    return date(year, info["month"], info["day"])
