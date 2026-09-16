import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from app.services.debug_mode import DebugModeService
from database.save_database import SaveDatabase


class DebugModeTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        self.saves_path = root / "saves.db"
        self.players_path = root / "players.db"
        connection = sqlite3.connect(self.players_path)
        try:
            connection.execute(
                """
                CREATE TABLE players (
                    id INTEGER PRIMARY KEY,
                    team TEXT NOT NULL,
                    name TEXT NOT NULL,
                    status INTEGER NOT NULL DEFAULT 0,
                    pos TEXT,
                    position_group TEXT,
                    age INTEGER
                )
                """
            )
            connection.executemany(
                "INSERT INTO players VALUES (?,?,?,?,?,?,?)",
                (
                    (1, "KIA 타이거즈", "디버그 타자", 1, "1B", "IF", 27),
                    (2, "LG 트윈스", "상대 타자", 1, "CF", "OF", 28),
                ),
            )
            connection.commit()
        finally:
            connection.close()
        self.database = SaveDatabase(self.saves_path)
        self.normal_id = self.database.create_save("일반", "LG 트윈스")
        self.debug_id = self.database.create_save(
            "[DEBUG] 이벤트 QA",
            "KIA 타이거즈",
            {"manager_name": "DEBUG 감독"},
            current_date="2025-11-08",
            is_debug=True,
        )
        self.service = DebugModeService(
            self.saves_path, self.players_path, self.debug_id, "KIA 타이거즈"
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_debug_save_is_reusable_and_hidden_from_normal_load_list(self):
        self.assertEqual([row["id"] for row in self.database.list_saves()], [self.normal_id])
        self.assertEqual(self.database.get_debug_save()["id"], self.debug_id)
        self.assertEqual(int(self.database.get_debug_save()["is_debug"]), 1)

    def test_schedule_and_injury_can_be_forced_and_cleared(self):
        schedule_id = self.service.create_event(
            "schedule:2025-11-01:offseason_open", "2025-11-08"
        )
        injury_id = self.service.create_event("dynamic:injury", "2025-11-08")
        rows = self.service.recent_events()
        self.assertEqual({row["id"] for row in rows}, {schedule_id, injury_id})
        connection = sqlite3.connect(self.saves_path)
        try:
            payload = json.loads(connection.execute(
                "SELECT payload_json FROM manager_events WHERE id=?", (injury_id,)
            ).fetchone()[0])
        finally:
            connection.close()
        self.assertTrue(payload["debug_event"])
        self.assertEqual(payload["debug_catalog_key"], "dynamic:injury")
        self.assertEqual(self.service.clear_event_records(), 2)
        self.assertEqual(self.service.recent_events(), [])

    def test_catalog_contains_dynamic_and_full_schedule_workflows(self):
        catalog = self.service.catalog()
        keys = {row["key"] for row in catalog}
        self.assertIn("dynamic:player_complaint", keys)
        self.assertIn("dynamic:trade_offer", keys)
        self.assertIn("dynamic:fa_opportunity", keys)
        self.assertIn("schedule:2025-11-12:second_draft_protect", keys)


if __name__ == "__main__":
    unittest.main()
