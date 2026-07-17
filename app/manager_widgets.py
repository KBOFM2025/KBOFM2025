"""감독 설정 화면에서 재사용하는 전용 위젯."""

from math import cos, pi, sin

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QImage,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QPolygonF,
    QRadialGradient,
)
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QSlider,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.config import MANAGER_ABILITY_MAX, MANAGER_RADAR_GROUPS


class ManagerStyleCard(QToolButton):
    """감독 사진을 전체 배경으로 사용하는 동일 크기 선택 카드."""

    def __init__(self, manager_name, tagline, image_path, focus_x=0.5, parent=None):
        super().__init__(parent)
        self.manager_name = manager_name
        self.tagline = tagline
        source_image = QImage(str(image_path))
        if source_image.isNull():
            self.color_photo = QPixmap()
            self.grayscale_photo = QPixmap()
        else:
            self.color_photo = QPixmap.fromImage(source_image)
            grayscale = source_image.convertToFormat(QImage.Format.Format_Grayscale8)
            self.grayscale_photo = QPixmap.fromImage(grayscale)
        self.focus_x = max(0.0, min(1.0, focus_x))
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumSize(245, 350)

    def sizeHint(self):
        return QSize(260, 370)

    def enterEvent(self, event):
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        card_rect = self.rect().adjusted(2, 2, -2, -2)
        card_path = QPainterPath()
        card_path.addRoundedRect(card_rect, 15, 15)
        painter.setClipPath(card_path)

        painter.fillPath(card_path, QColor("#101f31"))
        photo = self.color_photo if self.underMouse() else self.grayscale_photo
        if not photo.isNull():
            scaled = photo.scaled(
                card_rect.size(),
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            source_x = int(scaled.width() * self.focus_x - card_rect.width() / 2)
            source_x = max(0, min(source_x, scaled.width() - card_rect.width()))
            source_y = max(0, (scaled.height() - card_rect.height()) // 2)
            painter.drawPixmap(
                card_rect,
                scaled,
                scaled.rect().adjusted(
                    source_x,
                    source_y,
                    -(scaled.width() - card_rect.width() - source_x),
                    -(scaled.height() - card_rect.height() - source_y),
                ),
            )

        gradient = QLinearGradient(0, card_rect.top(), 0, card_rect.bottom())
        gradient.setColorAt(0.0, QColor(4, 12, 24, 15))
        gradient.setColorAt(0.42, QColor(4, 12, 24, 35))
        gradient.setColorAt(0.72, QColor(4, 12, 24, 185))
        gradient.setColorAt(1.0, QColor(4, 12, 24, 248))
        painter.fillPath(card_path, gradient)

        vignette = QRadialGradient(
            card_rect.center(),
            max(card_rect.width(), card_rect.height()) * 0.72,
        )
        vignette.setColorAt(0.0, QColor(0, 0, 0, 0))
        vignette.setColorAt(0.48, QColor(0, 0, 0, 8))
        vignette.setColorAt(0.78, QColor(0, 0, 0, 70))
        vignette.setColorAt(1.0, QColor(0, 0, 0, 165))
        painter.fillPath(card_path, vignette)

        painter.setClipping(False)
        border_color = QColor("#42a5f5") if self.isChecked() else QColor("#41566d")
        if self.underMouse() and not self.isChecked():
            border_color = QColor("#7894b0")
        painter.setPen(QPen(border_color, 4 if self.isChecked() else 2))
        painter.drawPath(card_path)

        text_rect = card_rect.adjusted(18, card_rect.height() - 92, -18, -16)
        painter.setPen(QColor("#ffffff"))
        painter.setFont(QFont("Noto Sans KR", 19, QFont.Bold))
        painter.drawText(
            text_rect.adjusted(0, 0, 0, -30),
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom,
            self.manager_name,
        )
        painter.setPen(QColor("#bcd1e5"))
        painter.setFont(QFont("Noto Sans KR", 12, QFont.DemiBold))
        painter.drawText(
            text_rect.adjusted(0, 44, 0, 0),
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
            self.tagline,
        )


class AbilitySliderControl(QWidget):
    valueChanged = Signal(int)

    def __init__(self, title, description, parent=None):
        super().__init__(parent)
        self.setObjectName("AbilityControl")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 11, 14, 12)
        layout.setSpacing(5)

        header = QHBoxLayout()
        title_label = QLabel(title)
        title_label.setFont(QFont("Noto Sans KR", 14, QFont.Bold))
        header.addWidget(title_label)
        header.addStretch()
        self.value_label = QLabel("0")
        self.value_label.setAlignment(Qt.AlignCenter)
        self.value_label.setFixedSize(34, 27)
        self.value_label.setStyleSheet(
            "background-color: #1976d2; color: white; border-radius: 7px; font-weight: bold;"
        )
        header.addWidget(self.value_label)
        layout.addLayout(header)

        description_label = QLabel(description)
        description_label.setWordWrap(True)
        description_label.setMinimumHeight(42)
        description_label.setStyleSheet("color: #aebfd0; font-size: 13px;")
        layout.addWidget(description_label)

        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, MANAGER_ABILITY_MAX)
        self.slider.setSingleStep(1)
        self.slider.setPageStep(1)
        self.slider.setTickInterval(1)
        self.slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.slider.valueChanged.connect(self._on_value_changed)
        layout.addWidget(self.slider)

    def _on_value_changed(self, value):
        self.value_label.setText(str(value))
        self.valueChanged.emit(value)

    def value(self):
        return self.slider.value()

    def setValue(self, value):
        self.slider.setValue(value)


