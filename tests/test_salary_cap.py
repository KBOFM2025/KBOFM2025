import unittest

from app.services.salary_cap import cap_limit, salary_cap_from_players


class SalaryCapTests(unittest.TestCase):
    def test_2026_official_limit(self):
        self.assertEqual(cap_limit(2026), 1_439_723)

    def test_top_40_excludes_rookies_and_foreign_players(self):
        players = [
            {"team": "KIA 타이거즈", "salary": 40_000, "is_rookie": 0, "is_foreign": 0}
            for _ in range(42)
        ]
        players.extend((
            {"team": "KIA 타이거즈", "salary": 50_000, "is_rookie": 1, "is_foreign": 0},
            {"team": "KIA 타이거즈", "salary": 50_000, "is_rookie": 0, "is_foreign": 1},
        ))
        result = salary_cap_from_players(players, "KIA 타이거즈", 2026, 100_000)
        self.assertEqual(result["current"], 1_600_000)
        self.assertEqual(result["projected"], 1_660_000)
        self.assertEqual(result["excess"], 220_277)
        self.assertEqual(result["first_excess_levy"], 66_083)


if __name__ == "__main__":
    unittest.main()
