"""FM 스타일의 구단 종합 정보 대시보드."""

import sqlite3

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.config import TEAM_INFO
from app.team_assets import set_team_logo
from app.player_ratings import overall_rating
from app.utils import resource_path
from app.views.team_manage.player_profile import _player_photo_path
from database import PLAYERS_DB_PATH


STADIUM_IMAGE_FILES = {
    "KIA 타이거즈": "kia.jpg",
    "삼성 라이온즈": "samsung.jpg",
    "LG 트윈스": "jamsil.jpg",
    "두산 베어스": "jamsil.jpg",
    "KT 위즈": "kt.jpg",
    "SSG 랜더스": "ssg.jpg",
    "롯데 자이언츠": "lotte.jpg",
    "한화 이글스": "hanwha.jpg",
    "NC 다이노스": "NC파크.png",
    "키움 히어로즈": "kiwoom.jpg",
}


class StadiumPhotoWidget(QWidget):
    """레이아웃 크기에 영향을 주지 않고 구장 사진을 직접 그린다."""

    def __init__(self, image_path, parent=None):
        super().__init__(parent)
        self._source = QPixmap(str(image_path))
        self.setObjectName("StadiumPhoto")
        self.setFixedHeight(210)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )

    def paintEvent(self, event):
        del event
        painter = QPainter(self)
        painter.setRenderHint(
            QPainter.RenderHint.SmoothPixmapTransform,
            True,
        )

        target = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        clip = QPainterPath()
        clip.addRoundedRect(target, 5, 5)
        painter.setClipPath(clip)
        painter.fillRect(target, QColor("#10171e"))

        if self._source.isNull():
            painter.setPen(QColor("#81909d"))
            painter.drawText(
                target,
                Qt.AlignmentFlag.AlignCenter,
                "구장 사진을 불러올 수 없습니다.",
            )
        else:
            image_width = self._source.width()
            image_height = self._source.height()
            target_ratio = target.width() / target.height()
            image_ratio = image_width / image_height

            if image_ratio > target_ratio:
                source_width = image_height * target_ratio
                source = QRectF(
                    (image_width - source_width) / 2,
                    0,
                    source_width,
                    image_height,
                )
            else:
                source_height = image_width / target_ratio
                source = QRectF(
                    0,
                    (image_height - source_height) / 2,
                    image_width,
                    source_height,
                )
            painter.drawPixmap(target, self._source, source)

        painter.setClipping(False)
        painter.setPen(QPen(QColor("#34414c"), 1))
        painter.drawRoundedRect(target, 5, 5)


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
    player_requested = Signal(object)

    def __init__(
        self,
        team_name,
        display_name,
        manager_data,
        colors,
        db_path=None,
        parent=None,
    ):
        super().__init__(parent)
        self.team_name = team_name
        self.display_name = display_name
        self.manager_data = manager_data
        self.info = TEAM_INFO[team_name]
        self.colors = colors
        self.db_path = db_path or PLAYERS_DB_PATH
        self.players = self._load_players()

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        page = QWidget()
        page.setObjectName("ClubInfoRoot")
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.setSpacing(0)

        page_layout.addWidget(self._build_header())
        page_layout.addWidget(self._build_navigation())

        scroll = QScrollArea()
        scroll.setObjectName("ClubScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        content.setObjectName("ClubContent")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(24, 20, 24, 28)
        content_layout.setSpacing(16)

        content_layout.addWidget(self._build_hero())
        content_layout.addLayout(self._build_metrics())

        columns = QHBoxLayout()
        columns.setSpacing(16)
        columns.addLayout(self._build_main_column(), 7)
        columns.addLayout(self._build_side_column(), 4)
        content_layout.addLayout(columns)
        content_layout.addStretch()

        scroll.setWidget(content)
        page_layout.addWidget(scroll, 1)
        root.addWidget(page)
        self.setStyleSheet(self._style(colors))

    def _build_header(self):
        header = QFrame()
        header.setObjectName("ClubHeader")
        layout = QHBoxLayout(header)
        layout.setContentsMargins(24, 14, 24, 14)
        layout.setSpacing(14)

        back_button = QPushButton("←")
        back_button.setObjectName("BackButton")
        back_button.setToolTip("이전 화면")
        back_button.setFixedSize(42, 42)
        back_button.clicked.connect(self.back_requested.emit)
        layout.addWidget(back_button)

        crest = QLabel()
        crest.setObjectName("HeaderCrest")
        crest.setFixedSize(48, 48)
        set_team_logo(crest, self.team_name, 46, 40)
        layout.addWidget(crest)

        heading = QVBoxLayout()
        heading.setSpacing(1)
        title = QLabel(self.display_name)
        title.setObjectName("ClubTitle")
        heading.addWidget(title)
        identity = QLabel(
            f"{self.team_name}  ·  {self.info['city']}  ·  "
            f"{self.info['stadium']}"
        )
        identity.setObjectName("ClubIdentity")
        heading.addWidget(identity)
        layout.addLayout(heading)
        layout.addStretch()

        status = QLabel("KBO LEAGUE\nCLUB PROFILE")
        status.setObjectName("HeaderStatus")
        status.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        layout.addWidget(status)
        return header

    def _build_navigation(self):
        nav = QFrame()
        nav.setObjectName("ClubNav")
        layout = QHBoxLayout(nav)
        layout.setContentsMargins(24, 0, 24, 0)
        layout.setSpacing(0)

        overview = QPushButton("구단 개요")
        overview.setObjectName("SectionActive")
        squad = QPushButton("선수단")
        squad.setObjectName("SectionButton")
        squad.clicked.connect(
            lambda: self.squad_requested.emit(self.team_name)
        )
        layout.addWidget(overview)
        layout.addWidget(squad)
        layout.addStretch()
        return nav

    def _build_hero(self):
        hero = QFrame()
        hero.setObjectName("ClubHero")
        layout = QHBoxLayout(hero)
        layout.setContentsMargins(30, 25, 26, 24)
        layout.setSpacing(28)

        copy = QVBoxLayout()
        copy.setSpacing(7)
        eyebrow = QLabel("CLUB IDENTITY  /  2025")
        eyebrow.setObjectName("HeroEyebrow")
        copy.addWidget(eyebrow)
        title = QLabel(self.display_name)
        title.setObjectName("HeroTitle")
        copy.addWidget(title)
        base_name = QLabel(self.team_name)
        base_name.setObjectName("HeroBaseName")
        copy.addWidget(base_name)
        description = QLabel(self.info["description"])
        description.setObjectName("HeroDescription")
        description.setWordWrap(True)
        description.setMaximumWidth(760)
        copy.addWidget(description)
        copy.addStretch()

        goals = QHBoxLayout()
        goals.setSpacing(8)
        goals.addWidget(
            self._goal_chip("SEASON", self.info["season_goal"]), 1
        )
        goals.addWidget(
            self._goal_chip("LONG TERM", self.info["long_term_goal"]), 1
        )
        copy.addLayout(goals)
        layout.addLayout(copy, 7)

        mascot_frame = QFrame()
        mascot_frame.setObjectName("MascotFrame")
        mascot_layout = QVBoxLayout(mascot_frame)
        mascot_layout.setContentsMargins(12, 10, 12, 12)
        mascot = QLabel()
        mascot.setObjectName("MascotImage")
        mascot.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mascot.setFixedSize(260, 185)
        pixmap = QPixmap(
            str(
                resource_path(
                    "image", "Mascort", self.info["mascot_image"]
                )
            )
        )
        if not pixmap.isNull():
            mascot.setPixmap(
                pixmap.scaled(
                    250,
                    175,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        else:
            mascot.setText("마스코트 이미지 없음")
            mascot.setFont(QFont("Segoe UI Emoji", 64))
        mascot_layout.addWidget(
            mascot, 0, Qt.AlignmentFlag.AlignCenter
        )
        mascot_name = QLabel(self.info["mascot_name"])
        mascot_name.setObjectName("MascotName")
        mascot_name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mascot_layout.addWidget(mascot_name)
        layout.addWidget(mascot_frame, 3)
        return hero

    def _build_metrics(self):
        metrics = QHBoxLayout()
        metrics.setSpacing(10)
        youtube = self.info.get("youtube", {})
        values = (
            ("창단", self.info["founded"], "CLUB HISTORY"),
            (
                "한국시리즈",
                self.info["championships"].split("·")[0].strip(),
                "CHAMPIONS",
            ),
            (
                "평균 관중",
                f"{self.info['average_attendance']:,}명",
                "HOME CROWD",
            ),
            ("단장", self.info["general_manager"], "FRONT OFFICE"),
            (
                "유튜브",
                f"{int(youtube.get('subscribers', 0)):,}명",
                youtube.get("channel", "OFFICIAL"),
            ),
        )
        for label, value, note in values:
            metrics.addWidget(
                self._metric_card(label, value, note), 1
            )
        return metrics

    def _build_main_column(self):
        column = QVBoxLayout()
        column.setSpacing(16)

        stars = self._card("핵심 선수", "CURRENT SQUAD")
        row = QHBoxLayout()
        row.setSpacing(10)
        for role, player in zip(
            ("CAPTAIN", "KEY PLAYER", "HOT PROSPECT"),
            self._featured_players(),
        ):
            row.addWidget(self._player_card(role, player), 1)
        stars.layout().addLayout(row)
        column.addWidget(stars)

        vision = self._card("구단 운영 철학", "BOARD & SUPPORTERS")
        grid = QGridLayout()
        grid.setSpacing(9)
        items = (
            ("프런트 성향", self.info["front_office_style"]),
            ("팬 성향", self.info["fan_style"]),
            ("미디어 전략", self.info["social_style"]),
            (
                "감독 체제",
                f"{self.manager_data.get('manager_name', '-')} 감독 중심의 "
                "현장 운영",
            ),
        )
        for index, (label, text) in enumerate(items):
            grid.addWidget(
                self._insight_block(label, text),
                index // 2,
                index % 2,
            )
        vision.layout().addLayout(grid)
        column.addWidget(vision)

        column.addWidget(self._build_squad_card())
        return column

    def _build_side_column(self):
        column = QVBoxLayout()
        column.setSpacing(16)

        profile = self._card("구단 프로필", "ORGANISATION")
        profile.layout().addWidget(
            self._facts(
                (
                    ("연고지", self.info["city"]),
                    ("홈구장", self.info["stadium"]),
                    ("모기업", self.info["parent_company"]),
                    ("단장", self.info["general_manager"]),
                    (
                        "감독",
                        self.manager_data.get("manager_name", "-"),
                    ),
                    ("마스코트", self.info["mascot_name"]),
                    ("역대 우승", self.info["championships"]),
                )
            )
        )
        column.addWidget(profile)

        stadium = self._card("홈구장", "HOME OF THE CLUB")
        stadium_file = STADIUM_IMAGE_FILES.get(self.team_name, "")
        stadium_path = resource_path(
            "image", "Stadium", stadium_file
        )
        visual = StadiumPhotoWidget(stadium_path)
        stadium.layout().addWidget(visual)

        stadium_name = QLabel(self.info["stadium"])
        stadium_name.setObjectName("StadiumName")
        stadium_name.setWordWrap(True)
        stadium.layout().addWidget(stadium_name)

        stadium_meta = QLabel(
            f"{self.info['city']}  ·  평균 관중 "
            f"{self.info['average_attendance']:,}명"
        )
        stadium_meta.setObjectName("StadiumMeta")
        stadium_meta.setWordWrap(True)
        stadium.layout().addWidget(stadium_meta)
        column.addWidget(stadium)

        legends = self._card("구단 레전드", "CLUB ICONS")
        legends_layout = QVBoxLayout()
        legends_layout.setSpacing(8)
        for name, role, legacy in CLUB_LEGENDS.get(
            self.team_name, ()
        ):
            legends_layout.addWidget(
                self._legend_card(name, role, legacy)
            )
        legends.layout().addLayout(legends_layout)
        column.addWidget(legends)
        column.addStretch()
        return column

    def _build_squad_card(self):
        card = self._card("전력 핵심 명단", "TOP RATED PLAYERS")
        table = QTableWidget()
        table.setColumnCount(5)
        table.setHorizontalHeaderLabels(
            ["선수", "포지션", "나이", "종합", "상태"]
        )
        leaders = self._top_players(8)
        table.setRowCount(len(leaders))
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(34)
        table.setMinimumHeight(305)
        table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers
        )
        table.setAlternatingRowColors(True)
        for row, player in enumerate(leaders):
            reserve_label = (
                "C팀(퓨처스)"
                if player.get("team") == "NC 다이노스"
                else "퓨처스팀"
            )
            values = (
                player["name"],
                player["pos"],
                player["age"],
                self._overall(player),
                "1군" if player.get("status") else reserve_label,
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if column == 0:
                    font = item.font()
                    font.setUnderline(True)
                    item.setFont(font)
                    item.setToolTip(
                        f"{player['name']} 선수 상세 정보 열기"
                    )
                else:
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignCenter
                    )
                table.setItem(row, column, item)
        table.cellClicked.connect(
            lambda row, column: self.player_requested.emit(
                leaders[row]
            )
            if column == 0 and 0 <= row < len(leaders)
            else None
        )
        table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        for column in range(1, 5):
            table.horizontalHeader().setSectionResizeMode(
                column, QHeaderView.ResizeMode.ResizeToContents
            )
        card.layout().addWidget(table)
        return card

    def _load_players(self):
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        try:
            return [
                dict(row)
                for row in connection.execute(
                    "SELECT * FROM players WHERE team = ?",
                    (self.team_name,),
                )
            ]
        finally:
            connection.close()

    def _top_players(self, limit=3):
        return sorted(
            self.players, key=self._overall, reverse=True
        )[:limit]

    def _featured_players(self):
        """사진 자산과 실제 역할을 우선해 대표 카드 3명을 구성한다."""
        preferred = {
            "NC 다이노스": ("박민우", "라일리", "김녹원"),
        }.get(self.team_name, ())
        by_name = {
            player["name"]: player for player in self.players
        }
        featured = [
            by_name[name] for name in preferred if name in by_name
        ]
        used = {player["name"] for player in featured}
        featured.extend(
            player
            for player in self._top_players()
            if player["name"] not in used
        )
        return featured[:3]

    @staticmethod
    def _overall(player):
        return overall_rating(player)

    def _player_card(self, role, player):
        card = QFrame()
        card.setObjectName("PlayerCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(0, 0, 0, 12)
        layout.setSpacing(5)

        role_label = QLabel(role)
        role_label.setObjectName("PlayerRole")
        role_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(role_label)

        photo = QLabel()
        photo.setObjectName("PlayerPhoto")
        photo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        photo.setFixedHeight(172)
        path = _player_photo_path(
            player.get("kbo_player_id"),
            player.get("name"),
            self.team_name,
        )
        if path:
            pixmap = QPixmap(str(path))
            scaled = pixmap.scaled(
                210,
                164,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            photo.setPixmap(scaled)
        else:
            photo.setText(player["name"][-2:])
            photo.setFont(QFont("Malgun Gothic", 25, QFont.Bold))
        layout.addWidget(photo)

        name = QPushButton(player["name"])
        name.setObjectName("PlayerNameLink")
        name.setCursor(Qt.CursorShape.PointingHandCursor)
        name.setToolTip(f"{player['name']} 선수 상세 정보 열기")
        name.clicked.connect(
            lambda _checked=False, selected=player:
            self.player_requested.emit(selected)
        )
        layout.addWidget(name)
        meta = QLabel(
            f"{player['pos']}  ·  {player['age']}세  ·  "
            f"종합 {self._overall(player)}"
        )
        meta.setObjectName("PlayerMeta")
        meta.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(meta)
        return card

    def _goal_chip(self, label, text):
        chip = QFrame()
        chip.setObjectName("GoalChip")
        layout = QVBoxLayout(chip)
        layout.setContentsMargins(12, 9, 12, 10)
        layout.setSpacing(3)
        heading = QLabel(label)
        heading.setObjectName("GoalLabel")
        layout.addWidget(heading)
        content = QLabel(text)
        content.setObjectName("GoalText")
        content.setWordWrap(True)
        layout.addWidget(content)
        return chip

    @staticmethod
    def _metric_card(label, value, note):
        card = QFrame()
        card.setObjectName("MetricCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(13, 11, 13, 11)
        layout.setSpacing(2)
        heading = QLabel(label)
        heading.setObjectName("MetricLabel")
        layout.addWidget(heading)
        metric = QLabel(str(value))
        metric.setObjectName("MetricValue")
        metric.setWordWrap(True)
        layout.addWidget(metric)
        detail = QLabel(str(note))
        detail.setObjectName("MetricNote")
        detail.setWordWrap(True)
        layout.addWidget(detail)
        return card

    @staticmethod
    def _insight_block(label, text):
        block = QFrame()
        block.setObjectName("InsightBlock")
        layout = QVBoxLayout(block)
        layout.setContentsMargins(12, 10, 12, 11)
        layout.setSpacing(4)
        heading = QLabel(label)
        heading.setObjectName("InsightTitle")
        layout.addWidget(heading)
        description = QLabel(text)
        description.setObjectName("InsightText")
        description.setWordWrap(True)
        layout.addWidget(description)
        return block

    @staticmethod
    def _legend_card(name, role, legacy):
        card = QFrame()
        card.setObjectName("LegendCard")
        layout = QHBoxLayout(card)
        layout.setContentsMargins(10, 9, 10, 9)
        layout.setSpacing(10)
        portrait = QLabel(name[-2:])
        portrait.setObjectName("LegendPortrait")
        portrait.setAlignment(Qt.AlignmentFlag.AlignCenter)
        portrait.setFixedSize(52, 52)
        layout.addWidget(portrait)
        copy = QVBoxLayout()
        copy.setSpacing(1)
        title = QLabel(name)
        title.setObjectName("LegendName")
        copy.addWidget(title)
        subtitle = QLabel(role)
        subtitle.setObjectName("LegendRole")
        copy.addWidget(subtitle)
        description = QLabel(legacy)
        description.setObjectName("BodyText")
        description.setWordWrap(True)
        copy.addWidget(description)
        layout.addLayout(copy, 1)
        return card

    @staticmethod
    def _card(title, eyebrow=None):
        card = QFrame()
        card.setObjectName("InfoCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 13, 14, 14)
        layout.setSpacing(10)
        header = QHBoxLayout()
        heading = QLabel(title)
        heading.setObjectName("CardTitle")
        header.addWidget(heading)
        header.addStretch()
        if eyebrow:
            note = QLabel(eyebrow)
            note.setObjectName("CardEyebrow")
            header.addWidget(note)
        layout.addLayout(header)
        return card

    @staticmethod
    def _facts(items):
        widget = QWidget()
        grid = QGridLayout(widget)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(0)
        for index, (name, value) in enumerate(items):
            label = QLabel(name)
            label.setObjectName("FactName")
            grid.addWidget(label, index, 0)
            content = QLabel(str(value))
            content.setObjectName("FactValue")
            content.setWordWrap(True)
            content.setAlignment(
                Qt.AlignmentFlag.AlignRight
                | Qt.AlignmentFlag.AlignVCenter
            )
            grid.addWidget(content, index, 1)
        grid.setColumnStretch(1, 1)
        return widget

    @staticmethod
    def _style(colors):
        return f"""
            QWidget#ClubInfoRoot, QWidget#ClubContent {{
                background-color: #0d1218;
            }}
            QLabel {{
                color: #dce5ee;
                font-family: 'Malgun Gothic', 'Segoe UI';
            }}
            QFrame#ClubHeader {{
                background-color: #171e26;
                border-bottom: 1px solid #34404b;
            }}
            QLabel#HeaderCrest {{
                background: #202a34;
                border: 1px solid #3b4956;
                border-radius: 5px;
            }}
            QLabel#ClubTitle {{
                color: white;
                font-size: 20px;
                font-weight: 900;
            }}
            QLabel#ClubIdentity {{
                color: #8493a1;
                font-size: 14px;
            }}
            QLabel#HeaderStatus {{
                color: {colors['accent_light']};
                font-size: 13px;
                font-weight: 900;
            }}
            QPushButton#BackButton {{
                color: white;
                background-color: #11171d;
                border: 1px solid #465563;
                border-radius: 5px;
                font-size: 20px;
                font-weight: 800;
                padding: 0;
            }}
            QPushButton#BackButton:hover {{
                background-color: {colors['accent']};
                border-color: {colors['accent_light']};
            }}
            QFrame#ClubNav {{
                background: #131920;
                border-bottom: 1px solid #29343e;
            }}
            QPushButton#SectionActive, QPushButton#SectionButton {{
                min-height: 40px;
                color: #8795a2;
                background: transparent;
                border: none;
                border-bottom: 3px solid transparent;
                padding: 0 20px;
                font-size: 15px;
                font-weight: 800;
            }}
            QPushButton#SectionActive {{
                color: white;
                border-bottom-color: {colors['accent_light']};
            }}
            QPushButton#SectionButton:hover {{
                color: white;
                background: #1a222b;
            }}
            QScrollArea#ClubScroll {{
                background: #0d1218;
                border: none;
            }}
            QFrame#ClubHero {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 #18232d,
                    stop:0.58 #141d25,
                    stop:1 {colors['card_bg']}
                );
                border: 1px solid #3a4855;
                border-top: 3px solid {colors['accent_light']};
                border-radius: 9px;
            }}
            QLabel#HeroEyebrow {{
                color: {colors['accent_light']};
                font-size: 13px;
                font-weight: 900;
            }}
            QLabel#HeroTitle {{
                color: white;
                font-size: 30px;
                font-weight: 900;
            }}
            QLabel#HeroBaseName {{
                color: #8d9ba8;
                font-size: 14px;
                font-weight: 750;
            }}
            QLabel#HeroDescription {{
                color: #c1ccd5;
                font-size: 15px;
            }}
            QFrame#MascotFrame {{
                background: rgba(8, 13, 18, 125);
                border: 1px solid rgba(150, 170, 188, 55);
                border-radius: 8px;
            }}
            QLabel#MascotName {{
                color: #9cabba;
                font-size: 14px;
                font-weight: 750;
            }}
            QFrame#GoalChip {{
                background: rgba(8, 13, 18, 155);
                border: 1px solid #3b4955;
                border-radius: 5px;
            }}
            QLabel#GoalLabel {{
                color: {colors['accent_light']};
                font-size: 13px;
                font-weight: 900;
            }}
            QLabel#GoalText {{
                color: #e7edf2;
                font-size: 14px;
                font-weight: 700;
            }}
            QFrame#MetricCard {{
                background: #171e25;
                border: 1px solid #303b46;
                border-radius: 7px;
            }}
            QLabel#MetricLabel {{
                color: #7f8e9b;
                font-size: 13px;
                font-weight: 800;
            }}
            QLabel#MetricValue {{
                color: white;
                font-size: 18px;
                font-weight: 900;
            }}
            QLabel#MetricNote {{
                color: #657582;
                font-size: 13px;
            }}
            QFrame#InfoCard {{
                background: #171e25;
                border: 1px solid #303b46;
                border-radius: 8px;
            }}
            QLabel#CardTitle {{
                color: white;
                font-size: 16px;
                font-weight: 900;
            }}
            QLabel#CardEyebrow {{
                color: {colors['accent_light']};
                font-size: 13px;
                font-weight: 900;
            }}
            QFrame#PlayerCard {{
                background: #11171d;
                border: 1px solid #35414c;
                border-radius: 6px;
            }}
            QLabel#PlayerRole {{
                color: white;
                background: {colors['accent']};
                padding: 6px;
                font-size: 13px;
                font-weight: 900;
                border-top-left-radius: 5px;
                border-top-right-radius: 5px;
            }}
            QLabel#PlayerPhoto {{
                background: #1d2730;
                border-bottom: 1px solid #34414c;
            }}
            QPushButton#PlayerNameLink {{
                min-height: 26px;
                color: white;
                background: transparent;
                border: none;
                padding: 2px;
                font-size: 15px;
                font-weight: 900;
            }}
            QPushButton#PlayerNameLink:hover {{
                color: {colors['accent_light']};
            }}
            QLabel#PlayerMeta {{
                color: #82919e;
                font-size: 13px;
            }}
            QFrame#InsightBlock {{
                background: #11171d;
                border: 1px solid #2e3943;
                border-left: 3px solid {colors['accent']};
                border-radius: 4px;
            }}
            QLabel#InsightTitle {{
                color: {colors['accent_light']};
                font-size: 14px;
                font-weight: 900;
            }}
            QLabel#InsightText {{
                color: #acbac6;
                font-size: 14px;
            }}
            QWidget#StadiumPhoto {{
                color: #81909d;
                background: #10171e;
                border: 1px solid #34414c;
                border-radius: 5px;
                font-size: 13px;
            }}
            QLabel#StadiumName {{
                color: white;
                padding-top: 6px;
                font-size: 15px;
                font-weight: 900;
            }}
            QLabel#StadiumMeta {{
                color: #82919e;
                padding-bottom: 2px;
                font-size: 14px;
                font-weight: 700;
            }}
            QLabel#FactName {{
                color: #788794;
                padding: 8px 0;
                border-bottom: 1px solid #28333d;
                font-size: 13px;
                font-weight: 750;
            }}
            QLabel#FactValue {{
                color: #d7e0e7;
                padding: 8px 0;
                border-bottom: 1px solid #28333d;
                font-size: 14px;
                font-weight: 700;
            }}
            QFrame#LegendCard {{
                background: #11171d;
                border: 1px solid #303b46;
                border-radius: 5px;
            }}
            QLabel#LegendPortrait {{
                color: white;
                background: {colors['accent']};
                border-radius: 4px;
                font-size: 15px;
                font-weight: 900;
            }}
            QLabel#LegendName {{
                color: white;
                font-size: 15px;
                font-weight: 900;
            }}
            QLabel#LegendRole {{
                color: {colors['accent_light']};
                font-size: 13px;
                font-weight: 800;
            }}
            QLabel#BodyText {{
                color: #8e9daa;
                font-size: 13px;
            }}
            QTableWidget {{
                color: #dbe4eb;
                background-color: #11171d;
                alternate-background-color: #151d24;
                border: 1px solid #2f3a44;
                border-radius: 4px;
                gridline-color: #26313a;
                selection-background-color: {colors['accent']};
            }}
            QHeaderView::section {{
                color: #9cabb7;
                background-color: #202a33;
                border: none;
                border-right: 1px solid #303b45;
                padding: 7px;
                font-size: 13px;
                font-weight: 800;
            }}
        """
