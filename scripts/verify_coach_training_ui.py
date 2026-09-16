"""임시 저장에서 코치 배정 UI의 저장·재진입·주간 편성을 확인한다."""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "venv" / "Lib" / "site-packages"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFontDatabase, QFont
from app.config.teams import TEAM_INFO
from app.services.training import TrainingService
from app.views.training_center import TrainingCenterPage
from database.save_database import SaveDatabase


def main():
    app = QApplication([])
    for filename in ("malgun.ttf", "malgunbd.ttf"):
        QFontDatabase.addApplicationFont(str(Path("C:/Windows/Fonts") / filename))
    app.setFont(QFont("Malgun Gothic", 10))
    from app.styles import GLOBAL_STYLE
    app.setStyleSheet(GLOBAL_STYLE)
    with tempfile.TemporaryDirectory() as directory:
        saves = SaveDatabase(Path(directory) / "preview.db")
        save_id = saves.create_save("코치 배정 검증", "KIA 타이거즈", current_date="2025-11-03")
        service = TrainingService(saves.db_path, ROOT / "data" / "players.db", save_id, "KIA 타이거즈")
        assert str(service._game_date()) == "2025-11-03"
        page = TrainingCenterPage(TEAM_INFO[service.team]["colors"], service)
        page.resize(1600, 960)
        page.show()
        page.tabs.setCurrentIndex(4)
        page._recommend_duties()
        assert page.head_coach_combo.count() > 1
        page.head_coach_combo.setCurrentIndex(1)
        page._save_duties()
        assert any(a["assignment_type"] == "responsibility" for a in service.assignments())
        page._head_coach_week()
        assert all(s["updated_at"] for s in service.weekly_schedule())
        page.tabs.setCurrentIndex(4)
        app.processEvents()
        output = ROOT / "tmp" / "training-responsibilities.png"
        assert page.grab().save(str(output), "PNG")
        print(f"UI save/reload/week scheduling passed: {output}")
        page.tabs.setCurrentIndex(5)
        page.management_mode.setCurrentIndex(3)
        page._save_management()
        assert service.management_policy()["delegate_individual"] == 1
        from app.services.training_planner import apply_delegated_training
        players = service.players()
        with service._connect() as connection:
            apply_delegated_training(connection, save_id, players, "2025-11-04")
        page.refresh()
        assert "2025-11-04" in page.management_report.text()
        app.processEvents()
        output = ROOT / "tmp" / "training-management.png"
        assert page.grab().save(str(output), "PNG")
        print(f"Delegation UI passed: {output}")
        from app.views.coach_profile import ATTRIBUTE_GROUPS
        for table, column in ((page.league_staff_table, 2), (page.candidate_table, 0),
                              (page.staff_table, 1), (page.duties_table, 0)):
            assert table.rowCount() > 0
            table.cellClicked.emit(0, column)
            assert page.content_stack.currentWidget() is page.coach_profile
            coach = service.coach(page.coach_profile.coach_id)
            for _group, fields in ATTRIBUTE_GROUPS:
                for key, _label in fields:
                    assert page.coach_profile.rating_labels[key].text() == str(coach[key])
            page.coach_profile.back_requested.emit()
            assert page.content_stack.currentWidget() is page.tabs
        page.staff_table.cellClicked.emit(0, 1)
        for width, height in ((1280, 800), (1920, 1080)):
            page.resize(width, height)
            app.processEvents()
            assert page.width() == width
            assert page.grab().save(str(ROOT / "tmp" / f"coach-profile-{width}.png"), "PNG")
        page.coach_profile.back_requested.emit()
        with service._connect() as connection:
            connection.execute("INSERT INTO player_development_events VALUES (?,?,?,?,?,?,?)",
                               (save_id, players[0]["id"], "2025-11-04", "contact", 10, 11, "UI 검증용 변화 기록"))
        page.refresh()
        page.tabs.setCurrentIndex(6)
        assert page.development_table.rowCount() == 1
        assert page.development_table.item(0, 4).text() == "11"
        app.processEvents()
        assert page.grab().save(str(ROOT / "tmp" / "player-development.png"), "PNG")
        page.tabs.setCurrentIndex(5)
        for width, height in ((1280, 800), (1920, 1080)):
            page.resize(width, height)
            app.processEvents()
            assert page.width() == width, "Layout forces an oversized window"
            assert page.grab().save(str(ROOT / "tmp" / f"training-dashboard-{width}.png"), "PNG")
        page.close()


if __name__ == "__main__":
    main()
