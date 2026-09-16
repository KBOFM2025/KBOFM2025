import sqlite3
import tempfile
import unittest
from pathlib import Path

from app.services.debug_auth import DebugAuthService


class DebugAuthTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "auth.db"
        self.service = DebugAuthService(self.database_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_first_run_registration_and_login(self):
        self.assertFalse(self.service.is_configured())
        username = self.service.register("debug_admin", "secure123", "secure123")
        self.assertEqual(username, "debug_admin")
        self.assertTrue(self.service.is_configured())
        success, _message = self.service.authenticate("debug_admin", "secure123")
        self.assertTrue(success)
        connection = sqlite3.connect(self.database_path)
        try:
            row = connection.execute(
                "SELECT salt,password_hash,iterations FROM debug_credentials WHERE id=1"
            ).fetchone()
        finally:
            connection.close()
        self.assertNotIn(b"secure123", bytes(row[1]))
        self.assertGreater(len(bytes(row[0])), 16)
        self.assertEqual(int(row[2]), DebugAuthService.ITERATIONS)

    def test_validation_and_lockout_after_five_failures(self):
        with self.assertRaises(ValueError):
            self.service.register("dbg", "short", "short")
        self.service.register("debug_admin", "secure123", "secure123")
        for _ in range(DebugAuthService.MAX_FAILURES - 1):
            success, message = self.service.authenticate("debug_admin", "wrong")
            self.assertFalse(success)
            self.assertIn("남은 시도", message)
        success, message = self.service.authenticate("debug_admin", "wrong")
        self.assertFalse(success)
        self.assertIn("잠겼습니다", message)
        success, message = self.service.authenticate("debug_admin", "secure123")
        self.assertFalse(success)
        self.assertIn("뒤 다시 시도", message)


if __name__ == "__main__":
    unittest.main()

