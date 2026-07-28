"""하루 리그 시뮬레이션을 UI 스레드 밖에서 실행한다."""

from PySide6.QtCore import QThread, Signal

from app.services.league_simulation import LeagueSimulationService


class DayAdvanceWorker(QThread):
    completed = Signal(object)
    failed = Signal(str)
    progress = Signal(object)

    def __init__(
        self,
        save_database,
        save_id,
        player_db_path,
        managed_team,
        target_date,
        parent=None,
    ):
        super().__init__(parent)
        self.save_database = save_database
        self.save_id = save_id
        self.player_db_path = player_db_path
        self.managed_team = managed_team
        self.target_date = target_date

    def run(self):
        try:
            service = LeagueSimulationService(
                self.save_database,
                self.save_id,
                self.player_db_path,
                self.managed_team,
                progress_callback=self.progress.emit,
            )
            summary = service.simulate_day(self.target_date)
            self.completed.emit(summary)
        except Exception as error:
            self.failed.emit(str(error))
