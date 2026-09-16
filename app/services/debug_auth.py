"""Local authentication for the privileged debug/QA account."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import sqlite3
from datetime import datetime, timedelta


DEBUG_AUTH_SQL = """
CREATE TABLE IF NOT EXISTS debug_credentials (
    id INTEGER PRIMARY KEY CHECK(id = 1),
    username TEXT NOT NULL UNIQUE,
    salt BLOB NOT NULL,
    password_hash BLOB NOT NULL,
    iterations INTEGER NOT NULL,
    failed_attempts INTEGER NOT NULL DEFAULT 0,
    locked_until TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""


class DebugAuthService:
    ITERATIONS = 310_000
    MAX_FAILURES = 5
    LOCK_SECONDS = 60

    def __init__(self, database_path):
        self.database_path = str(database_path)
        self._initialize()

    def _connect(self):
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self):
        connection = self._connect()
        try:
            connection.execute(DEBUG_AUTH_SQL)
            connection.commit()
        finally:
            connection.close()

    def is_configured(self):
        connection = self._connect()
        try:
            return connection.execute(
                "SELECT 1 FROM debug_credentials WHERE id=1"
            ).fetchone() is not None
        finally:
            connection.close()

    @classmethod
    def _validate(cls, username, password):
        username = str(username or "").strip()
        password = str(password or "")
        if len(username) < 4:
            raise ValueError("디버그 관리자 ID는 4자 이상이어야 합니다.")
        if len(password) < 8:
            raise ValueError("디버그 비밀번호는 8자 이상이어야 합니다.")
        if not any(character.isalpha() for character in password):
            raise ValueError("디버그 비밀번호에는 문자가 하나 이상 필요합니다.")
        if not any(character.isdigit() for character in password):
            raise ValueError("디버그 비밀번호에는 숫자가 하나 이상 필요합니다.")
        return username, password

    @staticmethod
    def _derive(password, salt, iterations):
        return hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt, int(iterations)
        )

    def register(self, username, password, confirmation):
        if self.is_configured():
            raise ValueError("디버그 관리자 계정이 이미 설정되어 있습니다.")
        username, password = self._validate(username, password)
        if password != str(confirmation or ""):
            raise ValueError("비밀번호 확인이 일치하지 않습니다.")
        salt = secrets.token_bytes(24)
        password_hash = self._derive(password, salt, self.ITERATIONS)
        now = datetime.now().isoformat(timespec="seconds")
        connection = self._connect()
        try:
            connection.execute(
                """
                INSERT INTO debug_credentials (
                    id,username,salt,password_hash,iterations,
                    failed_attempts,locked_until,created_at,updated_at
                ) VALUES (1,?,?,?,?,0,'',?,?)
                """,
                (
                    username, salt, password_hash, self.ITERATIONS,
                    now, now,
                ),
            )
            connection.commit()
        finally:
            connection.close()
        return username

    def authenticate(self, username, password):
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT * FROM debug_credentials WHERE id=1"
            ).fetchone()
            if row is None:
                return False, "디버그 관리자 계정을 먼저 설정하세요."
            now = datetime.now()
            locked_until = str(row["locked_until"] or "")
            if locked_until:
                try:
                    lock_time = datetime.fromisoformat(locked_until)
                except ValueError:
                    lock_time = now
                if lock_time > now:
                    seconds = max(1, int((lock_time - now).total_seconds()) + 1)
                    return False, f"로그인 시도가 잠겼습니다. {seconds}초 뒤 다시 시도하세요."
            candidate = self._derive(
                str(password or ""), bytes(row["salt"]), int(row["iterations"])
            )
            valid = (
                hmac.compare_digest(str(username or "").strip(), str(row["username"]))
                and hmac.compare_digest(candidate, bytes(row["password_hash"]))
            )
            if valid:
                connection.execute(
                    """
                    UPDATE debug_credentials
                    SET failed_attempts=0,locked_until='',updated_at=? WHERE id=1
                    """,
                    (now.isoformat(timespec="seconds"),),
                )
                connection.commit()
                return True, "로그인되었습니다."
            failures = int(row["failed_attempts"] or 0) + 1
            lock_value = ""
            if failures >= self.MAX_FAILURES:
                lock_value = (now + timedelta(seconds=self.LOCK_SECONDS)).isoformat(
                    timespec="seconds"
                )
            connection.execute(
                """
                UPDATE debug_credentials
                SET failed_attempts=?,locked_until=?,updated_at=? WHERE id=1
                """,
                (failures, lock_value, now.isoformat(timespec="seconds")),
            )
            connection.commit()
            if lock_value:
                return False, f"로그인에 {self.MAX_FAILURES}회 실패해 {self.LOCK_SECONDS}초 동안 잠겼습니다."
            return False, f"ID 또는 비밀번호가 올바르지 않습니다. 남은 시도 {self.MAX_FAILURES - failures}회"
        finally:
            connection.close()

