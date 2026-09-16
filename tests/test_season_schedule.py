import unittest
from datetime import date

from app.config.calendar import START_POINTS
from app.config.season_schedule import (
    CALENDAR_END,
    CALENDAR_START,
    SEASON_EVENTS,
    events_for,
    next_event_after,
    phase_for,
)


class SeasonScheduleTests(unittest.TestCase):
    def test_calendar_covers_full_offseason(self):
        self.assertEqual(date(2025, 11, 1), CALENDAR_START)
        self.assertEqual(date(2026, 2, 28), CALENDAR_END)
        self.assertTrue(all(CALENDAR_START <= day <= CALENDAR_END for day in SEASON_EVENTS))

    def test_event_ids_are_unique_and_schema_is_complete(self):
        events = [event for daily in SEASON_EVENTS.values() for event in daily]
        ids = [event["event_id"] for event in events]
        self.assertEqual(len(ids), len(set(ids)))
        required = {"event_id", "category", "title", "detail", "task",
                    "importance", "event_type", "inbox", "requires_action",
                    "workflow", "choices"}
        self.assertTrue(all(required <= set(event) for event in events))

    def test_every_november_milestone_has_an_implementation_workflow(self):
        november_events = [
            event for day, events in SEASON_EVENTS.items()
            if day.year == 2025 and day.month == 11
            for event in events
        ]
        self.assertTrue(november_events)
        self.assertTrue(all(event["workflow"] != "notice" for event in november_events))
        self.assertEqual(
            {
                "offseason_open", "coaching_staff_review",
                "national_team_roster", "national_team_callup",
                "roster_audit", "offseason_training_plan",
                "national_team_late_join", "fa_eligible", "fa_approved",
                "fa_market_open", "korea_czech_one", "korea_czech_two",
                "second_draft_protect", "national_team_departure",
                "korea_japan_one", "korea_japan_two", "national_team_return",
                "second_draft", "draft_integration", "kbo_awards",
                "reserve_submit", "november_review", "reserve_publication",
            },
            {event["event_id"] for event in november_events},
        )

    def test_required_november_tasks_have_real_decision_paths(self):
        panel_workflows = {
            "roster_audit", "second_draft_protection", "reserve_submission",
            "second_draft_results",
        }
        for day, events in SEASON_EVENTS.items():
            if day.year != 2025 or day.month != 11:
                continue
            for event in events:
                if not event["requires_action"]:
                    continue
                self.assertTrue(
                    event["choices"] or event["workflow"] in panel_workflows,
                    event["event_id"],
                )

        required_ids = {
            event["event_id"]
            for day, events in SEASON_EVENTS.items()
            if day.year == 2025 and day.month == 11
            for event in events if event["requires_action"]
        }
        self.assertEqual(
            {
                "offseason_open", "coaching_staff_review", "roster_audit",
                "offseason_training_plan", "fa_eligible", "fa_approved",
                "fa_market_open", "second_draft_protect", "second_draft",
                "draft_integration", "reserve_submit", "november_review",
            },
            required_ids,
        )

    def test_official_milestones_match_2025_26_calendar(self):
        expected = {
            date(2025, 11, 8): "FA 승인",
            date(2025, 11, 19): "2차 드래프트",
            date(2025, 11, 24): "KBO 시상식",
            date(2025, 12, 9): "골든글러브",
            date(2025, 12, 19): "정규시즌 일정",
            date(2026, 2, 4): "시범경기 일정",
        }
        for day, phrase in expected.items():
            self.assertTrue(
                any(phrase in event["title"] for event in SEASON_EVENTS[day]),
                (day, phrase),
            )

    def test_camp_does_not_begin_in_november(self):
        self.assertEqual("비활동기간·캠프 준비", phase_for(date(2026, 1, 24))[0])
        self.assertEqual("1차 캠프", phase_for(date(2026, 1, 25))[0])
        self.assertEqual("2차 캠프", phase_for(date(2026, 2, 22))[0])
        self.assertNotIn("CAMP", " ".join(point["title"] for point in START_POINTS.values()))

    def test_event_helpers(self):
        self.assertEqual(SEASON_EVENTS[date(2025, 11, 8)], events_for(date(2025, 11, 8)))
        next_day, events = next_event_after(date(2025, 11, 8))
        self.assertEqual(date(2025, 11, 9), next_day)
        self.assertEqual(SEASON_EVENTS[next_day], events)

    def test_national_team_games_show_on_calendar_without_inbox_spam(self):
        all_events = events_for(date(2025, 11, 8))
        inbox_events = events_for(date(2025, 11, 8), inbox_only=True)
        self.assertTrue(any(event["event_type"] == "game" for event in all_events))
        self.assertFalse(any(event["event_type"] == "game" for event in inbox_events))


if __name__ == "__main__":
    unittest.main()
