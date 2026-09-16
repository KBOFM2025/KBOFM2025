"""First-run setup and login dialog for debug mode."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout,
)


class DebugLoginDialog(QDialog):
    def __init__(self, auth_service, parent=None):
        super().__init__(parent)
        self.auth_service = auth_service
        self.setup_mode = not auth_service.is_configured()
        self.setWindowTitle("DEBUG 관리자 설정" if self.setup_mode else "DEBUG 관리자 로그인")
        self.setModal(True)
        self.setFixedWidth(460)
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 22)
        root.setSpacing(10)

        card = QFrame(objectName="LoginCard")
        box = QVBoxLayout(card)
        box.setContentsMargins(22, 20, 22, 20)
        eyebrow = QLabel("PRIVILEGED QA ACCESS", objectName="LoginEyebrow")
        box.addWidget(eyebrow)
        box.addWidget(QLabel(
            "디버그 관리자 최초 설정" if self.setup_mode else "디버그 관리자 로그인",
            objectName="LoginTitle",
        ))
        description = QLabel(
            "처음 한 번 사용할 관리자 ID와 비밀번호를 설정합니다. 비밀번호는 복구할 수 없는 해시로 저장됩니다."
            if self.setup_mode else
            "이벤트 강제 생성과 전용 QA 세이브에 접근하려면 관리자 인증이 필요합니다.",
            objectName="LoginMuted",
        )
        description.setWordWrap(True)
        box.addWidget(description)

        box.addWidget(QLabel("관리자 ID", objectName="FieldLabel"))
        self.username = QLineEdit()
        self.username.setPlaceholderText("4자 이상")
        if self.setup_mode:
            self.username.setText("debug_admin")
        box.addWidget(self.username)

        box.addWidget(QLabel("비밀번호", objectName="FieldLabel"))
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.password.setPlaceholderText("문자와 숫자를 포함한 8자 이상")
        self.password.returnPressed.connect(self._submit)
        box.addWidget(self.password)

        self.confirm_label = QLabel("비밀번호 확인", objectName="FieldLabel")
        self.confirmation = QLineEdit()
        self.confirmation.setEchoMode(QLineEdit.EchoMode.Password)
        self.confirmation.setPlaceholderText("비밀번호를 다시 입력")
        self.confirmation.returnPressed.connect(self._submit)
        self.confirm_label.setVisible(self.setup_mode)
        self.confirmation.setVisible(self.setup_mode)
        box.addWidget(self.confirm_label)
        box.addWidget(self.confirmation)

        self.message = QLabel(objectName="LoginMessage")
        self.message.setWordWrap(True)
        box.addWidget(self.message)
        root.addWidget(card)

        buttons = QHBoxLayout()
        cancel = QPushButton("취소", objectName="CancelButton")
        cancel.clicked.connect(self.reject)
        buttons.addWidget(cancel)
        buttons.addStretch()
        submit = QPushButton(
            "계정 설정" if self.setup_mode else "로그인",
            objectName="LoginButton",
        )
        submit.clicked.connect(self._submit)
        buttons.addWidget(submit)
        root.addLayout(buttons)
        self.setStyleSheet(self._style())
        self.password.setFocus(Qt.FocusReason.ActiveWindowFocusReason)

    def _submit(self):
        try:
            if self.setup_mode:
                self.auth_service.register(
                    self.username.text(), self.password.text(), self.confirmation.text()
                )
                self.accept()
                return
            success, message = self.auth_service.authenticate(
                self.username.text(), self.password.text()
            )
            if success:
                self.accept()
                return
            self.message.setText(message)
            self.password.clear()
            self.password.setFocus()
        except ValueError as error:
            self.message.setText(str(error))

    @staticmethod
    def _style():
        return """
            QDialog { background:#0d1217; color:#e8eef3; font-family:'Malgun Gothic','Segoe UI'; }
            QFrame#LoginCard { background:#151c22; border:1px solid #3f4d58; border-radius:9px; }
            QLabel#LoginEyebrow { color:#ffb74d; font-size:13px; font-weight:900; }
            QLabel#LoginTitle { color:white; font-size:20px; font-weight:900; }
            QLabel#LoginMuted { color:#97a5af; font-size:13px; }
            QLabel#FieldLabel { color:#bcc8cf; font-size:13px; margin-top:6px; }
            QLabel#LoginMessage { color:#ff8a80; min-height:24px; }
            QLineEdit { color:white; background:#0c1217; border:1px solid #485966; border-radius:5px; min-height:32px; padding:3px 9px; }
            QLineEdit:focus { border:1px solid #ffb74d; }
            QPushButton#LoginButton { color:#16100a; background:#ffb74d; border:1px solid #ffd180; border-radius:6px; min-width:110px; min-height:34px; font-weight:900; }
            QPushButton#CancelButton { color:#d6e0e6; background:#253039; border:1px solid #4a5a66; border-radius:6px; min-width:80px; min-height:34px; }
        """

