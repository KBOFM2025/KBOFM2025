"""게임 시작에 필요한 데이터 준비를 UI 스레드 밖에서 수행한다."""

from PySide6.QtCore import QThread, Signal


class StartupWorker(QThread):
    progress = Signal(int, str)
    completed = Signal(object)
    failed = Signal(str)

    def run(self):
        try:
            from database import SaveDatabase, ensure_player_database

            self.progress.emit(18, "KBO 선수 데이터베이스를 확인하고 있습니다")
            ensure_player_database()
            self.progress.emit(68, "구단과 선수 데이터를 불러왔습니다")
            save_database = SaveDatabase()
            self.progress.emit(88, "세이브 시스템을 준비하고 있습니다")
            self.completed.emit(save_database)
        except Exception as error:
            self.failed.emit(f"{type(error).__name__}: {error}")
