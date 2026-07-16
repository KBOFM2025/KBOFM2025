"""애플리케이션 전역에서 사용하는 작은 변환·경로 함수."""

import sys
from pathlib import Path

from app.config import MANAGER_ABILITIES, MANAGER_ABILITY_MAX


def resource_path(*parts):
    """개발 실행과 PyInstaller 실행 모두에서 리소스 경로를 반환한다."""
    if getattr(sys, "frozen", False):
        root = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    else:
        root = Path(__file__).resolve().parent.parent
    return root.joinpath(*parts)


def manager_data_from_save(save):
    """저장 레코드를 대시보드에서 사용하는 감독 데이터로 변환한다."""
    return {
        "manager_name": save.get("manager_name", "무명 감독"),
        "manager_age": save.get("manager_age", 45),
        "manager_style": save.get("manager_style", "염경엽"),
        **{
            key: save.get(f"manager_{key}", MANAGER_ABILITY_MAX // 2)
            for key in MANAGER_ABILITIES
        },
    }
