"""임시 디버그 저장으로 9이닝 진행과 투구 애니메이션을 점검한다."""
import os
import sys
import tempfile
import shutil
from pathlib import Path
from datetime import date

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "venv/Lib/site-packages")]
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFontDatabase, QFont
from app.config.teams import TEAM_INFO
from app.services.practice_games import PracticeGameService
from app.views.practice_game_match import PracticeGameMatchPage
from database.save_database import SaveDatabase


def main():
    app = QApplication([])
    for filename in ("malgun.ttf", "malgunbd.ttf"):
        QFontDatabase.addApplicationFont(f"C:/Windows/Fonts/{filename}")
    app.setFont(QFont("Malgun Gothic", 10))
    from app.styles import GLOBAL_STYLE
    app.setStyleSheet(GLOBAL_STYLE)
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        shutil.copy2(ROOT / "data/players.db", root / "players.db")
        saves = SaveDatabase(root / "save.db")
        save_id = saves.create_save("구장 애니메이션 검증", "KIA 타이거즈", current_date="2025-11-01", is_debug=True)
        service = PracticeGameService(saves.db_path, root / "players.db", save_id, "KIA 타이거즈")
        game_id = service.schedule_game(date(2026, 2, 28), "SSG 랜더스", venue_type="home", start_time="13:00", innings=9)
        page = PracticeGameMatchPage(TEAM_INFO["KIA 타이거즈"]["colors"], service)
        page.resize(1900, 1000)
        page.show()
        page.set_game(game_id)
        page._auto_lineup("first")
        page._start_game()
        page._begin_live_game()
        app.processEvents()
        output = ROOT / "tmp/live-field"
        output.mkdir(parents=True, exist_ok=True)
        seen = set()
        preview = "--preview" in sys.argv
        for number in range(12 if preview else 1000):
            if page.live_state.get("status") == "completed":
                break
            previous = len(page.live_state["plays"])
            page._show_next_play()
            assert page.field.active
            page._show_next_play()
            assert len(service.load_live_state(game_id)["plays"]) == previous + 1
            event = page._pending_progress["event"]
            assert "bases_after" in event
            code = event["result_code"]
            page.field.progress = .65
            if code not in seen and (code in {"OUT", "1B", "HR", "BB"} or not seen):
                app.processEvents()
                assert page.grab().save(str(output / f"{code}.png"), "PNG")
                seen.add(code)
            page.field.started -= 10
            page.field._tick()
            assert page._pending_progress is None
            assert not page.field.active
        if preview:
            page._show_next_play()
            page.hide()
            assert page._pending_progress is None
            assert not page.field.timer.isActive()
            print("Preview and navigation during animation passed.")
            page.close()
            return
        assert page.live_state["status"] == "completed"
        assert page.live_state["inning"] >= 9
        assert page.result_button.isEnabled()
        print(f"Completed {number} plays through inning {page.live_state['inning']}; rendering, input lock and results OK. Screenshots: {output}")
        page.close()


if __name__ == "__main__":
    main()
