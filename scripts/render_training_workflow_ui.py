"""11월 코치·훈련 필수 업무 화면을 오프스크린 PNG로 점검한다."""

from __future__ import annotations

import os
import sys
import tempfile
from datetime import date
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
LOCAL_SITE_PACKAGES = PROJECT_ROOT / "venv" / "Lib" / "site-packages"
if LOCAL_SITE_PACKAGES.exists():
    sys.path.insert(0, str(LOCAL_SITE_PACKAGES))

from PySide6.QtWidgets import QApplication

from app.config.teams import TEAM_INFO
from app.services.manager_events import ManagerEventService
from app.services.training import TrainingService
from app.views.training_center import TrainingCenterPage
from database.paths import PLAYERS_DB_PATH
from database.save_database import SaveDatabase


def save_frame(app, page, target):
    app.processEvents()
    if not page.grab().save(str(target), "PNG"):
        raise RuntimeError(f"화면 저장 실패: {target}")


def main():
    output = PROJECT_ROOT / "tmp" / "training-workflow-ui"
    output.mkdir(parents=True, exist_ok=True)
    for old_frame in output.glob("*.png"):
        old_frame.unlink()
    app = QApplication.instance() or QApplication([])
    with tempfile.TemporaryDirectory() as directory:
        saves = SaveDatabase(Path(directory) / "preview.db")
        save_id = saves.create_save(
            "훈련 UI 미리보기", "KIA 타이거즈", current_date="2025-11-02"
        )
        events = ManagerEventService(saves.db_path, PLAYERS_DB_PATH)
        training = TrainingService(
            saves.db_path, PLAYERS_DB_PATH, save_id, "KIA 타이거즈"
        )
        page = TrainingCenterPage(TEAM_INFO["KIA 타이거즈"]["colors"], training)
        page.resize(1600, 900)
        page.show()

        events.ensure_schedule_date(save_id, "KIA 타이거즈", date(2025, 11, 2))
        staff_event = next(
            event for event in saves.list_manager_events(save_id, 20)
            if event["event_date"] == "2025-11-02"
        )
        page.set_workflow(staff_event)
        save_frame(app, page, output / "01-staff-required.png")

        coaches = [
            coach for coach in training.coaches("hired")
            if coach["team"] == "KIA 타이거즈"
        ]
        for coach, focus in zip(coaches[:3], ("타격", "투수", "수비")):
            training.assign_coach(coach["id"], "team", 0, focus)
        page.refresh()
        save_frame(app, page, output / "02-staff-ready.png")

        events.ensure_schedule_date(save_id, "KIA 타이거즈", date(2025, 11, 4))
        training_event = next(
            event for event in saves.list_manager_events(save_id, 20)
            if event["event_date"] == "2025-11-04"
        )
        page.set_workflow(training_event)
        training.set_team_setting("균형", 3, "보통")
        training.set_weekly_schedule(training.weekly_schedule())
        for player in training.players()[:3]:
            focus = next(value for value in player["focus_options"] if value != "자동")
            training.set_individual_plan(player["id"], focus, 2)
        page.refresh()
        save_frame(app, page, output / "03-training-ready.png")
        page.tabs.setCurrentIndex(1)
        save_frame(app, page, output / "04-individual-training.png")
        page.tabs.setCurrentIndex(2)
        save_frame(app, page, output / "05-training-units.png")
        page.close()
    print(output.resolve())


if __name__ == "__main__":
    main()
