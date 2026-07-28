"""KBO FM의 가벼운 실행 진입점과 시작 로딩 흐름."""

import sys
from time import monotonic


def run():
    """부팅 화면을 먼저 표시한 뒤 게임 데이터와 시작 메뉴를 준비한다."""
    from PySide6.QtCore import QTimer
    from PySide6.QtGui import QFont
    from PySide6.QtWidgets import QApplication, QMessageBox

    from app.constants import APP_TITLE
    from app.crash_reporting import (
        install_crash_reporting,
        mark_clean_shutdown,
        show_previous_crash_report,
    )
    from app.styles import GLOBAL_STYLE, UI_FONT_FAMILY
    from app.views.startup_splash import StartupSplash

    previous_crash = install_crash_reporting()
    app = QApplication(sys.argv)
    app.setApplicationName(APP_TITLE)
    app.setFont(QFont(UI_FONT_FAMILY, 11))
    app.setStyleSheet(GLOBAL_STYLE)

    started_at = monotonic()
    state = {
        "worker": None,
        "start_window": None,
        "save_database": None,
    }
    splash = StartupSplash()
    splash.show_centered()

    def reveal_start_window():
        start_window = state["start_window"]
        if start_window is None:
            return
        start_window.show()
        start_window.raise_()
        start_window.activateWindow()
        if previous_crash:
            show_previous_crash_report(start_window)

    def startup_failed(message):
        print(f"[게임 시작 오류] {message}", flush=True)
        splash.show_error("게임 데이터를 준비하지 못했습니다")
        QMessageBox.critical(
            splash,
            "KBO FM 시작 오류",
            "게임 시작에 필요한 데이터를 준비하지 못했습니다.\n\n"
            f"{message}",
        )
        app.quit()

    def build_start_window():
        splash.set_progress(96, "시작 화면을 구성하고 있습니다")
        try:
            # 큰 화면 모듈은 부팅 창이 표시된 뒤에 불러온다.
            from app.windows import StartWindow

            state["start_window"] = StartWindow(
                save_database=state["save_database"],
                database_ready=True,
            )
        except Exception as error:
            startup_failed(f"{type(error).__name__}: {error}")
            return
        splash.finish(reveal_start_window)

    def startup_completed(save_database):
        state["save_database"] = save_database
        splash.set_progress(92, "게임 인터페이스를 준비하고 있습니다")
        elapsed_ms = int((monotonic() - started_at) * 1000)
        QTimer.singleShot(max(0, 2000 - elapsed_ms), build_start_window)

    def launch_startup_worker():
        try:
            from app.services.startup_worker import StartupWorker

            worker = StartupWorker()
            state["worker"] = worker
            worker.progress.connect(splash.set_progress)
            worker.completed.connect(startup_completed)
            worker.failed.connect(startup_failed)
            worker.finished.connect(worker.deleteLater)
            worker.start()
        except Exception as error:
            startup_failed(f"{type(error).__name__}: {error}")

    # 이벤트 루프가 부팅 화면을 한 번 그린 다음 초기화를 시작한다.
    QTimer.singleShot(0, launch_startup_worker)
    exit_code = app.exec()
    mark_clean_shutdown()
    return exit_code


def __getattr__(name):
    """기존 외부 import 호환성을 유지하되 화면 모듈은 필요할 때만 읽는다."""
    if name in {"MainWindow", "NewGameWizard", "StartWindow"}:
        from app import windows

        return getattr(windows, name)
    raise AttributeError(name)


__all__ = ["MainWindow", "NewGameWizard", "StartWindow", "run"]
