import sqlite3
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTabWidget, QPushButton, QStackedWidget
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

from app.config import TEAM_COLORS
from app.team_assets import team_logo_icon
from app.transitions import FadeStackTransition, fade_widget_in
from app.views.team_manage import FirstTeamTab, SecondTeamTab
from app.views.team_manage.player_profile import PlayerProfilePage
from database import PLAYERS_DB_PATH


class MyTeamManager(QWidget):
    def __init__(self, team_name="NC 다이노스", parent_window=None, display_name=None, db_path=None):  # 💡 parent_window(main.py) 인자 추가
        super().__init__()
        self.team_key = team_name
        self.selected_team = display_name or team_name
        self.parent_window = parent_window  # 뒤로가기(페이지 전환)를 제어하기 위한 부모 객체 저장
        self.colors = TEAM_COLORS.get(team_name, TEAM_COLORS["NC 다이노스"])
        self.db_path = db_path or PLAYERS_DB_PATH
        self.reserve_team_label = (
            "C팀(퓨처스)"
            if self.team_key == "NC 다이노스"
            else "퓨처스팀(2군)"
        )
        
        self.players = []
        self.load_players_from_db()

        # 구단의 트레이드 컬러 세트를 CSS(QSS) 스타일에 동적으로 바인딩
        c = self.colors
        self.setStyleSheet(f"""
            QWidget {{ background-color: {c['bg_dark']}; }}
            QLabel {{ color: {c['text']}; font-family: 'Malgun Gothic', 'Segoe UI'; }}
            QTabWidget::pane {{
                border: 1px solid {c['card_bg']};
                background-color: {c['bg_dark']};
                top: -1px;
            }}
            QTabBar::tab {{
                background-color: {c['card_bg']};
                color: #9ca3af;
                padding: 8px 18px;
                font-size: 14px;
                font-weight: 600;
                border: 1px solid {c['card_bg']};
                border-bottom: none;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                margin-right: 4px;
                font-family: 'Malgun Gothic', 'Segoe UI';
            }}
            QTabBar::tab:selected {{
                background-color: {c['tab_selected']};
                color: {c['accent']};
                border-bottom: 2px solid {c['accent']};
            }}
            QTabBar::tab:hover:not(:selected) {{
                background-color: {c['tab_selected']};
                color: {c['text']};
            }}
            
            /* 💡 뒤로가기 버튼 전용 스타일 */
            QPushButton#btn_back {{
                background-color: {c['card_bg']};
                color: {c['text']};
                border: 1px solid {c['accent']};
                border-radius: 3px;
                padding: 7px 13px;
                font-family: 'Malgun Gothic', 'Segoe UI';
                font-size: 13px;
                font-weight: 600;
            }}
            QPushButton#btn_back:hover {{
                background-color: {c['accent']};
                color: white;
            }}
        """)

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        self.page_stack = QStackedWidget()
        self.page_transition = FadeStackTransition(self.page_stack, self)
        root_layout.addWidget(self.page_stack)

        self.roster_page = QWidget()
        main_layout = QVBoxLayout(self.roster_page)
        main_layout.setContentsMargins(12, 9, 12, 12)
        main_layout.setSpacing(7)

        # ----------------------------------------------------
        # 💡 상단 헤더 영역 (타이틀 + 우측 뒤로가기 버튼 가로 배치)
        # ----------------------------------------------------
        header_layout = QHBoxLayout()
        
        # 선택한 구단에 맞는 타이틀
        title = QLabel(f"🏟️ {self.selected_team} 구단 관리실")
        title.setFont(QFont("Malgun Gothic", 17, QFont.Bold))
        title.setStyleSheet(f"color: {c['accent_light']};")
        header_layout.addWidget(title)
        
        header_layout.addStretch() # 중간 여백 확보
        
        # 🏠 뒤로가기 (대시보드로 가기) 버튼 추가
        self.btn_back = QPushButton("🏠 대시보드로 돌아가기")
        self.btn_back.setObjectName("btn_back")
        self.btn_back.setCursor(Qt.PointingHandCursor)
        self.btn_back.clicked.connect(self.go_to_dashboard)
        header_layout.addWidget(self.btn_back)
        
        main_layout.addLayout(header_layout)

        self.roster_summary = QLabel()
        self.roster_summary.setStyleSheet(
            "color: #9fb0bf; background: rgba(17, 25, 34, 180); "
            "border: 1px solid #31404d; border-radius: 2px; "
            "padding: 6px 10px; font-size: 13px; font-weight: 650;"
        )
        main_layout.addWidget(self.roster_summary)

        self.tabs = QTabWidget()
        
        self.tab1 = FirstTeamTab(self)
        self.tab2 = SecondTeamTab(self)
        
        # 구단 성격에 어울리는 대표 아이콘 분기 설정
        self.tabs.addTab(self.tab1, team_logo_icon(self.team_key), "1군 엔트리")
        self.tabs.addTab(
            self.tab2, f"육성 · {self.reserve_team_label}"
        )
        self.tabs.currentChanged.connect(self.on_tab_changed)
        
        main_layout.addWidget(self.tabs)

        self.profile_page = PlayerProfilePage(self.colors)
        self.profile_page.back_requested.connect(self.show_roster_page)
        self.page_stack.addWidget(self.roster_page)
        self.page_stack.addWidget(self.profile_page)
        self.refresh_all()

    # 💡 클릭 시 메인 윈도우의 switch_page를 실행해 대시보드(0번 스택)로 탈출하는 함수
    def go_to_dashboard(self):
        if self.parent_window:
            self.parent_window.switch_page(0) # 0번 페이지(리그 대시보드)로 강제 이동

    def show_player_profile(self, player):
        """팝업을 열지 않고 구단 관리 화면 전체를 선수 상세 페이지로 바꾼다."""
        self.profile_page.set_player(player)
        self.page_transition.to_widget(self.profile_page)

    def show_roster_page(self):
        self.page_transition.to_widget(self.roster_page)

    # 데이터베이스로부터 선수단 실시간 로드
    def load_players_from_db(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM players WHERE team = ? ORDER BY status DESC, pos, name",
            (self.team_key,),
        )
        rows = cursor.fetchall()
        
        self.players = [dict(row) for row in rows]
        conn.close()
        if self.parent_window and self.parent_window.save_id is not None:
            states = self.parent_window.save_database.get_player_simulation_states(
                self.parent_window.save_id, self.team_key
            )
            assignments = self.parent_window.save_database.get_latest_team_assignments(
                self.parent_window.save_id, self.team_key, 1
            )
            for player in self.players:
                player.update({f"sim_{key}": value for key, value in states.get(player["id"], {}).items()})
                player["simulation_assignment"] = assignments.get(player["id"], "")

    # 승격, 강등, 라인업 등의 상태 변화 발생 시 DB 업데이트
    def update_player_status_in_db(self, player_id, status, lineup_pos=0):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE players 
            SET status = ?, lineup_pos = ? 
            WHERE id = ? AND team = ?
        """, (status, lineup_pos, player_id, self.team_key))
        conn.commit()
        conn.close()
        if self.parent_window and self.parent_window.save_id is not None:
            self.parent_window.save_database.update_player_squad_group(
                self.parent_window.save_id, player_id, "1군" if status else "2군"
            )
        
        self.load_players_from_db()

    def save_lineup_to_db(self, assignments):
        """감독이 확정한 타순을 감독별 선수 DB에 영구 저장한다."""
        with sqlite3.connect(self.db_path) as connection:
            connection.execute(
                "UPDATE players SET lineup_pos=0 WHERE team=? AND status=1",
                (self.team_key,),
            )
            for player_id, assignment in assignments.items():
                connection.execute(
                    "UPDATE players SET lineup_pos=? WHERE id=? AND team=? AND status=1",
                    (assignment["order"], player_id, self.team_key),
                )
        if self.parent_window and self.parent_window.save_id is not None:
            self.parent_window.save_database.save_user_lineup(
                self.parent_window.save_id,
                self.parent_window.current_date.isoformat(),
                self.team_key,
                assignments,
            )
        self.load_players_from_db()

    def apply_tactic_to_db(self, batting, pitching):
        """선택한 전술을 현재 1군 타순과 투수 보직에 적용한다."""
        with sqlite3.connect(self.db_path) as connection:
            connection.execute(
                "UPDATE players SET lineup_pos=0 WHERE team=? AND status=1",
                (self.team_key,),
            )
            connection.execute(
                """
                UPDATE players SET role=''
                WHERE team=? AND status=1
                  AND (pos='P' OR position_group='P')
                """,
                (self.team_key,),
            )
            for item in batting:
                connection.execute(
                    """
                    UPDATE players SET lineup_pos=?
                    WHERE id=? AND team=? AND status=1
                    """,
                    (item["order"], item["player_id"], self.team_key),
                )
            for item in pitching:
                connection.execute(
                    """
                    UPDATE players SET role=?
                    WHERE id=? AND team=? AND status=1
                    """,
                    (item["role"], item["player_id"], self.team_key),
                )
        if self.parent_window and self.parent_window.save_id is not None:
            current_date = self.parent_window.current_date
            date_text = (
                current_date.isoformat()
                if hasattr(current_date, "isoformat")
                else str(current_date)
            )
            self.parent_window.save_database.save_user_tactic(
                self.parent_window.save_id,
                date_text,
                self.team_key,
                batting,
                pitching,
            )
        self.load_players_from_db()

    def on_tab_changed(self, index):
        self.refresh_all()
        fade_widget_in(self.tabs.currentWidget())

    def refresh_all(self):
        self.load_players_from_db()
        first_team = [p for p in self.players if int(p.get("status") or 0) == 1]
        reserve_team = [p for p in self.players if int(p.get("status") or 0) == 0]
        first_pitchers = sum(
            p.get("position_group") == "P" or p.get("pos") == "P"
            for p in first_team
        )
        injured = sum(
            int(p.get("sim_injury_days") or 0) > 0 for p in self.players
        )
        self.tabs.setTabText(
            0,
            f"1군 엔트리  {len(first_team)}",
        )
        self.tabs.setTabText(
            1,
            f"🌱 {self.reserve_team_label}  {len(reserve_team)}",
        )
        self.roster_summary.setText(
            "초기 편성 2025.10.31 최종 등록 명단  ·  현재 "
            f"1군 {len(first_team)}명 "
            f"(투수 {first_pitchers} · 야수 {len(first_team) - first_pitchers})  ·  "
            f"{self.reserve_team_label} {len(reserve_team)}명  ·  "
            f"부상 관리 {injured}명"
        )
        self.tab1.refresh()
        self.tab2.refresh()
