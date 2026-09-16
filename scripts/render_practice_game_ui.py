"""연습경기 화면을 오프스크린 PNG로 렌더링해 디자인을 점검한다."""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from datetime import date
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
LOCAL_SITE_PACKAGES = PROJECT_ROOT / "venv" / "Lib" / "site-packages"
if LOCAL_SITE_PACKAGES.exists() and str(LOCAL_SITE_PACKAGES) not in sys.path:
    sys.path.insert(0, str(LOCAL_SITE_PACKAGES))

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication

from app.config.teams import TEAM_INFO
from app.services.practice_games import PracticeGameService
from app.views.practice_game import PracticeGameSetupDialog
from app.views.practice_game_match import PracticeGameMatchPage
from database.paths import PLAYERS_DB_PATH
from database.save_database import SaveDatabase


def save_frame(app, page, target):
    app.processEvents()
    image = page.grab()
    if not image.save(str(target), "PNG"):
        raise RuntimeError(f"화면 저장 실패: {target}")


def process_for(milliseconds):
    loop = QEventLoop()
    QTimer.singleShot(milliseconds, loop.quit)
    loop.exec()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "tmp" / "practice-game-ui",
    )
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    for old_frame in args.output.glob("02-intro-*.png"):
        old_frame.unlink()

    app = QApplication.instance() or QApplication([])
    with tempfile.TemporaryDirectory() as temporary:
        saves = SaveDatabase(Path(temporary) / "preview.db")
        save_id = saves.create_save(
            "UI 미리보기", "KIA 타이거즈", current_date="2025-11-01",
            is_debug=True,
        )
        service = PracticeGameService(
            saves.db_path, PLAYERS_DB_PATH, save_id, "KIA 타이거즈"
        )
        setup = PracticeGameSetupDialog(
            TEAM_INFO["KIA 타이거즈"]["colors"], service,
            date(2025, 11, 1), selected_date=date(2026, 2, 28),
        )
        setup.show()
        save_frame(app, setup, args.output / "00-setup.png")
        setup.close()

        game_id = service.schedule_game(
            date(2026, 2, 28), "SSG 랜더스", venue_type="home",
            start_time="13:00", innings=9,
        )
        page = PracticeGameMatchPage(
            TEAM_INFO["KIA 타이거즈"]["colors"], service
        )
        page.resize(1900, 950)
        page.show()
        page.set_game(game_id)
        page._auto_lineup("first")
        save_frame(app, page, args.output / "01-lineup.png")

        page._start_game()
        page.intro_scene_timer.stop()
        page.intro_motion_timer.stop()
        page.intro_scene_index = 0
        page._show_intro_scene()
        page._advance_intro_scene()
        process_for(760)
        if page.intro_scene_index != 1 or page.intro_transitioning:
            raise RuntimeError("인트로 페이드 전환이 완료되지 않았습니다.")
        page.intro_scene_timer.stop()
        for index, scene in enumerate(page.intro_scenes, 1):
            page.intro_scene_index = index - 1
            page._show_intro_scene()
            page.intro_scene_timer.stop()
            kind = str(scene.get("kind") or "scene")
            save_frame(
                app, page, args.output / f"02-intro-{index:02d}-{kind}.png"
            )

        page._begin_live_game()
        save_frame(app, page, args.output / "03-match.png")
        page.close()

    print(args.output.resolve())


if __name__ == "__main__":
    main()
