"""저장된 세부 코치 능력치를 표시하는 전체 페이지. 사진·경력은 추정 생성하지 않는다."""
from html import escape

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QFrame, QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
    QGridLayout, QScrollArea, QProgressBar,
)
from app.services.training import coaching_quality, COACH_DEPARTMENTS


ATTRIBUTE_GROUPS = (
    ("기술 지도", (("batting", "타격 지도"), ("pitching", "투수 지도"),
                  ("defense", "수비 지도"), ("baserunning", "주루 지도"),
                  ("catching", "포수 지도"), ("fitness", "체력 훈련"))),
    ("정신적 능력 · 선수 관리", (("mental", "선수 심리 지도"), ("motivation", "동기부여"),
                  ("discipline", "기강 유지"), ("man_management", "선수 관리"),
                  ("adaptability", "적응력"))),
    ("전술 · 육성 · 분석", (("tactical", "전술 지도"), ("youth_development", "유망주 육성"),
                  ("development", "성장 지도"), ("data_analysis", "데이터 분석"))),
)


class CoachProfilePage(QWidget):
    back_requested = Signal()

    def __init__(self, service, parent=None):
        super().__init__(parent)
        self.service = service
        self.coach_id = None
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 12, 0, 0)
        navigation = QHBoxLayout()
        back = QPushButton("← 코칭스태프 목록", objectName="SecondaryButton")
        back.clicked.connect(self.back_requested.emit)
        navigation.addWidget(back)
        navigation.addStretch()
        navigation.addWidget(QLabel("STAFF PROFILE  /  능력치", objectName="SectionEyebrow"))
        root.addLayout(navigation)
        scroll = QScrollArea(objectName="DashboardScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget(objectName="DashboardContent")
        content.setMinimumWidth(900)
        scroll.setWidget(content)
        root.addWidget(scroll)
        grid = QGridLayout(content)
        grid.setContentsMargins(0, 8, 0, 0)
        grid.setSpacing(14)
        grid.setColumnStretch(0, 2)
        grid.setColumnStretch(1, 3)
        grid.setColumnStretch(2, 3)
        grid.setColumnStretch(3, 2)

        def panel(title):
            frame = QFrame(objectName="DashboardCard")
            box = QVBoxLayout(frame)
            box.setContentsMargins(18, 18, 18, 18)
            box.setSpacing(12)
            box.addWidget(QLabel(title, objectName="SectionTitle"))
            return frame, box

        identity, box = panel("코치 프로필")
        self.avatar = QLabel("STAFF", objectName="CoachAvatar")
        self.avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.avatar.setMinimumHeight(160)
        box.addWidget(self.avatar)
        self.name = QLabel(objectName="DashboardValue")
        self.name.setWordWrap(True)
        box.addWidget(self.name)
        self.identity = QLabel(objectName="DashboardReport")
        self.identity.setWordWrap(True)
        box.addWidget(self.identity)
        self.contract = QLabel(objectName="DashboardReport")
        self.contract.setWordWrap(True)
        box.addWidget(self.contract)
        box.addStretch()
        photo_note = QLabel("사진 미등록\n임의의 인물 사진은 사용하지 않습니다.", objectName="TrainingMuted")
        photo_note.setWordWrap(True)
        box.addWidget(photo_note)
        grid.addWidget(identity, 0, 0, 2, 1)
        self.rating_labels = {}
        for index, (title, fields) in enumerate(ATTRIBUTE_GROUPS):
            frame, box = panel(title)
            ratings = QGridLayout()
            ratings.setContentsMargins(0, 0, 0, 0)
            ratings.setHorizontalSpacing(14)
            ratings.setVerticalSpacing(0)
            ratings.setColumnStretch(0, 1)
            for row, (key, label) in enumerate(fields):
                text = QLabel(label, objectName="CoachAttributeName")
                text.setMinimumHeight(40)
                text.setWordWrap(True)
                value = QLabel("—", objectName="CoachAttributeValue")
                value.setFixedWidth(36)
                value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.rating_labels[key] = value
                ratings.addWidget(text, row, 0)
                ratings.addWidget(value, row, 1)
            box.addLayout(ratings)
            box.addStretch()
            grid.addWidget(frame, 0 if index < 2 else 1, 1 if index != 1 else 2,
                           1, 1 if index < 2 else 2)
        fit, box = panel("담당 분야별 품질")
        self.workload = QLabel(objectName="TrainingMuted")
        self.workload.setWordWrap(True)
        box.addWidget(self.workload)
        self.quality_bars = {}
        for focus in COACH_DEPARTMENTS:
            box.addWidget(QLabel(focus, objectName="FieldLabel"))
            bar = QProgressBar(objectName="CoachQuality")
            bar.setRange(0, 200)
            bar.setMinimumHeight(22)
            self.quality_bars[focus] = bar
            box.addWidget(bar)
        box.addStretch()
        grid.addWidget(fit, 0, 3, 2, 1)
        self.source = QLabel(objectName="TrainingMuted")
        self.source.setWordWrap(True)
        self.source.setOpenExternalLinks(True)
        grid.addWidget(self.source, 2, 0, 1, 4)
        grid.setRowStretch(3, 1)

    def set_coach(self, coach_id):
        coach = self.service.coach(int(coach_id))
        if not coach:
            return False
        self.coach_id = int(coach_id)
        self.name.setText(coach["name"])
        self.avatar.setText(coach["name"][:1])
        self.identity.setText(f"{coach['team'] or '영입 후보'}\n{coach['squad']} · {coach['role']}\n\n"
                              f"전문 분야  {coach['specialty']}\n지도 성향  {coach['coaching_style']}\n성격  {coach['personality']}")
        self.contract.setText(f"{'요구 연봉' if coach['status'] == 'candidate' else '연봉'}  {coach['salary_10k']:,}만원\n"
                              f"계약 종료  {coach['contract_end'] or '미계약'}")
        for key, label in self.rating_labels.items():
            raw = coach.get(key)
            label.setText(str(raw) if raw is not None else "—")
            level = "elite" if raw is not None and raw >= 16 else "good" if raw is not None and raw >= 11 else "low"
            label.setProperty("level", level)
            label.style().unpolish(label)
            label.style().polish(label)
        with self.service._connect() as connection:
            load = connection.execute("SELECT COALESCE(SUM(workload),0) FROM coach_assignments WHERE save_id=? AND coach_id=?",
                                      (self.service.save_id, coach_id)).fetchone()[0]
        self.workload.setText(f"배정 업무량 {load}\n전문 능력·동기부여·기강 유지와 업무량을 반영한 분야별 계산값입니다.")
        for focus, bar in self.quality_bars.items():
            quality = coaching_quality(coach, focus, load)
            bar.setValue(round(quality * 10))
            bar.setFormat(f"{quality:.1f} / 20")
        source_url = coach.get("source_url") or ""
        link = f' · <a style="color:#69cfff" href="{escape(source_url, quote=True)}">명단 출처 ↗</a>' if source_url.startswith(("https://", "http://")) else ""
        self.source.setText("능력치 1–20 · 녹색 16 이상 / 노란색 11–15 / 회색 10 이하<br>"
                            "능력치는 게임 추정치이며 실제 인물의 공식 평가가 아닙니다. 세부 능력은 저장된 값 그대로 표시합니다.<br>"
                            "정신·분석 항목 모두가 독립적인 시뮬레이션 효과를 갖는 것은 아닙니다. 오른쪽 품질은 현재 훈련 계산식과 같습니다." + link)
        return True