class ManagerRadarChart(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.values = {label: 0.0 for label in MANAGER_RADAR_GROUPS}
        self.setMinimumSize(340, 390)

    def set_abilities(self, abilities):
        self.values = {
            label: sum(abilities.get(key, 0) for key in keys) / len(keys)
            for label, keys in MANAGER_RADAR_GROUPS.items()
        }
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        panel = self.rect().adjusted(5, 5, -5, -5)
        painter.setPen(QPen(QColor("#263b52"), 1))
        painter.setBrush(QColor("#0d1b2a"))
        painter.drawRoundedRect(panel, 14, 14)

        painter.setPen(QColor("#dbe7f3"))
        painter.setFont(QFont("Noto Sans KR", 15, QFont.Bold))
        painter.drawText(
            QRectF(panel.left(), panel.top() + 15, panel.width(), 28),
            Qt.AlignmentFlag.AlignCenter,
            "감독 능력 종합",
        )

        center = QPointF(panel.center().x(), panel.center().y() + 15)
        radius = min(panel.width(), panel.height()) * 0.31
        labels = list(MANAGER_RADAR_GROUPS)

        def point_at(index, scale):
            angle = -pi / 2 + index * (2 * pi / 6)
            return QPointF(
                center.x() + cos(angle) * radius * scale,
                center.y() + sin(angle) * radius * scale,
            )

        painter.setBrush(Qt.BrushStyle.NoBrush)
        for level in range(1, 6):
            scale = level / 5
            polygon = QPolygonF([point_at(i, scale) for i in range(6)])
            painter.setPen(QPen(QColor(49, 72, 96, 150), 1))
            painter.drawPolygon(polygon)

        for index in range(6):
            painter.setPen(QPen(QColor(49, 72, 96, 180), 1))
            painter.drawLine(center, point_at(index, 1.0))

        value_polygon = QPolygonF(
            [
                point_at(
                    index,
                    max(0.0, min(MANAGER_ABILITY_MAX, self.values[label]))
                    / MANAGER_ABILITY_MAX,
                )
                for index, label in enumerate(labels)
            ]
        )
        painter.setPen(QPen(QColor("#60b5f7"), 2))
        painter.setBrush(QColor(25, 118, 210, 105))
        painter.drawPolygon(value_polygon)

        painter.setFont(QFont("Noto Sans KR", 11, QFont.DemiBold))
        for index, label in enumerate(labels):
            label_point = point_at(index, 1.25)
            label_rect = QRectF(label_point.x() - 55, label_point.y() - 12, 110, 24)
            painter.setPen(QColor("#bcd1e5"))
            painter.drawText(label_rect, Qt.AlignmentFlag.AlignCenter, label)
