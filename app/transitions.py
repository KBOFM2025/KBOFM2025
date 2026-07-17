"""화면 스택과 탭에 사용하는 공통 페이드 전환."""

from PySide6.QtCore import QEasingCurve, QObject, QPropertyAnimation
from PySide6.QtWidgets import QGraphicsOpacityEffect


class FadeStackTransition(QObject):
    """현재 화면을 지운 뒤 대상 화면을 부드럽게 나타낸다."""

    def __init__(self, stack, parent=None, fade_out_ms=120, fade_in_ms=210):
        super().__init__(parent or stack)
        self.stack = stack
        self.fade_out_ms = fade_out_ms
        self.fade_in_ms = fade_in_ms
        self._animation = None
        self._target = None
        self._after_switch = None
        self._running = False

    def to_widget(self, widget, after_switch=None):
        if widget is None or widget is self.stack.currentWidget():
            if after_switch:
                after_switch()
            return
        self._start(widget, after_switch)

    def to_index(self, index, after_switch=None):
        if index < 0 or index >= self.stack.count():
            return
        self.to_widget(self.stack.widget(index), after_switch)

    def _start(self, target, after_switch):
        if self._running:
            return
        self._running = True
        self._target = target
        self._after_switch = after_switch
        effect = QGraphicsOpacityEffect(self.stack)
        self.stack.setGraphicsEffect(effect)
        self._animation = QPropertyAnimation(effect, b"opacity", self)
        self._animation.setDuration(self.fade_out_ms)
        self._animation.setStartValue(1.0)
        self._animation.setEndValue(0.0)
        self._animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self._animation.finished.connect(self._switch_screen)
        self._animation.start()

    def _switch_screen(self):
        self.stack.setGraphicsEffect(None)
        self.stack.setCurrentWidget(self._target)
        if self._after_switch:
            self._after_switch()

        effect = QGraphicsOpacityEffect(self.stack)
        self.stack.setGraphicsEffect(effect)
        self._animation = QPropertyAnimation(effect, b"opacity", self)
        self._animation.setDuration(self.fade_in_ms)
        self._animation.setStartValue(0.0)
        self._animation.setEndValue(1.0)
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._animation.finished.connect(self._finish)
        self._animation.start()

    def _finish(self):
        self.stack.setGraphicsEffect(None)
        self._animation = None
        self._target = None
        self._after_switch = None
        self._running = False


def fade_widget_in(widget, duration_ms=180):
    """이미 선택된 탭 내용을 짧게 페이드 인한다."""
    if widget is None:
        return
    previous = getattr(widget, "_screen_fade_animation", None)
    if previous is not None:
        previous.stop()
    effect = QGraphicsOpacityEffect(widget)
    widget.setGraphicsEffect(effect)
    animation = QPropertyAnimation(effect, b"opacity", widget)
    animation.setDuration(duration_ms)
    animation.setStartValue(0.15)
    animation.setEndValue(1.0)
    animation.setEasingCurve(QEasingCurve.Type.OutCubic)
    animation.finished.connect(lambda target=widget: target.setGraphicsEffect(None))
    widget._screen_fade_animation = animation
    animation.start()
