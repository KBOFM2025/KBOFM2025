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
                    "importance", "event_type", "inbox", "requires_action"}
        self.assertTrue(all(required <= set(event) for event in events))

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
