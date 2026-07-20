"""전체 뉴스와 현재 날짜의 구단 브리핑 화면."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame,
    QButtonGroup,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.config import start_point_title


class NewsCard(QFrame):
    def __init__(self, category, headline, body, published_at, colors, parent=None):
        super().__init__(parent)
        is_medical = category == "의료 센터"
        self.setObjectName("MedicalNewsCard" if is_medical else "NewsCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 17, 20, 17)
        layout.setSpacing(8)

        meta = QHBoxLayout()
        category_label = QLabel(category)
        category_label.setStyleSheet(
            f"color: {'#ff7676' if is_medical else colors['accent_light']}; font-size: 13px; font-weight: 700;"
        )
        meta.addWidget(category_label)
        meta.addStretch()
        date_label = QLabel(published_at)
        date_label.setStyleSheet("color: #8292a3; font-size: 13px;")
        meta.addWidget(date_label)
        layout.addLayout(meta)

        headline_label = QLabel(headline)
        headline_label.setWordWrap(True)
        headline_label.setFont(QFont("Noto Sans KR", 19, QFont.Bold))
        layout.addWidget(headline_label)

        body_label = QLabel(body)
        body_label.setWordWrap(True)
        body_label.setStyleSheet("color: #b9c8d7; font-size: 14px;")
        layout.addWidget(body_label)

        self.setStyleSheet(f"""
            QFrame#NewsCard {{
                background-color: {colors['card_bg']};
                border: 1px solid #263b52;
                border-radius: 9px;
            }}
            QFrame#NewsCard:hover {{ border-color: {colors['accent']}; }}
            QFrame#MedicalNewsCard {{
                background-color: #21171a;
                border: 1px solid #9f3d49;
                border-left: 5px solid #ef4d5d;
                border-radius: 9px;
            }}
            QFrame#MedicalNewsCard:hover {{ border-color: #ff6b78; }}
            QLabel {{ color: {colors['text']}; font-family: 'Noto Sans KR', 'Malgun Gothic'; }}
        """)


class NewsFeedPage(QWidget):
    """게임에 누적되는 전체 구단·리그 뉴스 피드."""

    notification_count_changed = Signal(int)

    def __init__(
        self,
        club_name,
        base_team,
        manager_data,
        start_point,
        appointment_date,
        team_info,
        colors,
        save_database=None,
        save_id=None,
        parent=None,
    ):
        super().__init__(parent)
        self.club_name = club_name
        self.base_team = base_team
        self.colors = colors
        self.save_database = save_database
        self.save_id = save_id
        self.current_date = appointment_date
        manager_name = manager_data.get("manager_name", "무명")
        self.initial_news = [
            {
                "category": "구단 공식 발표",
                "headline": f"{club_name}, {manager_name} 신임 감독 선임",
                "body": f"{base_team}은 {manager_name} 감독과 함께 새 시즌 준비를 시작한다. 첫 업무 시점은 {start_point_title(start_point)}이다.",
                "news_date": appointment_date.isoformat(),
            },
            {
                "category": "시즌 전망",
                "headline": f"{club_name}이 제시한 첫 번째 시즌 목표",
                "body": team_info["season_goal"],
                "news_date": appointment_date.isoformat(),
            },
            {
                "category": "프런트 브리핑",
                "headline": f'{team_info["general_manager"]} 단장, 신임 감독에게 운영 방향 전달',
                "body": team_info["front_office_style"],
                "news_date": appointment_date.isoformat(),
            },
        ]

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)

        header = QHBoxLayout()
        title = QLabel("📰 KBO 뉴스 센터")
        title.setFont(QFont("Noto Sans KR", 26, QFont.Bold))
        header.addWidget(title)
        header.addStretch()
        self.article_count = QLabel()
        self.article_count.setStyleSheet(f"color: {colors['accent_light']}; font-weight: 700;")
        header.addWidget(self.article_count)
        self.read_all_button = QPushButton("새 뉴스 모두 읽음")
        self.read_all_button.setObjectName("NewsReadAll")
        self.read_all_button.clicked.connect(self.mark_all_read)
        header.addWidget(self.read_all_button)
        layout.addLayout(header)
        subtitle = QLabel("구단 공식 발표와 리그 주요 소식을 시간순으로 확인합니다.")
        subtitle.setStyleSheet("color: #a6b5c5; font-size: 14px;")
        layout.addWidget(subtitle)

        filters = QHBoxLayout()
        self.filter_group = QButtonGroup(self)
        self.filter_group.setExclusive(True)
        for index, (label, key) in enumerate((("전체 뉴스", "all"), ("부상·복귀", "medical"), ("내 구단", "club"), ("리그", "league"))):
            button = QPushButton(label)
            button.setCheckable(True)
            button.setProperty("news_filter", key)
            button.setObjectName("NewsFilter")
            self.filter_group.addButton(button, index)
            filters.addWidget(button)
            if index == 0:
                button.setChecked(True)
        filters.addStretch()
        self.filter_group.idClicked.connect(self.refresh_news)
        layout.addLayout(filters)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        layout.addWidget(self.scroll, 1)
        self.setStyleSheet(f"""
            QPushButton#NewsFilter {{ color: #aab7c5; background: #171e26; border: 1px solid #384654; border-radius: 6px; padding: 8px 18px; font-weight: 700; }}
            QPushButton#NewsFilter:hover, QPushButton#NewsFilter:checked {{ color: white; background: {colors['accent']}; border-color: {colors['accent_light']}; }}
            QPushButton#NewsReadAll {{ color: white; background: {colors['accent']}; border: none; border-radius: 6px; padding: 8px 15px; font-weight: 700; }}
        """)
        self.refresh_news()

    def set_game_date(self, game_date):
        self.current_date = game_date
        self.refresh_news()

    def set_save_id(self, save_id):
        self.save_id = save_id
        self.refresh_news()

    def _all_news(self):
        stored = self.save_database.list_daily_news(self.save_id) if self.save_database and self.save_id is not None else []
        combined, known = [], set()
        for news in [*stored, *self.initial_news]:
            item = dict(news)
            if item["category"] == "의료 센터" and (
                "발생 당시 소속은 2군," in item["body"] or "기존 2군 선수단" in item["body"]
            ):
                continue
            key = (item["news_date"], item["headline"])
            if key not in known:
                combined.append(item)
                known.add(key)
        return sorted(combined, key=lambda item: (item["news_date"], item.get("id", 0)), reverse=True)

    def refresh_news(self, _button_id=None):
        checked = self.filter_group.checkedButton()
        selected_filter = checked.property("news_filter") if checked else "all"
        articles = self._all_news()
        if selected_filter == "medical":
            articles = [item for item in articles if item["category"] == "의료 센터"]
        elif selected_filter == "club":
            articles = [item for item in articles if self.base_team in f"{item['headline']} {item['body']}" or item["category"] in ("구단 공식 발표", "프런트 브리핑")]
        elif selected_filter == "league":
            articles = [item for item in articles if item["category"] in ("리그", "리그 시뮬레이션", "상대 구단")]

        self.article_count.setText(f"기사 {len(articles)}건")
        unread = self.save_database.unread_daily_news_count(self.save_id) if self.save_database and self.save_id is not None else 0
        self.read_all_button.setEnabled(unread > 0)
        self.notification_count_changed.emit(unread)
        feed = QWidget()
        feed.setStyleSheet("background: transparent;")
        feed_layout = QVBoxLayout(feed)
        feed_layout.setContentsMargins(0, 4, 6, 4)
        feed_layout.setSpacing(12)
        for item in articles:
            feed_layout.addWidget(NewsCard(
                item["category"], item["headline"], item["body"],
                item["news_date"].replace("-", "."), self.colors,
            ))
        if not articles:
            empty = QLabel("해당 조건의 뉴스가 없습니다.")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setStyleSheet("color: #718096; padding: 60px;")
            feed_layout.addWidget(empty)
        feed_layout.addStretch()
        self.scroll.setWidget(feed)

    def mark_all_read(self):
        if self.save_database and self.save_id is not None:
            self.save_database.mark_all_daily_news_read(self.save_id)
        self.refresh_news()

    @staticmethod
    def _date_text(game_date):
        return f"{game_date.year}.{game_date.month:02d}.{game_date.day:02d}"


class DailyNewsCard(QFrame):
    def __init__(self, news, colors, on_confirm, parent=None):
        super().__init__(parent)
        is_read = bool(news["is_read"])
        self.setObjectName("DailyNewsCardRead" if is_read else "DailyNewsCardUnread")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(8)

        meta = QHBoxLayout()
        category = QLabel(news["category"])
        category.setStyleSheet(
            f"color: {colors['accent_light']}; font-size: 13px; font-weight: 700;"
        )
        meta.addWidget(category)
        meta.addStretch()
        status = QLabel("확인함" if is_read else "● 미확인")
        status.setStyleSheet(
            "color: #8292a3; font-size: 13px;"
            if is_read
            else "color: #fbbf24; font-size: 13px; font-weight: 700;"
        )
        meta.addWidget(status)
        layout.addLayout(meta)

        headline = QLabel(news["headline"])
        headline.setWordWrap(True)
        headline.setFont(QFont("Noto Sans KR", 18, QFont.Bold))
        layout.addWidget(headline)

        body = QLabel(news["body"])
        body.setWordWrap(True)
        body.setStyleSheet("color: #b9c8d7; font-size: 14px;")
        layout.addWidget(body)

        footer = QHBoxLayout()
        published = QLabel(news["news_date"].replace("-", "."))
        published.setStyleSheet("color: #8292a3; font-size: 12px;")
        footer.addWidget(published)
        footer.addStretch()
        if not is_read:
            confirm_button = QPushButton("확인")
            confirm_button.setObjectName("ConfirmNewsButton")
            confirm_button.clicked.connect(
                lambda _checked=False, news_key=news["session_key"]: on_confirm(news_key)
            )
            footer.addWidget(confirm_button)
        layout.addLayout(footer)

        self.setStyleSheet(f"""
            QFrame#DailyNewsCardUnread {{
                background-color: {colors['card_bg']};
                border: 1px solid {colors['accent']};
                border-radius: 9px;
            }}
            QFrame#DailyNewsCardRead {{
                background-color: #0d1b2a;
                border: 1px solid #263b52;
                border-radius: 9px;
            }}
            QLabel {{ color: {colors['text']}; font-family: 'Noto Sans KR', 'Malgun Gothic'; }}
            QPushButton#ConfirmNewsButton {{
                color: white;
                background-color: {colors['accent']};
                border: none;
                border-radius: 6px;
                padding: 7px 16px;
                font-weight: bold;
            }}
            QPushButton#ConfirmNewsButton:hover {{ background-color: {colors['accent_light']}; }}
        """)


class DailyNewsPage(QWidget):
    """날짜별 소식을 세이브 단위로 누적하고 확인 상태를 관리한다."""

    unread_count_changed = Signal(int)

    def __init__(
        self,
        club_name,
        manager_data,
        start_point,
        appointment_date,
        colors,
        save_database,
        save_id,
        parent=None,
    ):
        super().__init__(parent)
        self.club_name = club_name
        self.manager_name = manager_data.get("manager_name", "무명")
        self.start_point = start_point
        self.appointment_date = appointment_date
        self.colors = colors
        self.save_database = save_database
        self.save_id = save_id
        self.current_date = appointment_date
        loaded_news = (
            self.save_database.list_daily_news(save_id)
            if save_id is not None
            else []
        )
        self.news_items = []
        for news in loaded_news:
            item = dict(news)
            item["session_key"] = self._news_key(
                item["news_date"], item["headline"]
            )
            self.news_items.append(item)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)

        header = QHBoxLayout()
        title = QLabel("📅 일자별 소식")
        title.setFont(QFont("Noto Sans KR", 26, QFont.Bold))
        header.addWidget(title)
        header.addStretch()
        self.read_all_button = QPushButton("모두 확인")
        self.read_all_button.clicked.connect(self.mark_all_read)
        header.addWidget(self.read_all_button)
        layout.addLayout(header)
        self.date_label = QLabel()
        self.date_label.setStyleSheet(
            f"color: {colors['accent_light']}; font-size: 16px; font-weight: 700;"
        )
        layout.addWidget(self.date_label)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        layout.addWidget(self.scroll, 1)
        self.set_game_date(appointment_date)

    def set_game_date(self, game_date):
        self.current_date = game_date
        self._merge_persisted_news()
        weekdays = "월화수목금토일"
        self.date_label.setText(
            f"{game_date.year}년 {game_date.month}월 {game_date.day}일 "
            f"{weekdays[game_date.weekday()]}요일"
        )

        self._ensure_date_news(game_date)
        self.refresh_news()

    def _merge_persisted_news(self):
        if self.save_id is None:
            return
        known = {news["session_key"] for news in self.news_items}
        for stored in self.save_database.list_daily_news(self.save_id):
            item = dict(stored)
            key = self._news_key(item["news_date"], item["headline"])
            if key in known:
                continue
            item["session_key"] = key
            self.news_items.append(item)
            known.add(key)

    def _ensure_date_news(self, game_date):
        date_text = game_date.isoformat()
        day_number = (game_date - self.appointment_date).days + 1
        if day_number == 1:
            self._add_session_news(
                date_text,
                "오늘의 주요 소식",
                f"반갑습니다, {self.manager_name} 감독님",
                f"{self.club_name}에서의 첫 업무가 시작됐습니다. "
                "프런트 브리핑과 선수단 현황을 확인하세요.",
            )
        else:
            self._add_session_news(
                date_text,
                "구단 운영",
                f"{self.manager_name} 감독 부임 {day_number}일차",
                "오늘 접수된 구단 보고와 선수단 변화를 확인할 수 있습니다.",
            )

        self._add_session_news(
            date_text,
            "오늘의 업무",
            self._camp_headline(game_date),
            self._camp_body(game_date),
        )

    def _add_session_news(self, news_date, category, headline, body):
        news_key = self._news_key(news_date, headline)
        if any(news["session_key"] == news_key for news in self.news_items):
            return
        self.news_items.append(
            {
                "session_key": news_key,
                "news_date": news_date,
                "category": category,
                "headline": headline,
                "body": body,
                "is_read": 0,
            }
        )

    def refresh_news(self):
        content = QWidget()
        content.setStyleSheet("background: transparent;")
        cards = QVBoxLayout(content)
        cards.setContentsMargins(0, 4, 6, 4)
        cards.setSpacing(12)
        news_items = sorted(
            self.news_items,
            key=lambda news: (news["news_date"], news["session_key"]),
            reverse=True,
        )
        for news in news_items:
            cards.addWidget(DailyNewsCard(news, self.colors, self.mark_read))
        if not news_items:
            empty = QLabel("아직 누적된 소식이 없습니다.")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setStyleSheet("color: #64748b; padding: 40px;")
            cards.addWidget(empty)
        cards.addStretch()
        self.scroll.setWidget(content)
        unread = sum(not bool(news["is_read"]) for news in self.news_items)
        self.read_all_button.setEnabled(unread > 0)
        self.unread_count_changed.emit(unread)

    def mark_read(self, news_key):
        for news in self.news_items:
            if news["session_key"] == news_key:
                news["is_read"] = 1
                break
        self.refresh_news()

    def mark_all_read(self):
        for news in self.news_items:
            news["is_read"] = 1
        self.refresh_news()

    def persist(self, save_id):
        """게임 저장 버튼을 눌렀을 때만 누적 소식을 DB에 반영한다."""
        self.save_id = save_id
        self.save_database.sync_daily_news(save_id, self.news_items)

    @staticmethod
    def _news_key(news_date, headline):
        return f"{news_date}|{headline}"

    @staticmethod
    def _camp_headline(game_date):
        if (game_date.month, game_date.day) < (11, 27):
            return "CAMP1 훈련 계획과 선수단 상태 점검"
        if (game_date.month, game_date.day) < (12, 15):
            return "CAMP1 평가 정리와 CAMP2 준비"
        return "CAMP2 실전 운영과 개막 엔트리 경쟁"

    @staticmethod
    def _camp_body(game_date):
        if (game_date.month, game_date.day) < (11, 27):
            return "훈련 강도, 포지션별 과제와 선수 컨디션을 확인할 시점입니다."
        if (game_date.month, game_date.day) < (12, 15):
            return "1차 캠프 결과를 검토하고 2차 캠프 참가 선수와 실전 계획을 준비하세요."
        return "연습경기와 라인업 경쟁을 통해 개막 엔트리의 윤곽을 확정하세요."
