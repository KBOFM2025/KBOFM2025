"""게임 내부 객체를 로컬 모델에 전달할 작은 컨텍스트로 변환한다."""

import json
from copy import deepcopy

from app.utils import resource_path


_PROFILE_PATH = resource_path("data", "config", "club_governance_profiles.json")


def load_governance_profiles():
    with _PROFILE_PATH.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    return payload["clubs"]


def governance_profile_for(team_name):
    profiles = load_governance_profiles()
    if team_name not in profiles:
        raise KeyError(f"구단 거버넌스 프로필이 없습니다: {team_name}")
    return deepcopy(profiles[team_name])


def build_vision_context(
    team_name,
    club_name,
    manager_data,
    profile,
    evaluation,
    board_confidence,
    gm_relationship,
):
    return {
        "request_type": "club_vision",
        "base_team": team_name,
        "club": club_name,
        "manager": {
            "name": manager_data.get("manager_name", "무명 감독"),
            "style": manager_data.get("manager_style", "미지정"),
        },
        "general_manager": profile["general_manager"],
        "ownership": profile["ownership"],
        "current_relationships": {
            "board_confidence": board_confidence,
            "gm_relationship": gm_relationship,
        },
        "request": evaluation.as_dict(),
    }


def build_board_submission_context(team_name, club_name, manager_data, profile, cards):
    return {
        "request_type": "board_vision_batch_review",
        "base_team": team_name,
        "club": club_name,
        "manager": {
            "name": manager_data.get("manager_name", "무명 감독"),
            "style": manager_data.get("manager_style", "미정"),
        },
        "general_manager": profile["general_manager"],
        "ownership": profile["ownership"],
        "level_guide": {"1": "대폭 완화", "2": "일부 완화", "3": "이사회 원안", "4": "도전 목표", "5": "최고 목표"},
        "submission": [
            {
                "objective_key": card.objective_key,
                "title": card.title,
                "description": card.description,
                "priority": card.base_priority,
                "period": card.base_period,
                "selected_level": card.selected_level,
                "gm_proposed_level": card.gm_proposed_level,
                "changed_by_manager": card.selected_level != card.gm_proposed_level,
            }
            for card in cards
        ],
    }
