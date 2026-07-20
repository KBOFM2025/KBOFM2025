import sqlite3
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTabWidget, QPushButton, QStackedWidget
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

from app.config import TEAM_COLORS, TEAM_EMOJIS
from app.transitions import FadeStackTransition, fade_widget_in
from app.views.team_manage import FirstTeamTab, SecondTeamTab, SetLineupTab
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
        
        self.players = []
        self.load_players_from_db()

        # 구단의 트레이드 컬러 세트를 CSS(QSS) 스타일에 동적으로 바인딩
        c = self.colors
        self.setStyleSheet(f"""
            QWidget {{ background-color: {c['bg_dark']}; }}
            QLabel {{ color: {c['text']}; font-family: 'Noto Sans KR', 'Malgun Gothic'; }}
            QTabWidget::pane {{
                border: 1px solid {c['card_bg']};
                background-color: {c['bg_dark']};
                top: -1px;
            }}
            QTabBar::tab {{
                background-color: {c['card_bg']};
                color: #9ca3af;
                padding: 14px 26px;
                font-size: 15px;
                font-weight: 600;
                border: 1px solid {c['card_bg']};
                border-bottom: none;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                margin-right: 4px;
                font-family: 'Noto Sans KR', 'Malgun Gothic';
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
                border-radius: 6px;
                padding: 10px 18px;
                font-family: 'Noto Sans KR', 'Malgun Gothic';
                font-size: 15px;
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
        main_layout.setContentsMargins(30, 26, 30, 30)
        main_layout.setSpacing(18)

        # ----------------------------------------------------
        # 💡 상단 헤더 영역 (타이틀 + 우측 뒤로가기 버튼 가로 배치)
        # ----------------------------------------------------
        header_layout = QHBoxLayout()
        
        # 선택한 구단에 맞는 타이틀
        title = QLabel(f"🏟️ {self.selected_team} 구단 관리실")
        title.setFont(QFont("Noto Sans KR", 23, QFont.Bold))
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
        # ----------------------------------------------------

        self.tabs = QTabWidget()
        
        self.tab1 = FirstTeamTab(self)
        self.tab2 = SecondTeamTab(self)
        self.tab3 = SetLineupTab(self)
        
        # 구단 성격에 어울리는 대표 아이콘 분기 설정
        emoji_main = TEAM_EMOJIS.get(self.team_key, "⚾")
        emoji_sub = "🌱"
        
        self.tabs.addTab(self.tab1, f"{emoji_main} 1군 엔트리")
        self.tabs.addTab(self.tab2, f"{emoji_sub} C팀(2군) 육성")
        self.tabs.addTab(self.tab3, "📋 라인업 & 타순")
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

    def on_tab_changed(self, index):
        self.refresh_all()
        fade_widget_in(self.tabs.currentWidget())

    def refresh_all(self):
        self.load_players_from_db() 
        self.tab1.refresh()
        self.tab2.refresh()
        self.tab3.refresh()
