"""전체 뉴스와 현재 날짜의 구단 브리핑 화면."""

from datetime import timedelta

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QFrame,
    QButtonGroup,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QSplitter,
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
        headline_label.setFont(QFont("Malgun Gothic", 19, QFont.Bold))
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
            QLabel {{ color: {colors['text']}; font-family: 'Malgun Gothic', 'Segoe UI'; }}
        """)


class NewsFeedPage(QWidget):
    """게임에 누적되는 전체 구단·리그 뉴스 피드."""

    notification_count_changed = Signal(int)
    second_draft_requested = Signal(str)

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
        layout.setContentsMargins(7, 6, 7, 7)
        layout.setSpacing(6)

        header = QHBoxLayout()
        title = QLabel("KBO 뉴스 센터")
        title.setFont(QFont("Malgun Gothic", 18, QFont.Bold))
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
        subtitle.setStyleSheet("color: #8f9ba7; font-size: 11px;")
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

        self.news_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.news_list = QListWidget()
        self.news_list.setObjectName("NewsList")
        self.news_list.setMinimumWidth(310)
        self.news_list.setMaximumWidth(470)
        self.news_list.currentRowChanged.connect(self._show_article)
        self.news_splitter.addWidget(self.news_list)

        detail = QFrame()
        detail.setObjectName("NewsDetail")
        detail_layout = QVBoxLayout(detail)
        detail_layout.setContentsMargins(16, 13, 16, 16)
        detail_layout.setSpacing(8)
        detail_meta = QHBoxLayout()
        self.detail_category = QLabel("뉴스")
        self.detail_category.setObjectName("NewsDetailCategory")
        detail_meta.addWidget(self.detail_category)
        detail_meta.addStretch()
        self.detail_date = QLabel()
        self.detail_date.setObjectName("NewsDetailDate")
        detail_meta.addWidget(self.detail_date)
        detail_layout.addLayout(detail_meta)
        self.detail_headline = QLabel("기사를 선택하세요")
        self.detail_headline.setObjectName("NewsDetailHeadline")
        self.detail_headline.setWordWrap(True)
        detail_layout.addWidget(self.detail_headline)
        self.detail_body = QLabel("왼쪽 목록에서 확인할 소식을 선택할 수 있습니다.")
        self.detail_body.setObjectName("NewsDetailBody")
        self.detail_body.setWordWrap(True)
        self.detail_body.setAlignment(Qt.AlignmentFlag.AlignTop)
        detail_layout.addWidget(self.detail_body, 1)
        detail_actions = QHBoxLayout()
        detail_actions.addStretch()
        self.detail_action_button = QPushButton()
        self.detail_action_button.setObjectName("NewsArticleAction")
        self.detail_action_button.setVisible(False)
        self.detail_action_button.clicked.connect(
            self._activate_selected_article
        )
        detail_actions.addWidget(self.detail_action_button)
        detail_layout.addLayout(detail_actions)
        self.news_splitter.addWidget(detail)
        self.news_splitter.setStretchFactor(0, 0)
        self.news_splitter.setStretchFactor(1, 1)
        self.news_splitter.setSizes([380, 900])
        layout.addWidget(self.news_splitter, 1)
        self.setStyleSheet(f"""
            QPushButton#NewsFilter {{ color: #aab7c5; background: #171e26; border: 1px solid #384654; border-radius: 0; padding: 4px 13px; font-weight: 700; }}
            QPushButton#NewsFilter:hover, QPushButton#NewsFilter:checked {{ color: white; background: #252d36; border-bottom: 2px solid {colors['accent_light']}; }}
            QPushButton#NewsReadAll {{ color: white; background: {colors['accent']}; border: 1px solid {colors['accent_light']}; border-radius: 0; padding: 4px 12px; font-weight: 700; }}
            QPushButton#NewsArticleAction {{ color: white; background: {colors['accent']}; border: 1px solid {colors['accent_light']}; border-radius: 0; padding: 8px 18px; font-weight: 800; }}
            QPushButton#NewsArticleAction:hover {{ background: {colors['accent_light']}; }}
            QListWidget#NewsList {{ color: #dce4ec; background: #151a20; border: 1px solid #39434e; outline: none; font-size: 12px; }}
            QListWidget#NewsList::item {{ min-height: 48px; padding: 7px 10px; border-bottom: 1px solid #303943; }}
            QListWidget#NewsList::item:hover {{ background: #202831; }}
            QListWidget#NewsList::item:selected {{ color: white; background: #252d36; border-left: 3px solid {colors['accent_light']}; }}
            QFrame#NewsDetail {{ background: #151a20; border: 1px solid #39434e; }}
            QLabel#NewsDetailCategory {{ color: {colors['accent_light']}; font-size: 11px; font-weight: 700; }}
            QLabel#NewsDetailDate {{ color: #7f8b97; font-size: 11px; }}
            QLabel#NewsDetailHeadline {{ color: white; border-top: 1px solid #39434e; padding-top: 11px; font-size: 20px; font-weight: 700; }}
            QLabel#NewsDetailBody {{ color: #c2ccd5; font-size: 13px; padding-top: 6px; }}
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
            if (
                item["category"] == "리그 시뮬레이션"
                and "10개 구단 하루 진행 완료" in item["headline"]
            ):
                continue
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
        self.visible_articles = articles
        self.news_list.blockSignals(True)
        self.news_list.clear()
        previous_date = None
        first_article_row = None
        for article_index, item in enumerate(articles):
            date_key = item["news_date"]
            if date_key != previous_date:
                header = QListWidgetItem(
                    self._news_date_group_title(date_key)
                )
                header.setFlags(Qt.ItemFlag.NoItemFlags)
                header.setForeground(QColor("#8f9dac"))
                header.setBackground(QColor("#0f1419"))
                header_font = header.font()
                header_font.setBold(True)
                header_font.setPointSize(10)
                header.setFont(header_font)
                header.setData(Qt.ItemDataRole.UserRole, None)
                self.news_list.addItem(header)
                previous_date = date_key
            row_item = QListWidgetItem(
                f"{item['category']}\n{item['headline']}"
            )
            row_item.setData(
                Qt.ItemDataRole.UserRole, article_index
            )
            self.news_list.addItem(row_item)
            if first_article_row is None:
                first_article_row = self.news_list.count() - 1
        self.news_list.blockSignals(False)
        if not articles:
            self.detail_category.setText("뉴스")
            self.detail_date.clear()
            self.detail_headline.setText("해당 조건의 뉴스가 없습니다")
            self.detail_body.setText("다른 분류를 선택해 확인하세요.")
            self.detail_action_button.setVisible(False)
        else:
            self.news_list.setCurrentRow(first_article_row)
            self._show_article(first_article_row)

    def _show_article(self, row):
        article_index = self._article_index_for_row(row)
        if article_index is None:
            return
        item = self.visible_articles[article_index]
        self.detail_category.setText(item["category"])
        self.detail_date.setText(item["news_date"].replace("-", "."))
        self.detail_headline.setText(item["headline"])
        self.detail_body.setText(item["body"])
        draft_view = self._second_draft_view(item)
        self.detail_action_button.setVisible(draft_view is not None)
        if draft_view == "results":
            self.detail_action_button.setText("2차 드래프트 결과 확인  ›")
        elif draft_view:
            self.detail_action_button.setText("지명 가능 명단 확인  ›")

    def _activate_selected_article(self):
        row = self.news_list.currentRow()
        article_index = self._article_index_for_row(row)
        if article_index is None:
            return
        item = self.visible_articles[article_index]
        draft_view = self._second_draft_view(item)
        if draft_view is None:
            return
        if (
            item.get("id") is not None
            and not item.get("is_read")
            and self.save_database
            and self.save_id is not None
        ):
            self.save_database.mark_daily_news_read(
                self.save_id, item["id"]
            )
            item["is_read"] = 1
            self.notification_count_changed.emit(
                self.save_database.unread_daily_news_count(self.save_id)
            )
        self.second_draft_requested.emit(draft_view)

    def _article_index_for_row(self, row):
        if row < 0:
            return None
        item = self.news_list.item(row)
        if item is None:
            return None
        value = item.data(Qt.ItemDataRole.UserRole)
        return int(value) if value is not None else None

    def _news_date_group_title(self, date_key):
        formatted = str(date_key).replace("-", ".")
        if self.current_date and self.current_date.isoformat() == date_key:
            return f"오늘  ·  {formatted}"
        if (
            self.current_date
            and (self.current_date - timedelta(days=1)).isoformat() == date_key
        ):
            return f"어제  ·  {formatted}"
        return formatted

    @staticmethod
    def _second_draft_view(item):
        headline = str(item.get("headline") or "")
        if headline.startswith("2차 드래프트 보호선수 및 지명 대상 명단 확정"):
            return "available"
        if headline.startswith("2025 KBO 2차 드래프트 종료"):
            return "results"
        return None

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
        headline.setFont(QFont("Malgun Gothic", 18, QFont.Bold))
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
            QLabel {{ color: {colors['text']}; font-family: 'Malgun Gothic', 'Segoe UI'; }}
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
        title.setFont(QFont("Malgun Gothic", 26, QFont.Bold))
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
            return "스토브리그 전력 분석과 선수단 상태 점검"
        if (game_date.month, game_date.day) < (12, 15):
            return "1차 캠프 평가 정리와 실전 캠프 준비"
        return "2차 캠프 실전 운영과 개막 엔트리 경쟁"

    @staticmethod
    def _camp_body(game_date):
        if (game_date.month, game_date.day) < (11, 27):
            return "훈련 강도, 포지션별 과제와 선수 컨디션을 확인할 시점입니다."
        if (game_date.month, game_date.day) < (12, 15):
            return "1차 캠프 결과를 검토하고 2차 캠프 참가 선수와 실전 계획을 준비하세요."
        return "연습경기와 라인업 경쟁을 통해 개막 엔트리의 윤곽을 확정하세요."
