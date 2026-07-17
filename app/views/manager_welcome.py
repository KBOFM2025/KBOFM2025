"""새 감독 부임 직후 한 번 표시하는 FM 스타일 뉴스 화면."""

from datetime import date

from PySide6.QtCore import QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QFont, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.config import start_point_title
from app.utils import resource_path


class NewsPhotoLabel(QLabel):
    """검은 여백 없이 사진 중심부를 최소한으로 잘라 표시한다."""

    def __init__(self, image_path, parent=None):
        super().__init__(parent)
        self.source_pixmap = QPixmap(str(image_path))
        self.setAlignment(Qt.AlignCenter)
        self.setContentsMargins(0, 0, 0, 0)
        self.setMinimumHeight(250)
        self.setMaximumHeight(320)
        self.setMaximumWidth(520)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)

    def sizeHint(self):
        return QSize(430, 290)

    def minimumSizeHint(self):
        return QSize(300, 250)

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.source_pixmap.isNull() or self.width() <= 2 or self.height() <= 2:
            return

        target = self.rect().adjusted(1, 1, -1, -1)
        scaled = self.source_pixmap.scaled(
            target.size(),
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
        crop_x = max(0, (scaled.width() - target.width()) // 2)
        crop_y = max(0, (scaled.height() - target.height()) // 2)
        source = QRect(crop_x, crop_y, target.width(), target.height())

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        clip_path = QPainterPath()
        clip_path.addRoundedRect(QRectF(target), 7, 7)
        painter.setClipPath(clip_path)
        painter.drawPixmap(target, scaled, source)


class ManagerWelcomePage(QWidget):
    continue_requested = Signal()

    def __init__(
        self,
        club_name,
        base_team,
        manager_data,
        start_point,
        team_info,
        colors,
        parent=None,
    ):
        super().__init__(parent)
        manager_name = manager_data.get("manager_name", "무명")
        manager_style = manager_data.get("manager_style", "나만의")
        today = date.today().strftime("%Y.%m.%d")

        self.setObjectName("WelcomeNewsPage")
        self.setStyleSheet(self._style(colors))

        outer = QVBoxLayout(self)
        outer.setContentsMargins(70, 42, 70, 52)
        outer.setSpacing(0)

        masthead = QHBoxLayout()
        publication = QLabel("KBO BASEBALL MANAGER  ·  CLUB NEWS")
        publication.setObjectName("Publication")
        masthead.addWidget(publication)
        masthead.addStretch()
        published_at = QLabel(today)
        published_at.setObjectName("PublishedAt")
        masthead.addWidget(published_at)
        outer.addLayout(masthead)

        rule = QFrame()
        rule.setObjectName("NewsRule")
        rule.setFixedHeight(2)
        outer.addWidget(rule)
        outer.addSpacing(30)

        category = QLabel("구단 공식 발표  |  신임 감독 선임")
        category.setObjectName("Category")
        outer.addWidget(category)
        outer.addSpacing(12)

        headline = QLabel(f"{club_name}, {manager_name} 신임 감독 선임")
        headline.setObjectName("Headline")
        headline.setWordWrap(True)
        headline.setFont(QFont("Noto Sans KR", 34, QFont.Bold))
        outer.addWidget(headline)

        welcome = QLabel(f"반갑습니다, {manager_name} 감독님.")
        welcome.setObjectName("Welcome")
        welcome.setWordWrap(True)
        outer.addWidget(welcome)
        outer.addSpacing(24)

        article_row = QHBoxLayout()
        article_row.setSpacing(28)

        article = QFrame()
        article.setObjectName("Article")
        article_layout = QVBoxLayout(article)
        article_layout.setContentsMargins(26, 24, 26, 24)
        article_layout.setSpacing(16)

        press_photo = NewsPhotoLabel(resource_path("image", "First", "First_image.png"))
        press_photo.setObjectName("PressPhoto")
        article_layout.addWidget(press_photo, 0, Qt.AlignmentFlag.AlignHCenter)

        photo_caption = QLabel(
            f"{manager_name} 신임 감독이 구단 관계자와 악수한 뒤 취재진의 질문을 받고 있다."
        )
        photo_caption.setObjectName("PhotoCaption")
        photo_caption.setWordWrap(True)
        photo_caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
        article_layout.addWidget(photo_caption)

        lead = QLabel(
            f'{base_team} 구단이 {manager_name} 감독의 선임을 공식 발표했다.\n\n'
            f'구단은 {manager_style} 스타일을 바탕으로 선수단의 경쟁력을 끌어올리고 '
            f'새로운 시즌 목표를 달성해 줄 것으로 기대하고 있다.'
        )
        lead.setObjectName("Lead")
        lead.setWordWrap(True)
        lead.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        article_layout.addWidget(lead)

        quote = QLabel(
            f'“{club_name}의 전통을 존중하면서도 제 야구 철학을 분명하게 보여드리겠습니다. '
            '팬들이 자랑스러워할 수 있는 팀을 만들겠습니다.”'
        )
        quote.setObjectName("Quote")
        quote.setWordWrap(True)
        article_layout.addWidget(quote)

        outlook = QLabel(
            f'신임 감독의 첫 공식 일정은 「{start_point_title(start_point)}」부터 시작된다. '
            f'구단이 제시한 이번 시즌 목표는 “{team_info["season_goal"]}”이다.'
        )
        outlook.setObjectName("Body")
        outlook.setWordWrap(True)
        article_layout.addWidget(outlook)
        article_layout.addStretch()
        article_row.addWidget(article, 3)

        briefing = QFrame()
        briefing.setObjectName("Briefing")
        briefing_layout = QVBoxLayout(briefing)
        briefing_layout.setContentsMargins(22, 22, 22, 22)
        briefing_layout.setSpacing(13)

        briefing_title = QLabel("APPOINTMENT BRIEFING")
        briefing_title.setObjectName("BriefingTitle")
        briefing_layout.addWidget(briefing_title)
        briefing_layout.addWidget(
            self._fact("감독", f'{manager_name} · {manager_data.get("manager_age", 45)}세')
        )
        briefing_layout.addWidget(self._fact("운영 스타일", manager_style))
        briefing_layout.addWidget(self._fact("부임 시점", start_point_title(start_point)))
        briefing_layout.addWidget(self._fact("단장", team_info["general_manager"]))
        briefing_layout.addWidget(self._fact("홈구장", team_info["stadium"]))
        briefing_layout.addStretch()
        article_row.addWidget(briefing, 2)

        outer.addLayout(article_row, 1)
        outer.addSpacing(24)

        actions = QHBoxLayout()
        hint = QLabel("구단 이사회와의 첫 미팅이 준비되어 있습니다.")
        hint.setObjectName("Hint")
        actions.addWidget(hint)
        actions.addStretch()
        continue_button = QPushButton("감독 업무 시작  →")
        continue_button.setObjectName("ContinueButton")
        continue_button.clicked.connect(self.continue_requested.emit)
        actions.addWidget(continue_button)
        outer.addLayout(actions)

    @staticmethod
    def _fact(title, value):
        label = QLabel(f"{title}\n{value}")
        label.setObjectName("Fact")
        label.setWordWrap(True)
        return label

    @staticmethod
    def _style(colors):
        return f"""
            QWidget#WelcomeNewsPage {{ background-color: #07111f; }}
            QLabel {{ color: #dbe7f3; font-family: 'Noto Sans KR', 'Malgun Gothic'; }}
            QLabel#Publication {{ color: {colors['accent_light']}; font-size: 15px; font-weight: 700; }}
            QLabel#PublishedAt {{ color: #8495a8; font-size: 14px; }}
            QFrame#NewsRule {{ background-color: {colors['accent']}; border: none; }}
            QLabel#Category {{ color: {colors['accent_light']}; font-size: 15px; font-weight: 700; }}
            QLabel#Headline {{ color: #ffffff; }}
            QLabel#Welcome {{ color: #b8c9da; font-size: 23px; margin-top: 5px; }}
            QFrame#Article {{ background-color: #0d1b2a; border: 1px solid #2c4055; border-radius: 12px; }}
            QLabel#PressPhoto {{ background-color: #050b14; border: 1px solid #263b52; border-radius: 7px; }}
            QLabel#PhotoCaption {{ color: #8495a8; font-size: 12px; padding-bottom: 5px; }}
            QLabel#Lead {{ color: #edf4fa; font-size: 18px; line-height: 1.5; }}
            QLabel#Quote {{ color: #ffffff; background-color: {colors['card_bg']}; border-left: 4px solid {colors['accent']}; padding: 20px; font-size: 17px; font-weight: 700; }}
            QLabel#Body {{ color: #c4d2df; font-size: 16px; }}
            QFrame#Briefing {{ background-color: {colors['card_bg']}; border: 1px solid {colors['accent']}; border-radius: 10px; }}
            QLabel#BriefingTitle {{ color: {colors['accent_light']}; font-size: 14px; font-weight: 700; }}
            QLabel#Fact {{ color: #f8fafc; background-color: rgba(7, 17, 31, 150); border-radius: 7px; padding: 12px; font-size: 14px; }}
            QLabel#Hint {{ color: #8495a8; font-size: 14px; }}
            QPushButton#ContinueButton {{ color: white; background-color: {colors['accent']}; border: 1px solid {colors['accent_light']}; border-radius: 8px; padding: 15px 28px; font-family: 'Noto Sans KR', 'Malgun Gothic'; font-size: 16px; font-weight: 700; }}
            QPushButton#ContinueButton:hover {{ background-color: {colors['accent_light']}; }}
        """
