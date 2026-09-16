import sqlite3
import tempfile
import unittest
from pathlib import Path

from app.services.domestic_fa import DomesticFAService
from app.services.manager_events import ManagerEventService
from app.services.training import TrainingService
from database.league_simulation_repository import LeagueSimulationRepository


class _TradeService(ManagerEventService):
    def __init__(self):
        pass

    def _trade_player_rows(self, payload):
        incoming = {
            "id": 1, "name": "영입 선수", "age": 27, "salary": 12000,
            "contract_years": 2, "position_group": "IF", "contact": 14,
            "power": 13, "plate_discipline": 13,
        }
        outgoing = {
            "id": 2, "name": "이적 선수", "age": 30, "salary": 7000,
            "contract_years": 1, "position_group": "IF", "contact": 10,
            "power": 10, "plate_discipline": 10,
        }
        return {1: incoming, 2: outgoing}, [], []

    def _team_position_needs(self, team):
        return set()


class NegotiationTermsTests(unittest.TestCase):
    def test_domestic_fa_option_has_expected_value_but_not_full_guarantee(self):
        service = object.__new__(DomesticFAService)
        service._sessions = {1: {
            "status": "ready", "round": 0, "lowballs": 0,
            "asking_salary": 10000, "asking_years": 2,
            "asking_bonus": 4000, "asking_incentive": 4000,
            "desired_role": "주전", "desired_usage": "선발 출장 100경기 이상",
            "interest": 60,
        }}
        without_option = service.submit_offer(
            1, 2, 8500, 2500, "주전", "선발 출장 100경기 이상", 0,
        )
        self.assertEqual(without_option["status"], "countered")

        service._sessions[1].update(status="ready", round=0, lowballs=0)
        with_option = service.submit_offer(
            1, 2, 9000, 3000, "주전", "선발 출장 100경기 이상", 10000,
        )
        self.assertGreater(with_option["score"], without_option["score"])

    def test_trade_cash_discount_plus_option_can_be_accepted(self):
        service = _TradeService()
        payload = {
            "managed_team": "KIA 타이거즈", "other_team": "LG 트윈스",
            "incoming_id": 1, "outgoing_id": 2,
            "incoming_name": "영입 선수", "outgoing_name": "이적 선수",
            "trade_terms": {"cash_from_user_10k": 30000},
        }
        terms = service._trade_response_terms(
            payload,
            "보장액을 낮추고 성과 옵션을 추가합니다.",
            2,
            {
                "action": "custom_offer", "cash_from_user_10k": 20000,
                "conditional_cash_10k": 20000, "condition_probability": 50,
            },
        )
        self.assertEqual(terms["status"], "accepted")
        self.assertEqual(terms["offer_expected_value_10k"], 30000)
        self.assertEqual(terms["conditional_cash_from_user_10k"], 20000)


class TrainingServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        self.save_db = root / "save.db"
        self.player_db = root / "players.db"
        connection = sqlite3.connect(self.player_db)
        try:
            connection.execute(
                """
                CREATE TABLE players (
                    id INTEGER PRIMARY KEY, name TEXT, team TEXT, pos TEXT,
                    position_group TEXT, status INTEGER, contact INTEGER,
                    bat_control INTEGER, timing INTEGER, power INTEGER,
                    plate_discipline INTEGER, fielding_range INTEGER,
                    catching INTEGER, throwing_accuracy INTEGER,
                    fielding_judgment INTEGER, speed INTEGER,
                    baserunning_judgment INTEGER, composure INTEGER,
                    pitcher_velocity INTEGER, pitcher_stuff INTEGER,
                    pitcher_strikeout INTEGER, pitcher_command INTEGER,
                    pitcher_walk_control INTEGER, pitcher_movement INTEGER,
                    pitcher_pitchability INTEGER, pitcher_stamina INTEGER,
                    pitcher_composure INTEGER
                )
                """
            )
            connection.execute(
                "INSERT INTO players VALUES (1,'김테스트','KIA 타이거즈','1B','IF',1,10,10,10,10,10,10,10,10,10,10,10,10,0,0,0,0,0,0,0,0,0)"
            )
            connection.commit()
        finally:
            connection.close()
        LeagueSimulationRepository(self.save_db, self.player_db)
        self.service = TrainingService(
            self.save_db, self.player_db, 1, "KIA 타이거즈"
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def _delegate(self):
        head = next(c for c in self.service.coaches("hired")
                    if c["team"] == self.service.team and "수석" in c["role"])
        self.service.save_coaching_structure(self.service.recommended_coaching_structure(), head["id"])
        self.service.set_management_policy(True, True)

    def _advance_training(self, day):
        from app.services.training_planner import apply_delegated_training
        players = self.service.players()
        with self.service._connect() as connection:
            apply_delegated_training(connection, 1, players, day)

    def test_delegation_persists_and_runs_on_multiple_days(self):
        self._delegate()
        reloaded = TrainingService(self.save_db, self.player_db, 1, self.service.team)
        self.assertEqual(reloaded.management_policy()["delegate_team"], 1)
        self._advance_training("2025-11-03")
        self._advance_training("2025-11-04")
        with self.service._connect() as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM training_delegation_reports").fetchone()[0], 2)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM weekly_training_sessions").fetchone()[0], 6)
        self.assertIn("2025-11-04", self.service.delegation_report())

    def test_delegation_preserves_manual_and_can_release(self):
        self._delegate()
        self.service.set_individual_plan(1, "장타", 3)
        schedule = self.service.weekly_schedule("2025-11-03")
        for session in schedule:
            session["session_type"] = "휴식"
        self.service.set_weekly_schedule(schedule, "2025-11-03")
        self._advance_training("2025-11-03")
        self.assertEqual(self.service.players()[0]["training_focus"], "장타")
        self.assertTrue(all(s["session_type"] == "휴식" for s in self.service.weekly_schedule("2025-11-03")))
        self.service.release_training_overrides()
        self._advance_training("2025-11-03")
        self.assertNotEqual(self.service.players()[0]["training_focus"], "장타")

    def test_manager_takes_control_and_head_is_required(self):
        with self.assertRaises(ValueError):
            self.service.set_management_policy(True, False)
        self._delegate()
        self.service.set_management_policy(False, False)
        self._advance_training("2025-11-03")
        with self.service._connect() as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM training_delegation_reports").fetchone()[0], 0)

    def test_club_profiles_and_recovery_are_valid(self):
        from app.config.club_training_profiles import PROFILES
        from app.services.training import SESSION_TYPES
        from app.services.training_planner import sessions_for_day
        self.assertEqual(len(PROFILES), 10)
        plans = set()
        for team in PROFILES:
            plan = sessions_for_day(team, "2025-11-03")
            plans.add(plan)
            self.assertTrue(all(s in SESSION_TYPES for s in plan))
            self.assertEqual(sessions_for_day(team, "2025-11-03", fatigue=70), ("휴식", "회복", "휴식"))
        self.assertGreater(len(plans), 5)

    def test_partial_week_is_filled_without_overwriting(self):
        self._delegate()
        self._advance_training("2025-11-03")
        schedule = self.service.weekly_schedule("2025-11-03")
        self.assertEqual(len(schedule), 21)
        self.assertEqual(sum(s["updated_at"].startswith("auto:") for s in schedule), 3)

    def test_delegation_rest_for_injury_and_skips_national_players(self):
        self._delegate()
        with self.service._connect() as connection:
            connection.execute("""INSERT INTO player_simulation_states
                (save_id,player_id,team,injury_days,last_updated) VALUES (1,1,?,5,'2025-11-02')""",
                (self.service.team,))
        self._advance_training("2025-11-03")
        self.assertEqual(self.service.players()[0]["training_focus"], "회복")
        with self.service._connect() as connection:
            connection.execute("UPDATE player_simulation_states SET injury_days=0,squad_group='국가대표'")
            connection.execute("DELETE FROM individual_training_plans")
        self._advance_training("2025-11-04")
        with self.service._connect() as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM individual_training_plans").fetchone()[0], 0)

    def test_team_individual_and_coach_assignment_flow(self):
        setting = self.service.set_team_setting("타격", 4, "보통")
        self.assertEqual(setting["focus"], "타격")
        candidate = self.service.coaches("candidate")[0]
        hired = self.service.hire_coach(candidate["id"], "타격코치")
        self.service.assign_coach(hired["id"], "team", 0, "타격")
        self.service.set_individual_plan(1, "컨택", 3, hired["id"])
        player = self.service.players()[0]
        self.assertEqual(player["training_focus"], "컨택")
        self.assertEqual(player["coach_id"], hired["id"])
        self.assertIn("타격", {item["focus"] for item in self.service.assignments()})
        self.assertTrue(any(
            item["assignment_type"] == "player" and item["target_id"] == 1
            for item in self.service.assignments()
        ))

    def test_november_training_workflow_requires_real_saved_work(self):
        progress = self.service.workflow_progress()
        self.assertFalse(progress["staff_ready"])
        self.assertFalse(progress["training_ready"])

        coaches = [
            coach for coach in self.service.coaches("hired")
            if coach["team"] == "KIA 타이거즈"
        ]
        for coach, focus in zip(coaches[:3], ("타격", "투수", "수비")):
            self.service.assign_coach(coach["id"], "team", 0, focus)
        progress = self.service.workflow_progress()
        self.assertTrue(progress["staff_ready"])
        self.assertFalse(progress["training_ready"])

        self.service.set_team_setting("균형", 3, "보통")
        self.service.set_individual_plan(1, "컨택", 2)
        progress = self.service.workflow_progress()
        self.assertTrue(progress["team_plan_ready"])
        self.assertEqual(1, progress["individual_plan_count"])
        self.assertFalse(progress["training_ready"])

    def test_fm_style_week_sessions_units_and_coach_workload(self):
        schedule = self.service.weekly_schedule("2025-11-03")
        self.assertEqual(21, len(schedule))
        self.assertTrue(all(not row["updated_at"] for row in schedule))
        schedule[0]["session_type"] = "체력"
        saved = self.service.set_weekly_schedule(schedule, "2025-11-03")
        self.assertEqual(21, len(saved))
        self.assertTrue(all(row["updated_at"] for row in saved))

        self.service.set_training_unit(1, "외야수조")
        self.assertEqual("외야수조", self.service.players()[0]["training_unit"])

        coach = next(
            item for item in self.service.coaches("hired")
            if item["team"] == "KIA 타이거즈"
        )
        self.service.assign_coach(coach["id"], "team", 0, "타격")
        workload = next(
            item for item in self.service.coach_workloads()
            if item["id"] == coach["id"]
        )
        self.assertEqual(1, workload["workload"])
        self.assertGreaterEqual(workload["training_stars"], 1.0)

    def test_daily_effect_and_development_checkpoint(self):
        self.service.set_team_setting("타격", 4, "강행")
        self.service.set_individual_plan(1, "컨택", 3)
        connection = sqlite3.connect(self.save_db)
        try:
            connection.row_factory = sqlite3.Row
            connection.execute("ATTACH DATABASE ? AS playerdb", (str(self.player_db),))
            player = dict(connection.execute("SELECT * FROM playerdb.players WHERE id=1").fetchone())
            state = {"injury_days": 0, "training_points": 58}
            effect = TrainingService.daily_effect(connection, 1, player, state, 3)
            self.assertGreaterEqual(effect["training_gain"], 5)
            changed = TrainingService.apply_development_checkpoint(
                connection, 1, 58, effect["training_gain"], effect["attribute"]
            )
            self.assertTrue(changed)
            connection.commit()
            changed_attribute = effect["attribute"]
            connection.execute("DETACH DATABASE playerdb")
        finally:
            connection.close()
        connection = sqlite3.connect(self.player_db)
        try:
            value = connection.execute(
                f"SELECT {changed_attribute} FROM players WHERE id=1"
            ).fetchone()[0]
            self.assertEqual(value, 11)
        finally:
            connection.close()

    def test_coaching_structure_persists_multiple_fields_and_rejects_other_clubs(self):
        coaches = [c for c in self.service.coaches("hired") if c["team"] == self.service.team]
        head = next(c for c in coaches if "수석" in c["role"])
        coach_id = coaches[0]["id"]
        self.service.save_coaching_structure({coach_id: {"타격", "수비"}}, head["id"])
        restored = TrainingService(self.save_db, self.player_db, 1, self.service.team)
        assignments = restored.assignments()
        self.assertEqual({a["focus"] for a in assignments if a["assignment_type"] == "team"}, {"타격", "수비"})
        self.assertTrue(any(a["focus"] == "총괄" for a in assignments))
        with self.assertRaises(ValueError):
            restored.save_coaching_structure({-999: {"타격"}})
        self.assertEqual(assignments, restored.assignments())
        restored.save_coaching_structure({})
        self.assertEqual([], restored.assignments())

    def test_coach_overload_reduces_actual_development_and_rest_blocks_growth(self):
        coach = next(c for c in self.service.coaches("hired") if c["team"] == self.service.team)
        self.service.set_team_setting("타격", 4, "보통")
        self.service.set_individual_plan(1, "컨택", 3)
        with self.service._connect() as connection:
            connection.execute("UPDATE coaching_staff SET batting=20,motivation=20,discipline=20 WHERE id=?", (coach["id"],))
        def effect(day=None):
            with self.service._connect() as connection:
                return self.service.daily_effect(connection, 1, self.service.players()[0], {}, 3, day)
        self.service.save_coaching_structure({coach["id"]: {"타격"}})
        focused = effect()["training_gain"]
        self.service.save_coaching_structure({coach["id"]: {"타격", "수비", "주루", "체력", "투수"}})
        self.assertLess(effect()["training_gain"], focused)
        schedule = self.service.weekly_schedule("2025-11-03")
        for session in schedule:
            session["session_type"] = "휴식"
        self.service.set_weekly_schedule(schedule, "2025-11-03")
        rest = effect("2025-11-03")
        self.assertEqual(0, rest["training_gain"])
        self.assertLess(rest["fatigue_load"], 0)

    def test_unit_coach_only_affects_assigned_unit(self):
        coach = next(c for c in self.service.coaches("hired") if c["team"] == self.service.team)
        self.service.set_individual_plan(1, "컨택", 2)
        self.service.assign_coach(coach["id"], "unit", 1, "타격")
        with self.service._connect() as connection:
            player = self.service.players()[0]
            wrong_unit = self.service.daily_effect(connection, 1, player, {}, 3)["training_gain"]
        self.service.assign_coach(coach["id"], "unit", 3, "타격")
        with self.service._connect() as connection:
            right_unit = self.service.daily_effect(connection, 1, player, {}, 3)["training_gain"]
        self.assertGreater(right_unit, wrong_unit)

    def test_real_2025_staff_covers_all_clubs_with_fm_style_ratings(self):
        staff = [item for item in self.service.coaches("hired") if item["is_real"]]
        teams = {item["team"] for item in staff}
        self.assertEqual(len(teams), 10)
        self.assertTrue(all(sum(item["team"] == team for item in staff) >= 10 for team in teams))
        self.assertFalse(any(
            item["team"] == "KIA 타이거즈"
            and item["squad"] == "1군"
            and "감독" in item["role"]
            for item in staff
        ))
        self.assertEqual(sum(
            item["team"] != "KIA 타이거즈"
            and item["squad"] == "1군"
            and "감독" in item["role"]
            for item in staff
        ), 9)
        rating_fields = (
            "batting", "pitching", "defense", "baserunning", "catching", "mental",
            "motivation", "discipline", "man_management", "adaptability",
            "youth_development", "data_analysis",
        )
        self.assertTrue(all(
            1 <= int(coach[field]) <= 20 for coach in staff for field in rating_fields
        ))
        self.assertTrue(all(55 <= int(coach["current_ability"]) <= 200 for coach in staff))
        self.assertTrue(all(coach["source_url"] and coach["source_as_of"] for coach in staff))

    def test_namesakes_in_different_teams_and_hired_candidate_are_stable(self):
        namesakes = [
            item for item in self.service.coaches("hired") if item["name"] == "이승호"
        ]
        self.assertEqual({item["team"] for item in namesakes}, {"SSG 랜더스", "키움 히어로즈"})
        candidate = next(item for item in self.service.coaches("candidate") if item["name"] == "김기태")
        self.service.hire_coach(candidate["id"], "타격코치")
        TrainingService(self.save_db, self.player_db, 1, "KIA 타이거즈")
        same_name = [item for item in self.service.coaches() if item["name"] == "김기태"]
        self.assertEqual(len(same_name), 1)
        self.assertEqual(same_name[0]["status"], "hired")


if __name__ == "__main__":
    unittest.main()
