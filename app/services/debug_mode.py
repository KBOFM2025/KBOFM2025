"""Isolated QA helpers for forcing real manager-event workflows."""

from __future__ import annotations

import json
import sqlite3
from datetime import date

from app.config.season_schedule import SEASON_EVENTS
from app.services.manager_events import ManagerEventService


DYNAMIC_DEBUG_EVENTS = (
    ("player_complaint", "선수 면담", "기용 불만 선수와의 가변형 면담을 생성합니다."),
    ("trade_offer", "트레이드 제안", "실제 양 구단 선수 가치로 트레이드 협상을 생성합니다."),
    ("fa_opportunity", "FA 영입 제안", "FA 승인 선수와 샐러리캡을 반영한 제안을 생성합니다."),
    ("injury", "1군 선수 부상", "메디컬 대응 선택이 필요한 부상 이벤트를 생성합니다."),
    ("board_review", "이사회 운영 보고", "이사회 목표 대응 이벤트를 생성합니다."),
    ("entry_review", "1군 엔트리 점검", "현재 선수 상태를 사용한 엔트리 결정을 생성합니다."),
)


class DebugModeService:
    """Creates QA events in a debug save without advancing the calendar."""

    def __init__(self, saves_db_path, player_db_path, save_id, team):
        self.saves_db_path = str(saves_db_path)
        self.player_db_path = str(player_db_path)
        self.save_id = int(save_id)
        self.team = str(team)

    @staticmethod
    def catalog():
        rows = [
            {
                "key": f"dynamic:{key}",
                "group": "동적 이벤트",
                "title": title,
                "description": description,
                "source_date": "현재 선수단 기준",
            }
            for key, title, description in DYNAMIC_DEBUG_EVENTS
        ]
        for event_day in sorted(SEASON_EVENTS):
            for event in SEASON_EVENTS[event_day]:
                if not event.get("inbox", True):
                    continue
                rows.append({
                    "key": (
                        f"schedule:{event_day.isoformat()}:"
                        f"{event.get('event_id') or event['title']}"
                    ),
                    "group": "일정 이벤트",
                    "title": event["title"],
                    "description": event.get("task") or event.get("detail") or "",
                    "source_date": event_day.isoformat(),
                })
        return rows

    def _connect(self):
        connection = sqlite3.connect(self.saves_db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("ATTACH DATABASE ? AS playerdb", (self.player_db_path,))
        return connection

    @staticmethod
    def _seed_states(connection, save_id, day, players):
        for player in players:
            connection.execute(
                """
                INSERT OR IGNORE INTO player_simulation_states (
                    save_id,player_id,team,condition,fatigue,training_points,
                    injury_days,match_sharpness,morale,injury_risk,squad_group,
                    injury_type,last_updated
                ) VALUES (?,?,?,88,5,0,0,58,75,5,?,'',?)
                """,
                (
                    save_id,
                    int(player["id"]),
                    player["team"],
                    "1군" if int(player.get("status") or 0) else "2군",
                    day,
                ),
            )

    def create_event(self, catalog_key, event_date=None):
        day = str(event_date or date(2025, 11, 8).isoformat())
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            players = [
                dict(row) for row in connection.execute(
                    "SELECT * FROM playerdb.players ORDER BY team,name"
                ).fetchall()
            ]
            self._seed_states(connection, self.save_id, day, players)
            states = {
                int(row["player_id"]): dict(row)
                for row in connection.execute(
                    "SELECT * FROM player_simulation_states WHERE save_id=?",
                    (self.save_id,),
                ).fetchall()
            }
            before_id = int(connection.execute(
                "SELECT COALESCE(MAX(id),0) FROM manager_events WHERE save_id=?",
                (self.save_id,),
            ).fetchone()[0])
            run_number = int(connection.execute(
                """
                SELECT COUNT(*) FROM manager_events
                WHERE save_id=? AND payload_json LIKE '%\"debug_event\": true%'
                """,
                (self.save_id,),
            ).fetchone()[0]) + 1

            if catalog_key.startswith("schedule:"):
                _, source_day, event_key = catalog_key.split(":", 2)
                source = next(
                    (
                        dict(event)
                        for event in SEASON_EVENTS.get(date.fromisoformat(source_day), ())
                        if str(event.get("event_id") or event["title"]) == event_key
                    ),
                    None,
                )
                if source is None:
                    raise ValueError("선택한 일정 이벤트를 찾을 수 없습니다.")
                source["title"] = f"[DEBUG #{run_number}] {source['title']}"
                ManagerEventService._generate_schedule(
                    connection, self.save_id, self.team, source_day, (source,)
                )
            else:
                event_type = catalog_key.removeprefix("dynamic:")
                if event_type == "player_complaint":
                    managed = [player for player in players if player["team"] == self.team]
                    ManagerEventService._generate_complaint(
                        connection, self.save_id, self.team, day, managed, states
                    )
                elif event_type == "trade_offer":
                    ManagerEventService._generate_trade(
                        connection, self.save_id, self.team, day, players, states
                    )
                elif event_type == "fa_opportunity":
                    ManagerEventService._generate_fa(
                        connection, self.save_id, self.team, day, players, states
                    )
                elif event_type == "board_review":
                    managed = [player for player in players if player["team"] == self.team]
                    ManagerEventService._generate_board(
                        connection, self.save_id, self.team, day, managed, states
                    )
                elif event_type == "entry_review":
                    managed = [player for player in players if player["team"] == self.team]
                    ManagerEventService._generate_entry(
                        connection, self.save_id, self.team, day, managed, states
                    )
                elif event_type == "injury":
                    candidates = [
                        player for player in players
                        if player["team"] == self.team and int(player.get("status") or 0) == 1
                    ]
                    if not candidates:
                        raise ValueError("부상 이벤트를 만들 1군 선수가 없습니다.")
                    player = candidates[run_number % len(candidates)]
                    connection.execute(
                        """
                        UPDATE player_simulation_states
                        SET injury_days=7, injury_type='햄스트링 염좌',
                            condition=68, fatigue=45, injury_risk=28
                        WHERE save_id=? AND player_id=?
                        """,
                        (self.save_id, int(player["id"])),
                    )
                    ManagerEventService._generate_injuries(
                        connection,
                        self.save_id,
                        self.team,
                        day,
                        ({
                            "team": self.team,
                            "squad": "1군",
                            "player_id": player["id"],
                            "name": player["name"],
                            "injury_type": "햄스트링 염좌",
                            "expected_days": 7,
                            "position": player.get("pos") or player.get("position_group") or "-",
                            "age": player.get("age") or "-",
                            "condition": 68,
                            "fatigue": 45,
                        },),
                    )
                else:
                    raise ValueError("지원하지 않는 디버그 이벤트입니다.")

            created = connection.execute(
                """
                SELECT * FROM manager_events
                WHERE save_id=? AND id>?
                ORDER BY id DESC LIMIT 1
                """,
                (self.save_id, before_id),
            ).fetchone()
            if created is None:
                raise ValueError(
                    "현재 선수단 조건으로 이벤트를 생성하지 못했습니다. "
                    "이벤트 기록을 비운 뒤 다시 시도해 주세요."
                )
            payload = json.loads(created["payload_json"] or "{}")
            payload.update({
                "debug_event": True,
                "debug_catalog_key": catalog_key,
                "debug_run": run_number,
            })
            headline = str(created["headline"])
            if not headline.startswith("[DEBUG"):
                headline = f"[DEBUG #{run_number}] {headline}"
            connection.execute(
                "UPDATE manager_events SET headline=?,payload_json=? WHERE id=?",
                (headline, json.dumps(payload, ensure_ascii=False), int(created["id"])),
            )
            connection.commit()
            return int(created["id"])
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def recent_events(self):
        connection = sqlite3.connect(self.saves_db_path)
        connection.row_factory = sqlite3.Row
        try:
            return [dict(row) for row in connection.execute(
                """
                SELECT id,event_date,category,event_type,headline,status,result_text
                FROM manager_events
                WHERE save_id=? AND payload_json LIKE '%\"debug_event\": true%'
                ORDER BY id DESC LIMIT 100
                """,
                (self.save_id,),
            ).fetchall()]
        finally:
            connection.close()

    def clear_event_records(self):
        connection = sqlite3.connect(self.saves_db_path)
        try:
            ids = [
                int(row[0]) for row in connection.execute(
                    """
                    SELECT id FROM manager_events
                    WHERE save_id=? AND payload_json LIKE '%\"debug_event\": true%'
                    """,
                    (self.save_id,),
                ).fetchall()
            ]
            if ids:
                placeholders = ",".join("?" for _ in ids)
                connection.execute(
                    f"DELETE FROM manager_events WHERE id IN ({placeholders})", ids
                )
            connection.execute(
                """
                DELETE FROM daily_news
                WHERE save_id=? AND (
                    headline LIKE '[DEBUG %' OR headline LIKE '결정 완료 · [DEBUG %'
                )
                """,
                (self.save_id,),
            )
            connection.commit()
            return len(ids)
        finally:
            connection.close()
