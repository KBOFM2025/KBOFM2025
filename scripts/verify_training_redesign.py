"""Render every training section at two window sizes using a disposable save."""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'venv/Lib/site-packages')]
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFontDatabase, QFont
from app.styles import GLOBAL_STYLE
from app.config.teams import TEAM_INFO
from app.services.training import TrainingService
from app.views.training_center import TrainingCenterPage
from database.save_database import SaveDatabase


def main():
    app = QApplication([])
    for font in ('malgun.ttf', 'malgunbd.ttf'):
        QFontDatabase.addApplicationFont('C:/Windows/Fonts/' + font)
    app.setFont(QFont('Malgun Gothic', 10))
    app.setStyleSheet(GLOBAL_STYLE)
    output = ROOT / 'tmp/training-redesign'
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
        saves = SaveDatabase(Path(directory) / 'ui.db')
        identifier = saves.create_save('UI preview', 'KIA 타이거즈', current_date='2025-11-03')
        service = TrainingService(saves.db_path, ROOT / 'data/players.db', identifier, 'KIA 타이거즈')
        page = TrainingCenterPage(TEAM_INFO[service.team]['colors'], service)
        from app.services.training_ratings import record_training_rating
        player = service.players()[0]
        with service._connect() as connection:
            for day in ('2025-10-27', '2025-11-01', '2025-11-02', '2025-11-03'):
                record_training_rating(connection, identifier, player,
                    dict(condition=85, fatigue=10, morale=80), day,
                    dict(training_gain=3, focus='컨택', sessions=3))
        page.refresh()
        assert page.player_table.item(0, 6).text() != '—'
        assert '훈련 평점' in page.individual_rating.text()
        assert page.player_table.item(0, 6).text() in page.individual_rating.text()
        page.show()
        for width, height in ((1600, 960), (1280, 800)):
            page.resize(width, height)
            for index in range(7):
                page.navigation.button(index).click()
                app.processEvents()
                assert page.tabs.currentIndex() == index
                assert page.width() == width, (index, page.width(), width)
                assert page.height() == height, (index, page.height(), height)
                assert page.grab().save(str(output / f'{width}-{index}.png'))
            page.tabs.setCurrentIndex(3)
            for index in (0, 2):
                page.staff_sections.setCurrentIndex(index)
                app.processEvents()
                assert page.grab().save(str(output / f'{width}-staff-{index}.png'))
        page.tabs.setCurrentIndex(1)
        page.player_search.setText('김도영')
        app.processEvents()
        visible = [row for row in range(page.player_table.rowCount()) if not page.player_table.isRowHidden(row)]
        assert visible and all('김도영' in page.player_table.item(row, 0).text() for row in visible)
        page.player_search.clear()
        assert not any(page.player_table.isRowHidden(row) for row in range(page.player_table.rowCount()))
        page.unit_filter.setCurrentIndex(1)
        selected_unit = page.unit_filter.currentText()
        assert all(page.unit_table.item(row, 3).text() == selected_unit
                   for row in range(page.unit_table.rowCount()) if not page.unit_table.isRowHidden(row))
        page.unit_filter.setCurrentIndex(0)
        combo = next(iter(page.schedule_combos.values()))
        combo.setCurrentText('휴식')
        assert combo.property('category') == 'recovery'
        combo.setCurrentText('체력')
        assert combo.property('category') == 'load'
        page.navigation.button(0).click()
        scroll = page.tabs.widget(0)
        scroll.verticalScrollBar().setValue(scroll.verticalScrollBar().maximum())
        app.processEvents()
        assert page.grab().save(str(output / '1280-team-bottom.png'))
        page.close()
    print('All seven sections rendered at 1600 and 1280; navigation/search passed.')


if __name__ == '__main__':
    main()
