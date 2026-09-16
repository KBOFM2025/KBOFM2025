"""긴 일정 제목·다중 일정·월 이동에 대한 실제 Qt 레이아웃 검증."""
import os
import sys
from pathlib import Path
from datetime import date

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "venv/Lib/site-packages")]
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFontDatabase, QFont
from app.views.season_calendar import SeasonCalendarPage
from app.config.teams import TEAM_INFO
from app.styles import GLOBAL_STYLE


class StressCalendar(SeasonCalendarPage):
    def _events_for_day(self, selected):
        if selected == date(2025, 11, 8):
            return tuple(dict(title="FA 승인 선수 명단 및 구단별 계약·보상 조건 상세 검토 " * 8,
                              category="FA · 구단 운영", detail="긴 상세 설명 확인. " * 30,
                              task="선수 명단과 조건을 검토하세요. " * 10) for _ in range(8))
        return super()._events_for_day(selected)


def main():
    app = QApplication([])
    for name in ("malgun.ttf", "malgunbd.ttf"):
        QFontDatabase.addApplicationFont(str(Path("C:/Windows/Fonts") / name))
    app.setFont(QFont("Malgun Gothic", 10))
    app.setStyleSheet(GLOBAL_STYLE)
    page = StressCalendar(TEAM_INFO["KIA 타이거즈"]["colors"], date(2025, 11, 8))
    page.show()
    for width, height in ((1600, 960), (1280, 800), (900, 900)):
        page.resize(width, height)
        app.processEvents()
        app.processEvents()
        assert page.width() == width, (page.width(), width)
        rects = [page.month_grid.itemAtPosition(row, col).widget().geometry()
                 for row in range(6) for col in range(7)]
        assert max(r.width() for r in rects) - min(r.width() for r in rects) <= 1
        assert max(r.height() for r in rects) - min(r.height() for r in rects) <= 1
        assert page.detail_scroll.verticalScrollBar().maximum() > 0
        assert page.detail_scroll.horizontalScrollBar().maximum() == 0
        assert page.grab().save(str(ROOT / "tmp" / f"calendar-layout-{width}.png"))
    page.resize(1280, 800)
    for _ in range(3):
        page.change_month(1)
        app.processEvents()
        assert len(page.day_buttons) in (28, 30, 31)
    page.go_to_game_date()
    app.processEvents()
    target = next(b for b in page.day_buttons if b.day_number == 9)
    target.click()
    assert page.selected_date == date(2025, 11, 9)
    page.close()
    print("Calendar: equal 7×6 cells, overflow, 3 resolutions, month navigation and date selection passed.")


if __name__ == "__main__":
    main()
