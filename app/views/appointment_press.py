"""기자회견장 장면 위에서 진행하는 FM 스타일 취임 기자회견 화면."""

import textwrap

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton,
    QSizePolicy, QVBoxLayout, QWidget,
)

from app.utils import resource_path
from app.views.player_meeting import MeetingBackdrop


REGIONAL_PRESS = {
    "KIA 타이거즈": ("광주일보", "박소영"),
    "삼성 라이온즈": ("매일신문", "김도윤"),
    "LG 트윈스": ("서울신문", "이서준"),
    "두산 베어스": ("서울신문", "최민아"),
    "KT 위즈": ("경기일보", "정우진"),
    "SSG 랜더스": ("인천일보", "한지수"),
    "롯데 자이언츠": ("부산일보", "윤태호"),
    "한화 이글스": ("대전일보", "오세진"),
    "NC 다이노스": ("경남신문", "문채원"),
    "키움 히어로즈": ("서울경제", "장현수"),
}


def _answer(label, text, tone, board=0, fans=0, squad=0, media=0):
    return {
        "label": label, "text": text, "tone": tone,
        "effects": {"board": board, "fans": fans, "squad": squad, "media": media},
    }


def interview_questions(team, club_name, manager_name, season_goal):
    regional_outlet, regional_name = REGIONAL_PRESS.get(team, ("지역 스포츠", "김기자"))
    return (
        {
            "outlet": regional_outlet, "reporter": regional_name, "beat": "연고지·팬",
            "question": f"{manager_name} 감독님, {club_name} 팬들에게 가장 먼저 어떤 팀을 약속하시겠습니까?",
            "answers": (
                _answer("승리 약속", "결과로 증명하겠습니다. 팬들이 자부심을 느낄 수 있는 강한 팀을 만들겠습니다.", "야심", board=2, fans=3, squad=-1, media=1),
                _answer("지역과 함께", "연고지 팬들과 호흡하며 매 경기 포기하지 않는 팀을 만들겠습니다.", "진정성", fans=4, squad=1, media=1),
                _answer("과정부터", "기본기와 공정한 경쟁부터 바로 세워 오래 강한 팀을 만들겠습니다.", "신중", board=1, fans=1, squad=2),
                _answer("말보다 행동", "지금 큰 약속을 드리기보다 그라운드에서 달라진 모습을 보여드리겠습니다.", "절제", board=-1, fans=-1, squad=1, media=-1),
            ),
        },
        {
            "outlet": "KBS", "reporter": "이재훈", "beat": "시즌 목표",
            "question": f"구단은 ‘{season_goal}’을 목표로 제시했습니다. 감독님도 같은 수준의 성과가 가능하다고 보십니까?",
            "answers": (
                _answer("목표 수용", "구단이 제시한 목표를 받아들입니다. 책임을 피하지 않고 반드시 도전하겠습니다.", "책임", board=4, fans=2, squad=-1, media=2),
                _answer("우승 도전", "목표를 제한하고 싶지 않습니다. 마지막 경기까지 우승 가능성을 열어두겠습니다.", "공격", board=2, fans=4, squad=-2, media=3),
                _answer("단계적 접근", "현재 전력을 냉정하게 평가한 뒤 월별 목표를 달성하며 순위를 끌어올리겠습니다.", "현실", board=2, fans=1, squad=2, media=1),
                _answer("답변 유보", "선수단을 직접 확인하기 전 구체적인 순위를 약속하는 것은 적절하지 않습니다.", "유보", board=-3, fans=-2, squad=1, media=-2),
            ),
        },
        {
            "outlet": "MBC", "reporter": "김수현", "beat": "선수 기용",
            "question": "베테랑과 유망주의 출전 기회를 어떤 기준으로 배분하실 생각입니까?",
            "answers": (
                _answer("완전 경쟁", "이름과 나이를 보지 않겠습니다. 훈련과 경기에서 가장 준비된 선수가 출전합니다.", "원칙", board=1, fans=2, squad=3, media=2),
                _answer("베테랑 중심", "중요한 순간에는 경험이 필요합니다. 검증된 주축을 중심으로 안정적으로 운영하겠습니다.", "안정", board=2, fans=0, squad=-1, media=0),
                _answer("유망주 기회", "젊은 선수에게 실패할 권리까지 주겠습니다. 미래의 주축을 적극적으로 키우겠습니다.", "육성", board=1, fans=3, squad=2, media=2),
                _answer("상황별 기용", "상대와 컨디션, 경기 흐름에 따라 가장 적합한 선수를 선택하겠습니다.", "유연", board=2, fans=1, squad=2, media=1),
            ),
        },
        {
            "outlet": "SBS", "reporter": "박지민", "beat": "야구 철학",
            "question": "감독님의 야구를 한 문장으로 정의한다면 무엇이며, 경기 운영에서 무엇이 가장 달라집니까?",
            "answers": (
                _answer("공격적인 야구", "먼저 움직이고 한 베이스를 더 노리겠습니다. 상대가 편하게 경기하도록 두지 않겠습니다.", "공격", fans=3, squad=1, media=3),
                _answer("투수·수비", "실점을 통제하는 팀이 긴 시즌에서 살아남습니다. 수비와 마운드의 원칙부터 세우겠습니다.", "안정", board=2, fans=1, squad=2, media=1),
                _answer("데이터 야구", "감이 아니라 근거로 결정하되, 마지막 판단과 책임은 감독인 제가 지겠습니다.", "분석", board=2, fans=1, squad=1, media=3),
                _answer("선수 중심", "선수의 장점을 가장 편안하게 발휘시키는 것이 제 전술의 출발점입니다.", "소통", board=1, fans=2, squad=4, media=1),
            ),
        },
        {
            "outlet": "SPOTV", "reporter": "서정민", "beat": "전문 분석",
            "question": "부진과 연패가 찾아왔을 때 라인업과 투수 운용 원칙을 얼마나 빠르게 바꾸시겠습니까?",
            "answers": (
                _answer("빠른 변화", "명확한 문제라면 지체하지 않겠습니다. 엔트리와 보직을 과감하게 조정하겠습니다.", "결단", board=2, fans=2, squad=-1, media=3),
                _answer("주축 신뢰", "짧은 결과에 흔들리지 않겠습니다. 충분한 근거가 생길 때까지 주축 선수에게 시간을 주겠습니다.", "신뢰", board=1, fans=0, squad=3, media=1),
                _answer("데이터 검증", "표면적인 결과와 경기 내용을 분리해 분석하고 변화의 비용까지 확인한 뒤 결정하겠습니다.", "분석", board=2, fans=1, squad=1, media=3),
                _answer("코칭스태프 협의", "혼자 결론 내리지 않고 파트별 코치와 선수 의견을 들은 뒤 최종 결정을 내리겠습니다.", "협업", board=1, fans=1, squad=3, media=1),
            ),
        },
    )


