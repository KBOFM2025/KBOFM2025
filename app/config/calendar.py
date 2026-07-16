"""새 게임에서 선택할 수 있는 시즌 시작 기준점."""

from datetime import date

DEFAULT_START_POINT = "camp1_before"

START_POINTS = {
    "camp1_before": {
        "title": "CAMP1 시작 전",
        "month": 11,
        "day": 1,
        "description": "1차 스프링캠프 출발 전부터 선수단을 점검하고 훈련 계획을 직접 구성합니다.",
    },
    "camp1_after": {
        "title": "CAMP1 끝난 직후",
        "month": 11,
        "day": 27,
        "description": "1차 캠프의 훈련 결과와 선수 컨디션이 반영된 시점부터 구단 운영을 시작합니다.",
    },
    "camp2_before": {
        "title": "CAMP2 시작 전",
        "month": 12,
        "day": 15,
        "description": "실전 중심의 2차 캠프를 앞두고 라인업과 개막 엔트리 경쟁을 관리합니다.",
    },
}


def start_point_title(start_point):
    """저장된 시작 기준점 코드를 사용자 표시명으로 변환한다."""
    return START_POINTS.get(start_point, START_POINTS[DEFAULT_START_POINT])["title"]


def start_point_date(start_point, year=2025):
    """시작 기준점에 대응하는 게임 내 날짜를 반환한다."""
    info = START_POINTS.get(start_point, START_POINTS[DEFAULT_START_POINT])
    return date(year, info["month"], info["day"])
