"""공식 KBO CDN에서 내려받은 구단 로고 자산 접근."""

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon, QPixmap

from app.utils import resource_path


TEAM_LOGO_FILES = {
    "KIA 타이거즈": "kia.png", "삼성 라이온즈": "samsung.png",
    "LG 트윈스": "lg.png", "두산 베어스": "doosan.png",
    "KT 위즈": "kt.png", "SSG 랜더스": "ssg.png",
    "롯데 자이언츠": "lotte.png", "한화 이글스": "hanwha.png",
    "NC 다이노스": "nc.png", "키움 히어로즈": "kiwoom.png",
}


def team_logo_path(team_name):
    return resource_path("image", "team_logos", TEAM_LOGO_FILES.get(team_name, "nc.png"))


def team_logo_icon(team_name):
    return QIcon(str(team_logo_path(team_name)))


def set_team_logo(label, team_name, width=64, height=48):
    pixmap = QPixmap(str(team_logo_path(team_name)))
    label.setText("")
    label.setPixmap(pixmap.scaled(
        QSize(width, height), Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    ))
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
