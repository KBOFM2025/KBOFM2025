"""FM 스타일의 구단 종합 정보 대시보드."""

import sqlite3

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QPixmap
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QVBoxLayout, QWidget,
)

from app.config import TEAM_EMOJIS, TEAM_INFO
from app.utils import resource_path
from app.views.team_manage.player_profile import _display_rating, _player_photo_path
from database import PLAYERS_DB_PATH

CLUB_LEGENDS = {
    "KIA 타이거즈": (("선동열", "투수", "해태 왕조를 상징한 국보급 에이스"), ("이종범", "유격수·외야수", "공격·수비·주루를 지배한 바람의 아들"), ("김성한", "내야수", "초창기 타이거즈 왕조의 중심 타자")),
    "삼성 라이온즈": (("이승엽", "1루수", "KBO를 대표하는 홈런왕이자 라이온즈의 상징"), ("양준혁", "외야수", "꾸준한 출루와 장타를 겸비한 타격의 전설"), ("장효조", "외야수", "정교한 타격으로 시대를 지배한 교타자")),
    "LG 트윈스": (("김용수", "투수", "선발과 마무리에서 모두 빛난 노송"), ("박용택", "외야수", "트윈스 한 팀에서 역사를 쓴 프랜차이즈 스타"), ("이상훈", "투수", "강렬한 투구와 상징성으로 기억되는 야생마")),
    "두산 베어스": (("박철순", "투수", "OB 창단 우승을 이끈 불사조"), ("김동주", "3루수", "베어스 중심 타선을 오랫동안 지킨 강타자"), ("김형석", "1루수", "OB·두산 타선의 세대를 이은 프랜차이즈 타자")),
    "KT 위즈": (("박경수", "2루수", "창단 초기부터 첫 통합우승까지 이끈 주장"), ("유한준", "외야수", "꾸준함과 리더십으로 위즈 문화를 세운 베테랑"), ("이강철", "감독", "구단 최초 통합우승 체제를 완성한 지도자")),
    "SSG 랜더스": (("김광현", "투수", "SK 왕조와 SSG 우승을 연결한 프랜차이즈 에이스"), ("최정", "3루수", "리그 정상급 장타력으로 구단 역사를 쓴 중심 타자"), ("박경완", "포수", "왕조 마운드를 지휘한 명포수이자 리더")),
    "롯데 자이언츠": (("최동원", "투수", "1984년 한국시리즈의 기적을 만든 무쇠팔"), ("이대호", "1루수", "부산 야구를 대표한 조선의 4번 타자"), ("박정태", "2루수", "근성과 리더십으로 기억되는 자이언츠의 심장")),
    "한화 이글스": (("장종훈", "내야수", "연습생 신화를 쓴 이글스의 홈런왕"), ("송진우", "투수", "오랜 기간 마운드를 지킨 기록의 사나이"), ("정민철", "투수", "정교한 제구로 시대를 대표한 우완 에이스")),
    "NC 다이노스": (("이호준", "지명타자", "신생 구단의 중심을 잡은 초대 리더"), ("나성범", "외야수", "다이노스 초창기 타선을 대표한 프랜차이즈 스타"), ("박석민", "3루수", "창단 첫 통합우승에 경험과 장타를 더한 베테랑")),
    "키움 히어로즈": (("박병호", "1루수", "히어로즈를 대표하는 홈런왕"), ("서건창", "2루수", "KBO 최초 200안타 시즌을 만든 교타자"), ("강정호", "유격수", "유격수 장타 시대를 연 프랜차이즈 스타")),
}


