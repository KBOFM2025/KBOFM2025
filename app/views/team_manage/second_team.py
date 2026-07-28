"""FM 스타일 퓨처스 선수단 관리."""

from PySide6.QtWidgets import QMessageBox

from app.views.team_manage.roster_table import DenseRosterTab


class SecondTeamTab(DenseRosterTab):
    def __init__(self, parent_manager):
        super().__init__(
            parent_manager,
            roster_status=0,
            action_text="선택 선수 → 1군 콜업",
            action_color="#2f5793",
        )
        self.action_button.clicked.connect(self.promote_player)

    def promote_player(self):
        player = self.selected_player()
        if player is None:
            QMessageBox.warning(
                self,
                "알림",
                "1군으로 콜업할 선수를 선택해 주세요.",
            )
            return
        self.manager.update_player_status_in_db(
            player["id"], status=1, lineup_pos=0
        )
        QMessageBox.information(
            self,
            "완료",
            f"{player['name']} 선수가 1군 엔트리에 합류했습니다.",
        )
        self.manager.refresh_all()
