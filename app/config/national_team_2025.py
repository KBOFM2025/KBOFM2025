"""2025 NAVER K-BASEBALL SERIES 대한민국 대표팀 최종 소집 명단."""

from datetime import date
from typing import Mapping


SERIES_ID = "2025-k-baseball-series"
ROSTER_SOURCE_URL = (
    "https://www.koreabaseball.com/MediaNews/Notice/View.aspx?bdSe=11721"
)
CALLUP_SOURCE_URL = (
    "https://www.koreabaseball.com/MediaNews/Notice/View.aspx?bdSe=11747"
)

CALLUP_START = date(2025, 11, 2)
LATE_JOIN_DATE = date(2025, 11, 4)
TOKYO_DEPARTURE_DATE = date(2025, 11, 12)
RELEASE_DATE = date(2025, 11, 17)

# 10월 23일 투수 교체와 11월 1일 야수 부상 교체를 모두 반영한
# 실제 최종 소집 34명. LG·한화 선수는 한국시리즈 종료 뒤 11월 4일 합류했다.
NATIONAL_TEAM_ROSTER_2025 = (
    # 투수 18명
    ("KIA 타이거즈", "성영탁", "P"),
    ("삼성 라이온즈", "원태인", "P"),
    ("삼성 라이온즈", "배찬승", "P"),
    ("삼성 라이온즈", "이호성", "P"),
    ("LG 트윈스", "김영우", "P"),
    ("LG 트윈스", "손주영", "P"),
    ("두산 베어스", "곽빈", "P"),
    ("두산 베어스", "김택연", "P"),
    ("KT 위즈", "박영현", "P"),
    ("KT 위즈", "오원석", "P"),
    ("SSG 랜더스", "조병현", "P"),
    ("SSG 랜더스", "이로운", "P"),
    ("SSG 랜더스", "김건우", "P"),
    ("롯데 자이언츠", "최준용", "P"),
    ("롯데 자이언츠", "이민석", "P"),
    ("한화 이글스", "문동주", "P"),
    ("한화 이글스", "김서현", "P"),
    ("한화 이글스", "정우주", "P"),
    # 포수 3명
    ("LG 트윈스", "박동원", "C"),
    ("SSG 랜더스", "조형우", "C"),
    ("한화 이글스", "최재훈", "C"),
    # 내야수 8명
    ("삼성 라이온즈", "김영웅", "IF"),
    ("LG 트윈스", "문보경", "IF"),
    ("LG 트윈스", "신민재", "IF"),
    ("SSG 랜더스", "박성한", "IF"),
    ("한화 이글스", "노시환", "IF"),
    ("NC 다이노스", "김주원", "IF"),
    ("키움 히어로즈", "송성문", "IF"),
    ("상무", "한동희", "IF"),
    # 외야수 5명(문성주·구자욱 부상 제외, 이재원 대체 합류)
    ("삼성 라이온즈", "김성윤", "OF"),
    ("LG 트윈스", "박해민", "OF"),
    ("KT 위즈", "안현민", "OF"),
    ("한화 이글스", "문현빈", "OF"),
    ("상무", "이재원", "OF"),
)

WITHDRAWN_PLAYERS = (
    ("두산 베어스", "최승용", "부상", "롯데 이민석 대체"),
    ("NC 다이노스", "김영규", "부상", "삼성 이호성 대체"),
    ("LG 트윈스", "문성주", "엉덩이 중둔근 부상", "상무 이재원 대체"),
    ("삼성 라이온즈", "구자욱", "옆구리 부상", "상무 이재원 대체"),
)

NATIONAL_TEAM_PLAYER_NAMES = frozenset(
    name for _team, name, _position_group in NATIONAL_TEAM_ROSTER_2025
)
NATIONAL_TEAM_PLAYER_KEYS = frozenset(
    (team, name) for team, name, _position_group in NATIONAL_TEAM_ROSTER_2025
)


def join_date_for(team):
    return LATE_JOIN_DATE if team in {"LG 트윈스", "한화 이글스"} else CALLUP_START


def roster_for_team(team):
    return tuple(item for item in NATIONAL_TEAM_ROSTER_2025 if item[0] == team)


def is_national_team_player(player, team=None):
    """최종 소집 명단 포함 여부를 반환한다.

    저장 시점의 이적 때문에 현재 소속팀이 바뀌어도 대표 이력이 사라지지 않도록
    선수명은 최종 판정 기준으로 사용하고, team은 동명이인 확인용으로만 받는다.
    """
    if isinstance(player, Mapping):
        name = str(player.get("name") or "").strip()
        team = str(player.get("team") or team or "").strip()
    else:
        name = str(player or "").strip()
        team = str(team or "").strip()
    if not name:
        return False
    if team and (team, name) in NATIONAL_TEAM_PLAYER_KEYS:
        return True
    return name in NATIONAL_TEAM_PLAYER_NAMES