class AppointmentPressConferencePage(QWidget):
    completed = Signal(list, dict, str)

    def __init__(self, team, club_name, manager_data, team_info, colors, parent=None):
        super().__init__(parent)
        self.team = team
        self.club_name = club_name
        self.manager_name = manager_data.get("manager_name", "감독")
        self.colors = colors
        self.questions = interview_questions(
            team, club_name, self.manager_name, team_info.get("season_goal", "상위권 도약")
        )
        self.index = 0
        self.answers = []
        self.scores = {"board": 70, "fans": 70, "squad": 70, "media": 70}
        self.reporter_cards = []
        self.answer_buttons = []
        self._build()
        self._show_question()

    def _build(self):
        self.setObjectName("PressPage")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.scene = MeetingBackdrop(
            resource_path("image", "Scenes", "press_conference_room.png")
        )
        outer.addWidget(self.scene)
        page = QVBoxLayout(self.scene)
        page.setContentsMargins(16, 12, 16, 14)
        page.setSpacing(10)

        top_bar = QFrame()
        top_bar.setObjectName("TopBar")
        top = QHBoxLayout(top_bar)
        top.setContentsMargins(15, 8, 15, 8)
        title_box = QVBoxLayout()
        title_box.setSpacing(1)
        kicker = QLabel("기자회견  ·  APPOINTMENT PRESS CONFERENCE")
        kicker.setObjectName("Kicker")
        title_box.addWidget(kicker)
        title = QLabel(f"{self.club_name}  |  {self.manager_name} 감독")
        title.setObjectName("Title")
        title_box.addWidget(title)
        top.addLayout(title_box)
        top.addStretch()
        mood_box = QVBoxLayout()
        mood_box.setSpacing(0)
        mood_title = QLabel("현재 기자회견 분위기")
        mood_title.setObjectName("MoodTitle")
        mood_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mood_box.addWidget(mood_title)
        self.mood_label = QLabel("차분함")
        self.mood_label.setObjectName("Mood")
        self.mood_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mood_box.addWidget(self.mood_label)
        top.addLayout(mood_box)
        top.addStretch()
        self.progress = QLabel()
        self.progress.setObjectName("Progress")
        top.addWidget(self.progress)
        page.addWidget(top_bar)

        reporter_panel = QFrame()
        reporter_panel.setObjectName("ReporterPanel")
        reporters = QHBoxLayout(reporter_panel)
        reporters.setContentsMargins(8, 7, 8, 7)
        reporters.setSpacing(7)
        for question in self.questions:
            card = QLabel()
            card.setWordWrap(True)
            card.setAlignment(
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
            )
            card.setProperty("reporter", True)
            card.setMinimumHeight(66)
            card.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
            )
            reporters.addWidget(card)
            self.reporter_cards.append(card)
        page.addWidget(reporter_panel)

        question_row = QHBoxLayout()
        question_row.addStretch(2)
        question_box = QFrame()
        question_box.setObjectName("QuestionBox")
        question_box.setMinimumWidth(360)
        question_box.setMaximumWidth(980)
        stage_layout = QVBoxLayout(question_box)
        stage_layout.setContentsMargins(20, 13, 20, 15)
        stage_layout.setSpacing(5)
        self.outlet_label = QLabel()
        self.outlet_label.setObjectName("Outlet")
        stage_layout.addWidget(self.outlet_label)
        self.question_label = QLabel()
        self.question_label.setObjectName("Question")
        self.question_label.setWordWrap(True)
        stage_layout.addWidget(self.question_label)
        question_row.addWidget(question_box, 7)
        question_row.addStretch(2)
        page.addLayout(question_row)
        page.addStretch(1)

        answer_panel = QFrame()
        answer_panel.setObjectName("AnswerPanel")
        answers_layout = QVBoxLayout(answer_panel)
        answers_layout.setContentsMargins(12, 10, 12, 11)
        answers_layout.setSpacing(7)
        answer_header = QHBoxLayout()
        choice_title = QLabel("감독 답변 선택")
        choice_title.setObjectName("ChoiceTitle")
        answer_header.addWidget(choice_title)
        self.tone_label = QLabel("답변의 어조에 따라 기자와 구단 관계자의 반응이 달라집니다.")
        self.tone_label.setObjectName("Tone")
        self.tone_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        answer_header.addWidget(self.tone_label, 1)
        self.finish_button = QPushButton("기자회견 종료  →")
        self.finish_button.setObjectName("Finish")
        self.finish_button.setVisible(False)
        self.finish_button.clicked.connect(self._finish)
        answer_header.addWidget(self.finish_button)
        answers_layout.addLayout(answer_header)
        self.choice_grid = QGridLayout()
        self.choice_grid.setHorizontalSpacing(8)
        self.choice_grid.setVerticalSpacing(8)
        answers_layout.addLayout(self.choice_grid)
        page.addWidget(answer_panel)
        self._apply_style()

    @staticmethod
    def _label(text, object_name):
        label = QLabel(text)
        label.setObjectName(object_name)
        return label

    def _show_question(self):
        question = self.questions[self.index]
        self.progress.setText(
            f"공식 질의  {self.index + 1} / {len(self.questions)}"
        )
        self.outlet_label.setText(
            f"{question['outlet']}  ·  {question['reporter']} 기자  |  "
            f"담당: {question['beat']}"
        )
        self.question_label.setText(f"“{question['question']}”")
        for i, card in enumerate(self.reporter_cards):
            reporter = self.questions[i]
            if i < len(self.answers):
                status = f"답변 완료  ·  {self.answers[i]['tone']}"
            elif i == self.index:
                status = "현재 질문"
            else:
                status = "질문 대기"
            card.setText(
                f"{reporter['reporter']} 기자  ·  {reporter['outlet']}\n"
                f"{reporter['beat']}  |  {status}"
            )
            card.setProperty("active", i == self.index)
            card.setProperty("done", i < self.index)
            card.style().unpolish(card)
            card.style().polish(card)
        while self.choice_grid.count():
            item = self.choice_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.answer_buttons.clear()
        for index, answer in enumerate(question["answers"]):
            wrapped = "\n".join(textwrap.wrap(answer["text"], width=24))
            button = QPushButton(
                f"{answer['tone']}  ·  {answer['label']}\n{wrapped}"
            )
            button.setProperty("answer", True)
            button.setProperty("choice", index + 1)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setMinimumHeight(118)
            button.clicked.connect(
                lambda _checked=False, selected=index: self._choose(selected)
            )
            self.answer_buttons.append(button)
        self._relayout_answer_buttons()
        self._refresh_scores()

    def _relayout_answer_buttons(self):
        """창 폭에 따라 답변을 4열 또는 2열로 재배치한다."""
        while self.choice_grid.count():
            self.choice_grid.takeAt(0)
        columns = 4 if self.width() >= 1180 else 2
        for column in range(4):
            self.choice_grid.setColumnStretch(column, 0)
        for index, button in enumerate(self.answer_buttons):
            self.choice_grid.addWidget(
                button, index // columns, index % columns
            )
        for column in range(columns):
            self.choice_grid.setColumnStretch(column, 1)

    def resizeEvent(self, event):
        if self.answer_buttons:
            self._relayout_answer_buttons()
        super().resizeEvent(event)

    def _choose(self, answer_index):
        question = self.questions[self.index]
        answer = question["answers"][answer_index]
        record = {
            "outlet": question["outlet"], "reporter": question["reporter"],
            "question": question["question"], "answer": answer["text"],
            "tone": answer["tone"], "effects": dict(answer["effects"]),
        }
        self.answers.append(record)
        for key, delta in answer["effects"].items():
            self.scores[key] = max(0, min(100, self.scores[key] + delta))
        self.tone_label.setText(f"{answer['tone']} · {question['outlet']}은 답변의 핵심 표현을 속보 기사에 반영했습니다.")
        self.index += 1
        if self.index < len(self.questions):
            self._show_question()
            return
        for i, card in enumerate(self.reporter_cards):
            reporter = self.questions[i]
            card.setText(
                f"{reporter['reporter']} 기자  ·  {reporter['outlet']}\n"
                f"{reporter['beat']}  |  답변 완료 · {self.answers[i]['tone']}"
            )
            card.setProperty("active", False)
            card.setProperty("done", True)
            card.style().unpolish(card)
            card.style().polish(card)
        self.progress.setText("공식 질의  완료")
        self.outlet_label.setText("구단 홍보팀  ·  기자회견 종료 안내")
        self.question_label.setText(
            "모든 공식 질문에 답했습니다. 각 매체가 기사를 송고하고 있으며, "
            "답변 내용은 구단 뉴스와 내부 관계도에 반영됩니다."
        )
        while self.choice_grid.count():
            item = self.choice_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.finish_button.setVisible(True)
        self.tone_label.setText("공식 질의가 모두 끝났습니다. 기자회견을 종료할 수 있습니다.")
        self._refresh_scores()

    def _refresh_scores(self):
        media = self.scores["media"]
        average = sum(self.scores.values()) / len(self.scores)
        if media >= 78 and average >= 74:
            mood = "매우 긍정적"
        elif media >= 72 and average >= 70:
            mood = "긍정적"
        elif media <= 63 or average <= 65:
            mood = "긴장됨"
        else:
            mood = "차분함"
        self.mood_label.setText(mood)

    def _finish(self):
        strongest = max(self.scores, key=self.scores.get)
        labels = {"board": "이사회 신뢰", "fans": "팬 기대", "squad": "선수단 반응", "media": "언론 평가"}
        summary = f"첫 기자회견은 {labels[strongest]}에서 가장 긍정적인 반응을 얻었습니다."
        self.finish_button.setEnabled(False)
        self.completed.emit(list(self.answers), dict(self.scores), summary)

    def _apply_style(self):
        c = self.colors
        self.setStyleSheet(f"""
            QWidget#PressPage {{ background: #080b0e; }}
            QLabel {{ color: #dfe7ee; font-family: 'Malgun Gothic', 'Segoe UI'; }}
            QFrame#TopBar {{ background: rgba(10, 13, 16, 238); border: 1px solid rgba(91, 101, 110, 170); }}
            QLabel#Kicker {{ color: #9aa5ae; font-size: 9px; font-weight: 700; }}
            QLabel#Title {{ color: white; font-size: 15px; font-weight: 900; }}
            QLabel#MoodTitle {{ color: #8b959d; font-size: 8px; }}
            QLabel#Mood {{ color: white; background: rgba(108, 110, 108, 205); border-radius: 13px; padding: 5px 50px; font-size: 11px; font-weight: 800; }}
            QLabel#Progress {{ color: #d9e3ec; background: rgba(20, 25, 30, 220); border: 1px solid #45515c; padding: 8px 13px; font-size: 10px; font-weight: 800; }}
            QFrame#ReporterPanel {{ background: rgba(10, 13, 16, 176); border: 1px solid rgba(74, 82, 89, 145); }}
            QLabel[reporter="true"] {{ color: #9aa3aa; background: rgba(32, 35, 37, 205); border: 1px solid rgba(82, 88, 91, 180); border-radius: 3px; padding: 8px 10px; font-size: 10px; }}
            QLabel[reporter="true"][active="true"] {{ color: white; background: rgba(87, 91, 76, 225); border: 1px solid {c['accent_light']}; font-weight: 800; }}
            QLabel[reporter="true"][done="true"] {{ color: #a7c2ad; background: rgba(35, 55, 43, 215); border-color: #537a5e; }}
            QFrame#QuestionBox {{ background: rgba(23, 25, 27, 235); border: 1px solid rgba(101, 106, 109, 210); border-radius: 3px; }}
            QLabel#Outlet {{ color: {c['accent_light']}; font-size: 10px; font-weight: 900; }}
            QLabel#Question {{ color: white; font-size: 17px; font-weight: 800; }}
            QFrame#AnswerPanel {{ background: rgba(24, 25, 27, 242); border: 1px solid rgba(83, 87, 90, 210); border-radius: 5px; }}
            QLabel#ChoiceTitle {{ color: white; font-size: 12px; font-weight: 900; }}
            QLabel#Tone {{ color: #aab2b9; font-size: 10px; }}
            QPushButton[answer="true"] {{ color: #e7e9eb; background: rgba(45, 46, 48, 242); border: 1px solid #424548; border-top: 3px solid #707477; border-radius: 3px; padding: 10px 12px; text-align: left; font-size: 10px; font-weight: 600; }}
            QPushButton[answer="true"][choice="1"] {{ border-top-color: #5fa66f; }}
            QPushButton[answer="true"][choice="2"] {{ border-top-color: #80906a; }}
            QPushButton[answer="true"][choice="3"] {{ border-top-color: #c79c4a; }}
            QPushButton[answer="true"][choice="4"] {{ border-top-color: #a35b5b; }}
            QPushButton[answer="true"]:hover {{ color: white; background: rgba(63, 66, 69, 248); border: 1px solid {c['accent_light']}; border-top: 3px solid {c['accent_light']}; }}
            QPushButton#Finish {{ color: white; background: {c['accent']}; border: 1px solid {c['accent_light']}; padding: 9px 16px; font-size: 11px; font-weight: 800; }}
            QPushButton#Finish:hover {{ background: {c['accent_light']}; }}
        """)
