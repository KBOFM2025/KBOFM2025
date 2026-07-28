"""FM 스타일 1군 엔트리 관리."""

from PySide6.QtWidgets import QMessageBox

from app.views.team_manage.roster_table import DenseRosterTab


class FirstTeamTab(DenseRosterTab):
    def __init__(self, parent_manager):
        super().__init__(
            parent_manager,
            roster_status=1,
            action_text=(
                f"선택 선수 → {parent_manager.reserve_team_label}"
            ),
            action_color="#7f2f35",
        )
        self.action_button.clicked.connect(self.demote_player)

    def demote_player(self):
        player = self.selected_player()
        if player is None:
            QMessageBox.warning(
                self,
                "알림",
                f"{self.manager.reserve_team_label}으로 이동할 "
                "선수를 선택해 주세요.",
            )
            return
        self.manager.update_player_status_in_db(
            player["id"], status=0, lineup_pos=0
        )
        QMessageBox.information(
            self,
            "완료",
            f"{player['name']} 선수를 "
            f"{self.manager.reserve_team_label}으로 이동했습니다.",
        )
        self.manager.refresh_all()