class ClubInfoPage(QWidget):
    back_requested = Signal()
    squad_requested = Signal(str)

    def __init__(self, team_name, display_name, manager_data, colors, db_path=None, parent=None):
        super().__init__(parent)
        self.team_name = team_name
        self.info = TEAM_INFO[team_name]
        self.colors = colors
        self.db_path = db_path or PLAYERS_DB_PATH
        self.players = self._load_players()

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        page = QWidget()
        page.setObjectName("ClubInfoRoot")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(18, 15, 18, 22)
        layout.setSpacing(10)

        header = QFrame()
        header.setObjectName("ClubHeader")
        header_layout = QHBoxLayout(header)
        back_button = QPushButton("←  이전 화면")
        back_button.setObjectName("BackButton")
        back_button.clicked.connect(self.back_requested.emit)
        header_layout.addWidget(back_button)
        crest = QLabel(TEAM_EMOJIS.get(team_name, "⚾"))
        crest.setFont(QFont("Segoe UI Emoji", 38))
        crest.setFixedWidth(65)
        crest.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_layout.addWidget(crest)
        heading = QVBoxLayout()
        title = QLabel(display_name)
        title.setObjectName("ClubTitle")
        title.setFont(QFont("Noto Sans KR", 25, QFont.Bold))
        heading.addWidget(title)
        heading.addWidget(QLabel(f"{team_name} · {self.info['city']} · {self.info['founded']} 창단"))
        header_layout.addLayout(heading)
        header_layout.addStretch()
        status = QLabel("KBO LEAGUE  ·  CLUB OVERVIEW")
        status.setObjectName("HeaderStatus")
        header_layout.addWidget(status)
        layout.addWidget(header)

        sections = QHBoxLayout()
        club_section = QPushButton("구단 정보")
        club_section.setObjectName("SectionActive")
        squad_section = QPushButton("선수단 정보")
        squad_section.setObjectName("SectionButton")
        squad_section.clicked.connect(lambda: self.squad_requested.emit(self.team_name))
        sections.addWidget(club_section)
        sections.addWidget(squad_section)
        sections.addStretch()
        layout.addLayout(sections)

        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(10)
        grid.setColumnStretch(0, 25)
        grid.setColumnStretch(1, 45)
        grid.setColumnStretch(2, 30)

        identity = self._card("구단 프로필")
        il = identity.layout()
        mascot = QLabel()
        mascot.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pixmap = QPixmap(str(resource_path("image", "Mascort", self.info["mascot_image"])))
        if not pixmap.isNull():
            mascot.setPixmap(pixmap.scaled(170, 110, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        else:
            mascot.setText(TEAM_EMOJIS.get(team_name, "⚾"))
            mascot.setFont(QFont("Segoe UI Emoji", 64))
        il.addWidget(mascot)
        il.addWidget(self._facts((
            ("연고지", self.info["city"]), ("홈구장", self.info["stadium"]),
            ("모기업", self.info["parent_company"]), ("단장", self.info["general_manager"]),
            ("감독", manager_data.get("manager_name", "-")), ("우승", self.info["championships"]),
        )))
        culture = QLabel(self.info["description"])
        culture.setWordWrap(True)
        culture.setObjectName("BodyText")
        il.addWidget(culture)
        grid.addWidget(identity, 0, 0, 3, 1)

        stars = self._card("핵심 선수")
        star_row = QHBoxLayout()
        for role, player in zip(("CAPTAIN", "KEY PLAYER", "HOT PROSPECT"), self._top_players()):
            star_row.addWidget(self._player_card(role, player), 1)
        stars.layout().addLayout(star_row)
        grid.addWidget(stars, 0, 1)

        stadium = self._card("홈구장")
        sl = stadium.layout()
        stadium_visual = QLabel(f"{TEAM_EMOJIS.get(team_name, '⚾')}\n{self.info['stadium']}")
        stadium_visual.setObjectName("StadiumVisual")
        stadium_visual.setAlignment(Qt.AlignmentFlag.AlignCenter)
        stadium_visual.setMinimumHeight(120)
        sl.addWidget(stadium_visual)
        sl.addWidget(self._facts((("도시", self.info["city"]), ("평균 관중", f"{self.info['average_attendance']:,}명"), ("구장 상태", "양호"))))
        grid.addWidget(stadium, 0, 2)

        vision = self._card("구단 비전과 운영 철학")
        vl = vision.layout()
        for label, text in (("이번 시즌", self.info["season_goal"]), ("장기 목표", self.info["long_term_goal"]), ("프런트", self.info["front_office_style"]), ("팬 문화", self.info["fan_style"])):
            item = QLabel(f"{label}\n{text}")
            item.setWordWrap(True)
            item.setObjectName("VisionItem")
            vl.addWidget(item)
        grid.addWidget(vision, 1, 1)

        squad = self._card("주요 선수단")
        table = QTableWidget()
        table.setColumnCount(5)
        table.setHorizontalHeaderLabels(["선수", "포지션", "나이", "종합", "상태"])
        leaders = self._top_players(8)
        table.setRowCount(len(leaders))
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(25)
        table.setMaximumHeight(245)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        for row, player in enumerate(leaders):
            rating = self._overall(player)
            for column, value in enumerate((player["name"], player["pos"], player["age"], rating, "1군" if player.get("status") else "C팀")):
                item = QTableWidgetItem(str(value))
                if column:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                table.setItem(row, column, item)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column in range(1, 5):
            table.horizontalHeader().setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        squad.layout().addWidget(table)
        grid.addWidget(squad, 2, 1)

        legends = self._card("구단을 상징하는 선수")
        legend_column = QVBoxLayout()
        for name, role, legacy in CLUB_LEGENDS.get(team_name, ()):
            legend = QFrame()
            legend.setObjectName("LegendCard")
            legend_layout = QHBoxLayout(legend)
            portrait = QLabel(name[-2:])
            portrait.setObjectName("LegendPortrait")
            portrait.setAlignment(Qt.AlignmentFlag.AlignCenter)
            portrait.setFixedSize(68, 68)
            legend_layout.addWidget(portrait)
            text = QVBoxLayout()
            legend_name = QLabel(name)
            legend_name.setObjectName("LegendName")
            text.addWidget(legend_name)
            text.addWidget(QLabel(role))
            description = QLabel(legacy)
            description.setWordWrap(True)
            description.setObjectName("BodyText")
            text.addWidget(description)
            legend_layout.addLayout(text, 1)
            legend_column.addWidget(legend, 1)
        legends.layout().addLayout(legend_column)
        grid.addWidget(legends, 1, 2, 2, 1)
        layout.addLayout(grid, 1)
        root.addWidget(page)
        self.setStyleSheet(self._style(colors))

    def _load_players(self):
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        try:
            return [dict(row) for row in connection.execute("SELECT * FROM players WHERE team = ?", (self.team_name,))]
        finally:
            connection.close()

    def _top_players(self, limit=3):
        return sorted(self.players, key=self._overall, reverse=True)[:limit]

    @staticmethod
    def _overall(player):
        detailed = [player.get(key) for key in ("contact", "power", "plate_discipline", "bat_control", "timing") if player.get(key) is not None]
        ratings = detailed or [
            _display_rating(player.get(key), True)
            for key in ("con", "pow", "eye", "def")
            if player.get(key) is not None
        ]
        return round(sum(ratings) / len(ratings), 1) if ratings else 0

    def _player_card(self, role, player):
        card = QFrame()
        card.setObjectName("PlayerCard")
        layout = QVBoxLayout(card)
        role_label = QLabel(role)
        role_label.setObjectName("PlayerRole")
        role_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(role_label)
        photo = QLabel()
        photo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        path = _player_photo_path(player.get("kbo_player_id"))
        if path:
            pixmap = QPixmap(str(path))
            photo.setPixmap(pixmap.scaled(105, 92, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        else:
            photo.setText(player["name"][-2:])
            photo.setFont(QFont("Noto Sans KR", 25, QFont.Bold))
        layout.addWidget(photo)
        name = QLabel(player["name"])
        name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name.setFont(QFont("Noto Sans KR", 14, QFont.Bold))
        layout.addWidget(name)
        meta = QLabel(f"{player['pos']} · {player['age']}세 · 종합 {self._overall(player)}")
        meta.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(meta)
        return card

    @staticmethod
    def _card(title):
        card = QFrame()
        card.setObjectName("InfoCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 10, 12, 12)
        heading = QLabel(title)
        heading.setObjectName("CardTitle")
        layout.addWidget(heading)
        return card

    @staticmethod
    def _facts(items):
        widget = QWidget()
        grid = QGridLayout(widget)
        grid.setContentsMargins(0, 0, 0, 0)
        for index, (name, value) in enumerate(items):
            grid.addWidget(QLabel(name), index, 0)
            content = QLabel(str(value))
            content.setWordWrap(True)
            content.setAlignment(Qt.AlignmentFlag.AlignRight)
            grid.addWidget(content, index, 1)
        return widget

    @staticmethod
    def _style(colors):
        return f"""
            QWidget#ClubInfoRoot {{ background-color: #11161d; }}
            QLabel {{ color: #dce5ee; font-family: 'Noto Sans KR', 'Malgun Gothic'; }}
            QFrame#ClubHeader {{ background-color: #202630; border-bottom: 2px solid {colors['accent']}; }}
            QLabel#ClubTitle {{ color: white; }}
            QLabel#HeaderStatus {{ color: {colors['accent_light']}; font-weight: 700; padding: 10px; }}
            QPushButton#BackButton {{ color: white; background-color: #151a20; border: 1px solid #46515d; border-radius: 6px; padding: 10px 16px; font-weight: 700; }}
            QPushButton#BackButton:hover {{ background-color: {colors['accent']}; border-color: {colors['accent_light']}; }}
            QPushButton#SectionActive, QPushButton#SectionButton {{ color: #c8d2dc; background-color: #1b2027; border: none; border-bottom: 2px solid #46515d; padding: 9px 24px; font-size: 14px; font-weight: 700; }}
            QPushButton#SectionActive {{ color: white; border-bottom-color: {colors['accent_light']}; background-color: #252c35; }}
            QPushButton#SectionButton:hover {{ color: white; background-color: #252c35; border-bottom-color: {colors['accent']}; }}
            QFrame#InfoCard {{ background-color: #1b2027; border: 1px solid #3b4652; border-radius: 3px; }}
            QLabel#CardTitle {{ color: {colors['accent_light']}; background-color: #252c35; border-left: 3px solid {colors['accent']}; padding: 7px 9px; font-size: 14px; font-weight: 700; }}
            QFrame#PlayerCard {{ background-color: #151a20; border: 1px solid #38424d; }}
            QLabel#PlayerRole {{ color: white; background-color: {colors['accent']}; padding: 5px; font-weight: 800; }}
            QLabel#StadiumVisual {{ color: white; background-color: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #22384b, stop:0.5 {colors['accent']}, stop:1 #17202a); border: 1px solid {colors['accent_light']}; font-size: 20px; font-weight: 800; }}
            QLabel#VisionItem, QLabel#LineupRow {{ background-color: #151a20; border-bottom: 1px solid #343e49; padding: 7px; }}
            QLabel#BodyText {{ color: #aebdcb; padding: 7px; }}
            QFrame#LegendCard {{ background-color: #151a20; border: 1px solid #38424d; border-radius: 8px; }}
            QLabel#LegendPortrait {{ color: white; background-color: {colors['accent']}; border-radius: 34px; font-size: 20px; font-weight: 800; }}
            QLabel#LegendName {{ color: white; font-size: 16px; font-weight: 800; }}
            QTableWidget {{ background-color: #151a20; alternate-background-color: #20262d; border: none; gridline-color: #343e49; }}
            QHeaderView::section {{ color: #dce5ee; background-color: #252c35; border: none; padding: 6px; }}
        """
