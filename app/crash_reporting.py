"""예외·Qt 오류·네이티브 강제종료를 파일과 화면에 남기는 전역 로거."""

import faulthandler
import os
import sys
import threading
import traceback
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import qInstallMessageHandler
from PySide6.QtWidgets import QApplication, QMessageBox


LOG_DIRECTORY = Path(__file__).resolve().parent.parent / "data" / "logs"
CRASH_LOG_PATH = LOG_DIRECTORY / "crash.log"
SESSION_MARKER_PATH = LOG_DIRECTORY / "running.session"

_crash_stream = None
_showing_error = False
_previous_session_unclean = False


def _timestamp():
    return datetime.now().isoformat(timespec="seconds")


def _write(text):
    global _crash_stream
    LOG_DIRECTORY.mkdir(parents=True, exist_ok=True)
    if _crash_stream is None or _crash_stream.closed:
        _crash_stream = CRASH_LOG_PATH.open(
            "a", encoding="utf-8", buffering=1
        )
    _crash_stream.write(text.rstrip() + "\n")
    _crash_stream.flush()


def report_exception(exc_type, value, tb, context="Python 예외"):
    details = "".join(traceback.format_exception(exc_type, value, tb))
    _write(
        f"\n[{_timestamp()}] {context}\n"
        f"PID={os.getpid()} THREAD={threading.current_thread().name}\n"
        f"{details}"
    )
    return details


def _show_exception(exc_type, value, tb, context):
    global _showing_error
    details = report_exception(exc_type, value, tb, context)
    print(f"[KBO FM 오류] {context}\n{details}", file=sys.stderr, flush=True)
    if _showing_error or QApplication.instance() is None:
        return
    _showing_error = True
    try:
        box = QMessageBox()
        box.setIcon(QMessageBox.Icon.Critical)
        box.setWindowTitle("KBO FM 오류")
        box.setText(
            "처리 중 오류가 발생했습니다. 게임을 강제로 종료하지 않고 "
            "오류 로그를 저장했습니다."
        )
        box.setInformativeText(
            f"{exc_type.__name__}: {value}\n\n"
            f"로그: {CRASH_LOG_PATH}"
        )
        box.setDetailedText(details)
        box.exec()
    except Exception:
        _write(
            f"[{_timestamp()}] 오류 안내창 표시 실패\n"
            f"{traceback.format_exc()}"
        )
    finally:
        _showing_error = False


def _sys_exception_hook(exc_type, value, tb):
    _show_exception(exc_type, value, tb, "처리되지 않은 Python 예외")


def _thread_exception_hook(args):
    details = report_exception(
        args.exc_type,
        args.exc_value,
        args.exc_traceback,
        f"백그라운드 스레드 예외 · {args.thread.name}",
    )
    print(
        f"[KBO FM 백그라운드 오류] {args.thread.name}\n{details}",
        file=sys.stderr,
        flush=True,
    )


def _qt_message_handler(message_type, context, message):
    if message_type.value >= 1:
        location = ""
        if context and context.file:
            location = f" · {context.file}:{context.line}"
        _write(
            f"[{_timestamp()}] Qt message type={message_type.value}"
            f"{location}\n{message}"
        )


def install_crash_reporting():
    """QApplication 생성 전에 호출해 이전 비정상 종료도 감지한다."""
    global _crash_stream, _previous_session_unclean
    LOG_DIRECTORY.mkdir(parents=True, exist_ok=True)
    _previous_session_unclean = SESSION_MARKER_PATH.exists()
    _crash_stream = CRASH_LOG_PATH.open("a", encoding="utf-8", buffering=1)
    _write(
        f"\n[{_timestamp()}] KBO FM 세션 시작 · PID={os.getpid()} · "
        f"이전 비정상 종료={_previous_session_unclean}"
    )
    SESSION_MARKER_PATH.write_text(
        f"{_timestamp()} PID={os.getpid()}", encoding="utf-8"
    )
    try:
        faulthandler.enable(_crash_stream, all_threads=True)
    except (RuntimeError, OSError):
        _write(f"[{_timestamp()}] faulthandler 활성화 실패")
    sys.excepthook = _sys_exception_hook
    if hasattr(threading, "excepthook"):
        threading.excepthook = _thread_exception_hook
    qInstallMessageHandler(_qt_message_handler)
    return _previous_session_unclean


def show_previous_crash_report(parent=None):
    if not _previous_session_unclean or not CRASH_LOG_PATH.exists():
        return
    text = CRASH_LOG_PATH.read_text(encoding="utf-8", errors="replace")
    tail = text[-12000:]
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Warning)
    box.setWindowTitle("이전 강제종료 감지")
    box.setText("직전 실행이 정상적으로 종료되지 않았습니다.")
    box.setInformativeText(f"전체 로그: {CRASH_LOG_PATH}")
    box.setDetailedText(tail)
    box.exec()


def mark_clean_shutdown():
    try:
        SESSION_MARKER_PATH.unlink(missing_ok=True)
    except OSError:
        pass
    _write(f"[{_timestamp()}] KBO FM 정상 종료")
    if _crash_stream is not None and not _crash_stream.closed:
        _crash_stream.close()

