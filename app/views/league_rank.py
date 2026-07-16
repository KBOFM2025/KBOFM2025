import sqlite3
from app.config import TEAM_NAMES
from database.paths import PLAYERS_DB_PATH
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

class LeagueRankTab(QWidget):
    def __init__(self, colors):
        super().__init__()
        self.colors = colors
        
        # 스타일 바인딩
        c = self.colors
        self.setStyleSheet(f"""
            QFrame#card {{ background-color: {c['card_bg']}; border: 1px solid #1e293b; border-radius: 8px; padding: 10px; }}
            QLabel#title {{ color: {c['accent_light']}; font-size: 16px; font-weight: bold; margin-bottom: 5px; }}
            QTableWidget {{ background-color: transparent; border: none; color: {c['text']}; }}
            QHeaderView::section {{ background-color: {c['bg_dark']}; color: #94a3b8; font-weight: bold; border: none; padding: 6px; }}
        """)
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(20)
        
        # 상단 통합 타이틀
        top_title = QLabel("🏆 2026 KBO 정규리그 대시보드")
        top_title.setFont(QFont("Malgun Gothic", 18, QFont.Bold))
        main_layout.addWidget(top_title)
        
        # 중간 영역: 좌측(리그 순위) / 우측(투타 탑5 가로 분할)
        content_layout = QHBoxLayout()
        content_layout.setSpacing(20)
        
        # [1] 좌측: 리그 순위 카드
        rank_frame = QFrame()
        rank_frame.setObjectName("card")
        rank_vbox = QVBoxLayout(rank_frame)
        
        rank_title = QLabel("📊 정규시즌 팀 순위")
        rank_title.setObjectName("title")
        rank_vbox.addWidget(rank_title)
        
        self.table_rank = QTableWidget()
        self.configure_read_only_table(self.table_rank)
        self.table_rank.setColumnCount(4)
        self.table_rank.setHorizontalHeaderLabels(["순위", "구단명", "승패", "승률"])
        self.table_rank.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table_rank.setRowCount(len(TEAM_NAMES))
        
        # 가상 데이터 매칭
        teams_data = [
            (str(rank), team_name, "0승 0패 0무", "0.000")
            for rank, team_name in enumerate(TEAM_NAMES, start=1)
        ]
        for row, (r, name, rec, pct) in enumerate(teams_data):
            self.table_rank.setItem(row, 0, QTableWidgetItem(r))
            self.table_rank.setItem(row, 1, QTableWidgetItem(name))
            self.table_rank.setItem(row, 2, QTableWidgetItem(rec))
            self.table_rank.setItem(row, 3, QTableWidgetItem(pct))
            
        rank_vbox.addWidget(self.table_rank)
        content_layout.addWidget(rank_frame, stretch=4)
        
        # [2] 우측: 선수 랭킹 레이아웃 (투수 탑5 / 타자 탑5 세로 적층)
        player_stats_vbox = QVBoxLayout()
        player_stats_vbox.setSpacing(15)
        
        # 투수 탑랭킹 카드
        p_frame = QFrame()
        p_frame.setObjectName("card")
        p_vbox = QVBoxLayout(p_frame)
        p_lbl = QLabel("🔮 투수 부문 TOP 랭커 (구속/제구 종합)")
        p_lbl.setObjectName("title")
        p_vbox.addWidget(p_lbl)
        
        self.table_pitchers = QTableWidget()
        self.configure_read_only_table(self.table_pitchers)
        self.table_pitchers.setColumnCount(3)
        self.table_pitchers.setHorizontalHeaderLabels(["순위", "이름", "종합 능력치"])
        self.table_pitchers.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        p_vbox.addWidget(self.table_pitchers)
        player_stats_vbox.addWidget(p_frame)
        
        # 타자 탑랭킹 카드
        b_frame = QFrame()
        b_frame.setObjectName("card")
        b_vbox = QVBoxLayout(b_frame)
        b_lbl = QLabel("⚾ 타자 부문 TOP 랭커 (컨택/파워 종합)")
        b_lbl.setObjectName("title")
        b_vbox.addWidget(b_lbl)
        
        self.table_batters = QTableWidget()
        self.configure_read_only_table(self.table_batters)
        self.table_batters.setColumnCount(3)
        self.table_batters.setHorizontalHeaderLabels(["순위", "이름", "종합 능력치"])
        self.table_batters.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        b_vbox.addWidget(self.table_batters)
        player_stats_vbox.addWidget(b_frame)
        
        content_layout.addLayout(player_stats_vbox, stretch=3)
        main_layout.addLayout(content_layout)
        
        # 데이터베이스 연동하여 랭커 로드
        self.load_top_players()

    @staticmethod
    def configure_read_only_table(table):
        """리그 데이터 표는 조회만 가능하고 내용 수정은 허용하지 않는다."""
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.setDragEnabled(False)
        table.setAcceptDrops(False)
        table.setDropIndicatorShown(False)
        table.horizontalHeader().setSectionsMovable(False)
        table.verticalHeader().setVisible(False)
        
    def load_top_players(self):
        # DB에서 선수단 데이터를 정렬하여 상위 5명 로드
        if not PLAYERS_DB_PATH.exists():
            return
            
        conn = sqlite3.connect(PLAYERS_DB_PATH)
        cursor = conn.cursor()
        
        # 투수 Top 5 (con:구속 + pow:제구 합산 기준)
        cursor.execute("SELECT name, team, (con+pow) as total FROM players WHERE pos='P' ORDER BY total DESC LIMIT 5")
        pitchers = cursor.fetchall()
        self.table_pitchers.setRowCount(len(pitchers))
        for i, (name, team, total) in enumerate(pitchers):
            self.table_pitchers.setItem(i, 0, QTableWidgetItem(str(i+1)))
            self.table_pitchers.setItem(i, 1, QTableWidgetItem(f"{name} · {team}"))
            self.table_pitchers.setItem(i, 2, QTableWidgetItem(str(int(total/2))))
            
        # 타자 Top 5 (con:컨택 + pow:파워 합산 기준)
        cursor.execute("SELECT name, team, (con+pow) as total FROM players WHERE pos!='P' ORDER BY total DESC LIMIT 5")
        batters = cursor.fetchall()
        self.table_batters.setRowCount(len(batters))
        for i, (name, team, total) in enumerate(batters):
            self.table_batters.setItem(i, 0, QTableWidgetItem(str(i+1)))
            self.table_batters.setItem(i, 1, QTableWidgetItem(f"{name} · {team}"))
            self.table_batters.setItem(i, 2, QTableWidgetItem(str(int(total/2))))
            
        conn.close()

