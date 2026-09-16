"""연습경기 일정과 향후 경기 결과를 관리하는 서비스."""

from __future__ import annotations

import csv
import json
import random
import sqlite3
from collections import defaultdict
from contextlib import contextmanager
from datetime import date, datetime
from functools import lru_cache

from app.config.teams import TEAM_INFO
from app.services.kbo_game_calibration import (
    build_game_environment,
    matchup_adjustments,
    pitcher_day_form,
)
from app.services.team_lineup_engine import hitter_rating, pitcher_rating
from app.utils import resource_path
from database.league_simulation_repository import LeagueSimulationRepository


PRACTICE_WINDOW_START = date(2026, 2, 24)
PRACTICE_WINDOW_END = date(2026, 2, 28)
VENUE_TYPES = {
    "home": "홈",
    "away": "원정",
    "neutral": "중립",
}
PRACTICE_PURPOSES = (
    "전력 점검",
    "주전 실전 감각",
    "유망주 평가",
    "선발투수 빌드업",
    "불펜 운용 점검",
    "전술 실험",
)
LINEUP_POLICIES = (
    "주전 중심",
    "주전·백업 혼합",
    "유망주 중심",
    "경쟁 포지션 우선",
)
PITCHING_PLANS = (
    "정규 선발 운용",
    "선발 3이닝 제한",
    "선발 50구 제한",
    "불펜 데이",
    "투수 전원 점검",
)


@lru_cache(maxsize=1)
def _pitcher_usage_profiles():
    """2025 1군 기록으로 등판당 평균 아웃과 추정 투구 수를 만든다."""
    path = resource_path("data", "source", "kbo_2025_first_team_pitching.csv")
    if not path.exists():
        return {}
    profiles = {}
    with path.open("r", encoding="utf-8-sig", newline="") as source:
        for row in csv.DictReader(source):
            player_id = str(row.get("kbo_player_id") or "").strip()
            try:
                games = max(1, int(row.get("G") or 0))
                outs = int(row.get("IP_OUTS") or 0)
                batters = int(row.get("TBF") or 0)
            except (TypeError, ValueError):
                continue
            if not player_id or not outs or not batters:
                continue
            profiles[player_id] = {
                "average_outs": outs / games,
                "average_pitches": batters / games * 3.85,
                "complete_game_rate": int(row.get("CG") or 0) / games,
            }
    return profiles


def _pitcher_workload_limit(player, plan, is_starter):
    profile = _pitcher_usage_profiles().get(
        str(player.get("kbo_player_id") or ""), {}
    )
    if not is_starter:
        return {
            "outs": max(3, min(6, round(float(profile.get("average_outs") or 3)))),
            "pitches": max(18, min(34, round(float(profile.get("average_pitches") or 24)))),
        }
    historical_outs = max(
        15,
        min(19, round(float(profile.get("average_outs") or 16.5))),
    )
    historical_pitches = max(
        78,
        min(102, round(float(profile.get("average_pitches") or 88))),
    )
    limits = {
        "정규 선발 운용": (historical_outs, historical_pitches),
        "선발 3이닝 제한": (9, 58),
        "선발 50구 제한": (12, 52),
        "불펜 데이": (3, 28),
        "투수 전원 점검": (6, 40),
    }
    outs, pitches = limits.get(str(plan), (historical_outs, historical_pitches))
    return {"outs": outs, "pitches": pitches}


class PracticeGameError(ValueError):
    """연습경기 일정이 규칙에 맞지 않을 때 발생한다."""


class PracticeGameService:
    """정규시즌 기록과 분리된 연습경기 일정을 저장한다."""

    def __init__(self, saves_db_path, player_db_path, save_id, managed_team):
        self.saves_db_path = str(saves_db_path)
        self.player_db_path = str(player_db_path)
        self.save_id = int(save_id)
        self.managed_team = str(managed_team)
        LeagueSimulationRepository(self.saves_db_path, self.player_db_path)
        self._require_debug_save()

    def _require_debug_save(self):
        with self._connect() as connection:
            row = connection.execute(
                "SELECT is_debug FROM game_saves WHERE id=?",
                (self.save_id,),
            ).fetchone()
        if row is None or not bool(row["is_debug"]):
            raise PracticeGameError(
                "연습경기 기능은 현재 DEBUG 계정에서만 사용할 수 있습니다."
            )

    @contextmanager
    def _connect(self):
        connection = sqlite3.connect(self.saves_db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    @property
    def opponents(self):
        return tuple(team for team in TEAM_INFO if team != self.managed_team)

    def schedule_game(
        self,
        game_date,
        opponent_team,
        *,
        venue_type="home",
        start_time="13:00",
        innings=9,
        purpose="전력 점검",
        lineup_policy="주전 중심",
        pitching_plan="선발 3이닝 제한",
        current_date=None,
    ):
        game_day = self._as_date(game_date)
        today = self._as_date(current_date) if current_date else None
        opponent_team = str(opponent_team).strip()
        venue_type = str(venue_type).strip()
        start_time = str(start_time).strip()
        innings = int(innings)

        if not PRACTICE_WINDOW_START <= game_day <= PRACTICE_WINDOW_END:
            raise PracticeGameError(
                "연습경기는 2차 캠프 기간인 2026년 2월 24일부터 28일 사이에 편성할 수 있습니다."
            )
        if today and game_day < today:
            raise PracticeGameError("이미 지난 날짜에는 연습경기를 편성할 수 없습니다.")
        if opponent_team not in self.opponents:
            raise PracticeGameError("상대 구단은 다른 KBO 구단 중에서 선택해야 합니다.")
        if venue_type not in VENUE_TYPES:
            raise PracticeGameError("경기장 구분이 올바르지 않습니다.")
        if innings not in (7, 9):
            raise PracticeGameError("연습경기는 7이닝 또는 9이닝으로 편성해야 합니다.")
        if purpose not in PRACTICE_PURPOSES:
            raise PracticeGameError("지원하지 않는 경기 목적입니다.")
        if lineup_policy not in LINEUP_POLICIES:
            raise PracticeGameError("지원하지 않는 라인업 운용 방식입니다.")
        if pitching_plan not in PITCHING_PLANS:
            raise PracticeGameError("지원하지 않는 투수 운용 계획입니다.")
        self._validate_time(start_time)

        now = datetime.now().isoformat(timespec="seconds")
        stadium = self._stadium_for(opponent_team, venue_type)
        try:
            with self._connect() as connection:
                cursor = connection.execute(
                    """
                    INSERT INTO practice_games (
                        save_id, game_date, managed_team, opponent_team,
                        venue_type, stadium, start_time, innings, purpose,
                        lineup_policy, pitching_plan, status, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'scheduled', ?, ?)
                    """,
                    (
                        self.save_id, game_day.isoformat(), self.managed_team,
                        opponent_team, venue_type, stadium, start_time, innings,
                        purpose, lineup_policy, pitching_plan, now, now,
                    ),
                )
                game_id = cursor.lastrowid
                if game_id is None:
                    raise PracticeGameError("연습경기 일정을 저장하지 못했습니다.")
                return int(game_id)
        except sqlite3.IntegrityError as error:
            raise PracticeGameError("해당 날짜에는 이미 연습경기가 편성되어 있습니다.") from error

    def list_games(self, start_date=None, end_date=None, *, include_cancelled=False):
        conditions = ["save_id=?", "managed_team=?"]
        params = [self.save_id, self.managed_team]
        if start_date is not None:
            conditions.append("game_date>=?")
            params.append(self._as_date(start_date).isoformat())
        if end_date is not None:
            conditions.append("game_date<=?")
            params.append(self._as_date(end_date).isoformat())
        if not include_cancelled:
            conditions.append("status<>'cancelled'")
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT * FROM practice_games
                WHERE {' AND '.join(conditions)}
                ORDER BY game_date, start_time, id
                """,
                tuple(params),
            ).fetchall()
        return [dict(row) for row in rows]

    def games_on(self, game_date, *, include_cancelled=False):
        day = self._as_date(game_date)
        return self.list_games(day, day, include_cancelled=include_cancelled)

    def cancel_game(self, game_id, *, current_date=None):
        today = self._as_date(current_date) if current_date else None
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM practice_games
                WHERE id=? AND save_id=? AND managed_team=?
                """,
                (int(game_id), self.save_id, self.managed_team),
            ).fetchone()
            if row is None:
                raise PracticeGameError("연습경기 일정을 찾을 수 없습니다.")
            if row["status"] != "scheduled":
                raise PracticeGameError("예정 상태의 경기만 취소할 수 있습니다.")
            if today and self._as_date(row["game_date"]) < today:
                raise PracticeGameError("이미 지난 연습경기는 취소할 수 없습니다.")
            connection.execute(
                """
                UPDATE practice_games
                SET status='cancelled', updated_at=?
                WHERE id=?
                """,
                (datetime.now().isoformat(timespec="seconds"), int(game_id)),
            )

    def game_details(self, game_id):
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM practice_games
                WHERE id=? AND save_id=? AND managed_team=?
                """,
                (int(game_id), self.save_id, self.managed_team),
            ).fetchone()
        if row is None:
            raise PracticeGameError("연습경기를 찾을 수 없습니다.")
        return dict(row)

    def reset_debug_game(
        self,
        game_id,
        *,
        opponent_team=None,
        venue_type="home",
        start_time="13:00",
        innings=9,
        purpose="전력 점검",
        lineup_policy="주전·백업 혼합",
        pitching_plan="정규 선발 운용",
    ):
        """기존 DEBUG 경기 슬롯을 완전히 비우고 새 QA 경기로 재사용한다."""
        game = self.game_details(game_id)
        opponent_team = str(opponent_team or game["opponent_team"]).strip()
        venue_type = str(venue_type).strip()
        start_time = str(start_time).strip()
        innings = int(innings)
        if opponent_team not in self.opponents:
            raise PracticeGameError("상대 구단은 다른 KBO 구단 중에서 선택해야 합니다.")
        if venue_type not in VENUE_TYPES:
            raise PracticeGameError("경기장 구분이 올바르지 않습니다.")
        if innings not in (7, 9):
            raise PracticeGameError("연습경기는 7이닝 또는 9이닝으로 편성해야 합니다.")
        if purpose not in PRACTICE_PURPOSES:
            raise PracticeGameError("지원하지 않는 경기 목적입니다.")
        if lineup_policy not in LINEUP_POLICIES:
            raise PracticeGameError("지원하지 않는 라인업 운용 방식입니다.")
        if pitching_plan not in PITCHING_PLANS:
            raise PracticeGameError("지원하지 않는 투수 운용 계획입니다.")
        self._validate_time(start_time)

        now = datetime.now().isoformat(timespec="seconds")
        stadium = self._stadium_for(opponent_team, venue_type)
        with self._connect() as connection:
            for table in (
                "practice_game_live_states",
                "practice_game_plays",
                "practice_game_player_stats",
                "practice_game_roster",
            ):
                connection.execute(
                    f"DELETE FROM {table} WHERE game_id=?", (int(game_id),)
                )
            connection.execute(
                """
                UPDATE practice_games
                SET opponent_team=?,venue_type=?,stadium=?,start_time=?,innings=?,
                    purpose=?,lineup_policy=?,pitching_plan=?,status='scheduled',
                    managed_score=NULL,opponent_score=NULL,result_json='{}',updated_at=?
                WHERE id=? AND save_id=? AND managed_team=?
                """,
                (
                    opponent_team, venue_type, stadium, start_time, innings,
                    purpose, lineup_policy, pitching_plan, now, int(game_id),
                    self.save_id, self.managed_team,
                ),
            )
        return int(game_id)

    def available_players(self, team=None):
        """1·2군 구분과 컨디션을 포함한 경기 선택 가능 선수 목록."""
        team = str(team or self.managed_team)
        player_connection = sqlite3.connect(self.player_db_path)
        player_connection.row_factory = sqlite3.Row
        try:
            players = [
                dict(row) for row in player_connection.execute(
                    "SELECT * FROM players WHERE team=? ORDER BY status DESC, position_group, id",
                    (team,),
                ).fetchall()
            ]
        finally:
            player_connection.close()
        with self._connect() as connection:
            states = {
                int(row["player_id"]): dict(row)
                for row in connection.execute(
                    """
                    SELECT * FROM player_simulation_states
                    WHERE save_id=? AND team=?
                    """,
                    (self.save_id, team),
                ).fetchall()
            }
        for player in players:
            state = states.get(int(player["id"]), {})
            player["squad_group"] = str(
                state.get("squad_group")
                or ("1군" if int(player.get("status") or 0) == 1 else "2군")
            )
            player["condition"] = int(state.get("condition", 85))
            player["fatigue"] = int(state.get("fatigue", 0))
            player["match_sharpness"] = int(state.get("match_sharpness", 55))
            player["injury_days"] = int(state.get("injury_days", 0))
            player["rating"] = round(
                pitcher_rating(player)
                if player.get("position_group") == "P"
                else hitter_rating(player),
                1,
            )
        return players

    def suggest_lineup(self, squad_preference="mixed", team=None):
        """수비 구성 요건을 지키며 선발 9명과 선발투수를 추천한다."""
        team = str(team or self.managed_team)
        players = [p for p in self.available_players(team) if not p["injury_days"]]
        squad_bonus = {
            "first": {"1군": 8.0, "2군": 0.0},
            "second": {"1군": 0.0, "2군": 8.0},
            "mixed": {"1군": 3.0, "2군": 3.0},
        }.get(squad_preference, {"1군": 3.0, "2군": 3.0})

        def score(player):
            return (
                float(player["rating"]) * 4
                + int(player["condition"]) * .18
                + int(player["match_sharpness"]) * .10
                - int(player["fatigue"]) * .15
                + squad_bonus.get(player["squad_group"], 0.0)
            )

        hitters = [p for p in players if p.get("position_group") != "P"]
        pitchers = [p for p in players if p.get("position_group") == "P"]
        selected = []
        used = set()
        slots = (
            ("C", "C"), ("IF", "1B"), ("IF", "2B"), ("IF", "3B"),
            ("IF", "SS"), ("OF", "LF"), ("OF", "CF"), ("OF", "RF"),
        )
        for group, position in slots:
            candidates = [
                p for p in hitters
                if p["id"] not in used and p.get("position_group") == group
            ]
            if not candidates:
                candidates = [p for p in hitters if p["id"] not in used]
            if not candidates:
                break
            player = max(candidates, key=lambda item: (score(item), -int(item["id"])))
            used.add(player["id"])
            selected.append({**player, "defensive_position": position})
        remaining = [p for p in hitters if p["id"] not in used]
        if remaining:
            player = max(remaining, key=lambda item: (score(item), -int(item["id"])))
            selected.append({**player, "defensive_position": "DH"})
        selected.sort(
            key=lambda p: (
                float(p.get("contact") or p.get("con") or 10) * 1.35
                + float(p.get("power") or p.get("pow") or 10)
                + float(p.get("plate_discipline") or p.get("eye") or 10) * .7
            ),
            reverse=True,
        )
        starter = max(pitchers, key=score) if pitchers else None
        return selected[:9], starter

    def save_lineup(self, game_id, hitter_ids, starter_id, positions=None):
        game = self.game_details(game_id)
        if game["status"] != "scheduled":
            raise PracticeGameError("예정 상태의 경기만 라인업을 변경할 수 있습니다.")
        hitter_ids = [int(player_id) for player_id in hitter_ids]
        if len(hitter_ids) != 9 or len(set(hitter_ids)) != 9:
            raise PracticeGameError("서로 다른 선발 타자 9명을 선택해야 합니다.")
        players = {int(p["id"]): p for p in self.available_players()}
        if any(player_id not in players for player_id in hitter_ids):
            raise PracticeGameError("선수단에 없는 선수가 포함되어 있습니다.")
        hitters = [players[player_id] for player_id in hitter_ids]
        if any(p.get("position_group") == "P" for p in hitters):
            raise PracticeGameError("타순에는 야수만 등록할 수 있습니다.")
        if any(p["injury_days"] for p in hitters):
            raise PracticeGameError("부상 선수는 선발 라인업에 등록할 수 없습니다.")
        starter = players.get(int(starter_id))
        if starter is None or starter.get("position_group") != "P":
            raise PracticeGameError("선발투수를 선택해야 합니다.")
        if starter["injury_days"]:
            raise PracticeGameError("부상 투수는 선발로 등록할 수 없습니다.")

        positions = list(positions) if positions is not None else self._positions_for(hitters)
        required_positions = {"C", "1B", "2B", "3B", "SS", "LF", "CF", "RF", "DH"}
        if len(positions) != 9 or set(positions) != required_positions:
            raise PracticeGameError(
                "수비 위치는 C·1B·2B·3B·SS·LF·CF·RF·DH를 한 명씩 배정해야 합니다."
            )
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM practice_game_roster WHERE game_id=? AND team=?",
                (int(game_id), self.managed_team),
            )
            connection.executemany(
                """
                INSERT INTO practice_game_roster (
                    game_id,team,player_id,player_name,role,batting_order,
                    position,is_starter
                ) VALUES (?,?,?,?,?,?,?,1)
                """,
                [
                    (
                        int(game_id), self.managed_team, int(player["id"]),
                        player["name"], "batter", order, positions[index],
                    )
                    for index, (order, player) in enumerate(zip(range(1, 10), hitters))
                ],
            )
            connection.execute(
                """
                INSERT INTO practice_game_roster (
                    game_id,team,player_id,player_name,role,batting_order,
                    position,is_starter
                ) VALUES (?,?,?,?, 'pitcher',0,'P',1)
                """,
                (int(game_id), self.managed_team, int(starter["id"]), starter["name"]),
            )
        self._ensure_opponent_lineup(int(game_id), game["opponent_team"])
        return self.prepared_lineup(game_id)

    def prepared_lineup(self, game_id):
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM practice_game_roster
                WHERE game_id=? ORDER BY team, role, batting_order, player_id
                """,
                (int(game_id),),
            ).fetchall()
        return [dict(row) for row in rows]

    def _ensure_opponent_lineup(self, game_id, opponent_team):
        with self._connect() as connection:
            existing = connection.execute(
                "SELECT COUNT(*) FROM practice_game_roster WHERE game_id=? AND team=?",
                (game_id, opponent_team),
            ).fetchone()[0]
        if existing:
            return
        hitters, starter = self.suggest_lineup("first", opponent_team)
        if len(hitters) < 9 or starter is None:
            raise PracticeGameError("상대 구단의 경기 가능 선수가 부족합니다.")
        with self._connect() as connection:
            connection.executemany(
                """
                INSERT INTO practice_game_roster (
                    game_id,team,player_id,player_name,role,batting_order,
                    position,is_starter
                ) VALUES (?,?,?,?,?,?,?,1)
                """,
                [
                    (
                        game_id, opponent_team, int(player["id"]), player["name"],
                        "batter", order, player["defensive_position"],
                    )
                    for order, player in enumerate(hitters, 1)
                ],
            )
            connection.execute(
                """
                INSERT INTO practice_game_roster (
                    game_id,team,player_id,player_name,role,batting_order,
                    position,is_starter
                ) VALUES (?,?,?,?, 'pitcher',0,'P',1)
                """,
                (game_id, opponent_team, int(starter["id"]), starter["name"]),
            )

    @staticmethod
    def _positions_for(hitters):
        available = {
            "C": ["C"],
            "IF": ["1B", "2B", "3B", "SS"],
            "OF": ["LF", "CF", "RF"],
        }
        assigned = []
        remaining = ["C", "1B", "2B", "3B", "SS", "LF", "CF", "RF", "DH"]
        for player in hitters:
            group = str(player.get("position_group") or "")
            preferred = str(player.get("pos") or "")
            options = available.get(group, [])
            position = preferred if preferred in remaining and preferred != "IF" and preferred != "OF" else None
            if position is None:
                position = next((slot for slot in options if slot in remaining), None)
            if position is None:
                position = "DH" if "DH" in remaining else remaining[0]
            remaining.remove(position)
            assigned.append(position)
        return assigned

    def simulate_game(self, game_id):
        """선수 능력치를 사용해 타석 단위 연습경기를 결정론적으로 진행한다."""
        game = self.game_details(game_id)
        if game["status"] == "completed":
            return self.load_game_result(game_id)
        if game["status"] != "scheduled":
            raise PracticeGameError("취소된 연습경기는 진행할 수 없습니다.")
        roster = self.prepared_lineup(game_id)
        managed_batters = [
            row for row in roster
            if row["team"] == self.managed_team and row["role"] == "batter"
        ]
        managed_pitchers = [
            row for row in roster
            if row["team"] == self.managed_team and row["role"] == "pitcher"
        ]
        if len(managed_batters) != 9 or len(managed_pitchers) != 1:
            raise PracticeGameError("경기 시작 전에 선발 타자 9명과 선발투수를 확정해야 합니다.")
        self._ensure_opponent_lineup(int(game_id), game["opponent_team"])
        roster = self.prepared_lineup(game_id)

        teams = (self.managed_team, game["opponent_team"])
        player_maps = {
            team: {int(player["id"]): player for player in self.available_players(team)}
            for team in teams
        }
        batting = {}
        starters = {}
        for team in teams:
            team_rows = [row for row in roster if row["team"] == team]
            batting[team] = [
                player_maps[team][int(row["player_id"])]
                for row in sorted(
                    (row for row in team_rows if row["role"] == "batter"),
                    key=lambda row: int(row["batting_order"]),
                )
            ]
            pitcher_row = next(row for row in team_rows if row["role"] == "pitcher")
            starters[team] = player_maps[team][int(pitcher_row["player_id"])]

        pitcher_pools = {}
        for team in teams:
            relievers = sorted(
                (
                    player for player in player_maps[team].values()
                    if player.get("position_group") == "P"
                    and not player["injury_days"]
                    and int(player["id"]) != int(starters[team]["id"])
                ),
                key=lambda player: (float(player["rating"]), -int(player["id"])),
                reverse=True,
            )
            pitcher_pools[team] = [starters[team], *relievers[:5]]

        managed_home = game["venue_type"] != "away"
        away_team = game["opponent_team"] if managed_home else self.managed_team
        home_team = self.managed_team if managed_home else game["opponent_team"]
        environment = build_game_environment(
            self.save_id,
            int(game_id),
            teams,
            home_team,
        )
        rng = random.Random(
            f"practice:{self.save_id}:{game_id}:{game['game_date']}:{game['opponent_team']}"
        )
        scores = {team: 0 for team in teams}
        batting_index = {team: 0 for team in teams}
        stats = {}
        plays = []
        sequence = 0
        innings = int(game["innings"])
        line_score = {team: [] for team in teams}

        def stat_for(team, player):
            key = (team, int(player["id"]))
            if key not in stats:
                order = next(
                    (
                        int(row["batting_order"])
                        for row in roster
                        if row["team"] == team
                        and int(row["player_id"]) == int(player["id"])
                    ),
                    0,
                )
                position = next(
                    (
                        str(row["position"])
                        for row in roster
                        if row["team"] == team
                        and int(row["player_id"]) == int(player["id"])
                    ),
                    "P" if player.get("position_group") == "P" else "",
                )
                stats[key] = {
                    "team": team, "player_id": int(player["id"]),
                    "player_name": player["name"],
                    "squad_group": player["squad_group"],
                    "batting_order": order, "position": position,
                    "plate_appearances": 0, "at_bats": 0, "runs": 0,
                    "hits": 0, "doubles": 0, "triples": 0,
                    "home_runs": 0, "walks": 0, "strikeouts": 0,
                    "rbi": 0, "innings_outs": 0, "hits_allowed": 0,
                    "runs_allowed": 0, "walks_allowed": 0,
                    "strikeouts_pitched": 0, "pitches": 0,
                }
            return stats[key]

        def add_play(inning, half, offense, batter, pitcher, code, description,
                     runs, outs_after):
            nonlocal sequence
            sequence += 1
            plays.append({
                "sequence_no": sequence, "inning": inning, "half": half,
                "offense_team": offense,
                "batter_id": int(batter["id"]) if batter else None,
                "batter_name": batter["name"] if batter else "",
                "pitcher_id": int(pitcher["id"]) if pitcher else None,
                "pitcher_name": pitcher["name"] if pitcher else "",
                "result_code": code, "description": description,
                "runs_scored": runs,
                "managed_score": scores[self.managed_team],
                "opponent_score": scores[game["opponent_team"]],
                "outs_after": outs_after,
            })

        def resolve_runners(bases, batter, outcome):
            scored = []
            if outcome == "BB":
                if bases[0] is not None:
                    if bases[1] is not None:
                        if bases[2] is not None:
                            scored.append(bases[2])
                        bases[2] = bases[1]
                    bases[1] = bases[0]
                bases[0] = batter
            elif outcome == "1B":
                if bases[2] is not None:
                    scored.append(bases[2])
                if bases[1] is not None:
                    if rng.random() < .62:
                        scored.append(bases[1])
                        bases[2] = None
                    else:
                        bases[2] = bases[1]
                else:
                    bases[2] = None
                bases[1] = bases[0]
                bases[0] = batter
            elif outcome == "2B":
                for runner in (bases[2], bases[1]):
                    if runner is not None:
                        scored.append(runner)
                bases[2] = bases[0]
                bases[1] = batter
                bases[0] = None
            elif outcome == "3B":
                scored.extend(runner for runner in bases if runner is not None)
                bases[:] = [None, None, batter]
            elif outcome == "HR":
                scored.extend(runner for runner in bases if runner is not None)
                scored.append(batter)
                bases[:] = [None, None, None]
            return scored

        max_innings = 11
        starter_innings = {
            team: max(
                1,
                round(
                    _pitcher_workload_limit(
                        starters[team], game["pitching_plan"], True
                    )["outs"] / 3
                ),
            )
            for team in teams
        }
        reliever_span = (
            1 if game["pitching_plan"] in {"불펜 데이", "투수 전원 점검"}
            else 2
        )
        active_pitcher_ids = {}
        for inning in range(1, max_innings + 1):
            for half, offense, defense in (
                ("초", away_team, home_team),
                ("말", home_team, away_team),
            ):
                if half == "말" and inning >= innings and scores[home_team] > scores[away_team]:
                    line_score[home_team].append("X")
                    break
                if inning <= starter_innings[defense]:
                    pitcher_index = 0
                else:
                    pitcher_index = 1 + (
                        inning - starter_innings[defense] - 1
                    ) // reliever_span
                pitcher_index = min(
                    pitcher_index, len(pitcher_pools[defense]) - 1
                )
                pitcher = pitcher_pools[defense][pitcher_index]
                if active_pitcher_ids.get(defense) != int(pitcher["id"]):
                    active_pitcher_ids[defense] = int(pitcher["id"])
                    add_play(
                        inning, half, offense, None, pitcher, "PITCH_CHANGE",
                        f"{inning}회{half} · {defense} 투수 {pitcher['name']} 등판",
                        0, 0,
                    )
                inning_start = scores[offense]
                bases = [None, None, None]
                outs = 0
                plate_count = 0
                while outs < 3 and plate_count < 30:
                    batter = batting[offense][batting_index[offense] % 9]
                    batting_index[offense] += 1
                    plate_count += 1
                    batter_stat = stat_for(offense, batter)
                    pitcher_stat = stat_for(defense, pitcher)
                    batter_stat["plate_appearances"] += 1
                    pitcher_stat["pitches"] += rng.randint(3, 7)

                    contact = float(batter.get("contact") or batter.get("con") or 10)
                    power = float(batter.get("power") or batter.get("pow") or 10)
                    eye = float(batter.get("plate_discipline") or batter.get("eye") or 10)
                    stuff = float(pitcher.get("pitcher_stuff") or 10)
                    command = float(pitcher.get("pitcher_command") or 10)
                    movement = float(pitcher.get("pitcher_movement") or 10)
                    form = pitcher_day_form(
                        environment,
                        self.save_id,
                        int(game_id),
                        defense,
                        int(pitcher["id"]),
                        is_reliever=int(pitcher["id"]) != int(starters[defense]["id"]),
                    )
                    adjustments = matchup_adjustments(
                        environment, offense, defense, form
                    )
                    fatigue_start = (
                        26
                        if int(pitcher["id"]) != int(starters[defense]["id"])
                        else 76
                    )
                    fatigue_penalty = max(
                        0.0,
                        (int(pitcher_stat["pitches"]) - fatigue_start) / 18.0,
                    )
                    offense_day = adjustments["offense"]
                    if inning > innings:
                        offense_day += 1.5
                    elif inning >= 7 and scores[offense] == 0:
                        offense_day += 2.0
                    pitching_day = adjustments["pitching"] - min(3.0, fatigue_penalty)
                    contact_edge = (
                        (contact - stuff) * .78
                        + (offense_day - pitching_day) * 1.15
                    )
                    power_edge = (
                        (power - movement) * .78
                        + (offense_day - pitching_day) * .80
                    )
                    eye_edge = (
                        (eye - command) * .78
                        + (offense_day * .45 - pitching_day) * 1.15
                    )
                    walk_p = max(
                        .028,
                        min(.16, .078 + eye_edge * .005),
                    )
                    strikeout_p = max(
                        .08,
                        min(.34, .19 - contact_edge * .011),
                    )
                    homer_p = max(
                        .008,
                        min(.09, .029 + power_edge * .004),
                    )
                    single_p = max(
                        .10,
                        min(.24, .158 + contact_edge * .006),
                    )
                    double_p = max(
                        .025,
                        min(.095, .052 + power_edge * .0025),
                    )
                    triple_p = .006 + max(0, float(batter.get("speed") or 10) - 12) * .001
                    roll = rng.random()
                    thresholds = (
                        (walk_p, "BB"),
                        (walk_p + strikeout_p, "K"),
                        (walk_p + strikeout_p + homer_p, "HR"),
                        (walk_p + strikeout_p + homer_p + triple_p, "3B"),
                        (walk_p + strikeout_p + homer_p + triple_p + double_p, "2B"),
                        (walk_p + strikeout_p + homer_p + triple_p + double_p + single_p, "1B"),
                    )
                    outcome = next((code for threshold, code in thresholds if roll < threshold), "OUT")
                    runs_before = scores[offense]
                    if outcome == "BB":
                        batter_stat["walks"] += 1
                        pitcher_stat["walks_allowed"] += 1
                        scored = resolve_runners(bases, batter, outcome)
                        description = f"{batter['name']}, 볼넷으로 출루합니다."
                    elif outcome in {"1B", "2B", "3B", "HR"}:
                        batter_stat["at_bats"] += 1
                        batter_stat["hits"] += 1
                        pitcher_stat["hits_allowed"] += 1
                        if outcome == "2B":
                            batter_stat["doubles"] += 1
                        elif outcome == "3B":
                            batter_stat["triples"] += 1
                        elif outcome == "HR":
                            batter_stat["home_runs"] += 1
                        scored = resolve_runners(bases, batter, outcome)
                        labels = {"1B": "안타", "2B": "2루타", "3B": "3루타", "HR": "홈런"}
                        description = f"{batter['name']}, {labels[outcome]}!"
                    else:
                        batter_stat["at_bats"] += 1
                        scored = []
                        outs += 1
                        pitcher_stat["innings_outs"] += 1
                        if outcome == "K":
                            batter_stat["strikeouts"] += 1
                            pitcher_stat["strikeouts_pitched"] += 1
                            description = f"{batter['name']}, 헛스윙 삼진."
                        else:
                            result = "내야 땅볼" if rng.random() < .55 else "외야 뜬공"
                            description = f"{batter['name']}, {result} 아웃."
                    if scored:
                        scores[offense] += len(scored)
                        batter_stat["rbi"] += len(scored)
                        pitcher_stat["runs_allowed"] += len(scored)
                        for runner in scored:
                            stat_for(offense, runner)["runs"] += 1
                        description += f" {len(scored)}득점."
                    add_play(
                        inning, half, offense, batter, pitcher, outcome,
                        description, scores[offense] - runs_before, outs,
                    )
                    if (
                        half == "말" and inning >= innings
                        and scores[home_team] > scores[away_team]
                    ):
                        add_play(
                            inning, half, offense, None, pitcher, "WALK_OFF",
                            f"{home_team}, 끝내기로 연습경기를 마칩니다.", 0, outs,
                        )
                        break
                line_score[offense].append(scores[offense] - inning_start)
                add_play(
                    inning, half, offense, None, pitcher, "HALF_END",
                    f"{inning}회{half} 종료 · {self.managed_team} "
                    f"{scores[self.managed_team]}–{scores[game['opponent_team']]} "
                    f"{game['opponent_team']}",
                    0, outs,
                )
                if (
                    half == "말" and inning >= innings
                    and scores[home_team] > scores[away_team]
                ):
                    break
            if inning >= innings and scores[home_team] != scores[away_team]:
                break

        result_payload = {
            "home_team": home_team,
            "away_team": away_team,
            "line_score": line_score,
            "managed_team": self.managed_team,
            "opponent_team": game["opponent_team"],
            "managed_score": scores[self.managed_team],
            "opponent_score": scores[game["opponent_team"]],
            "simulation_model": environment["model"],
            "historical_calibration": {
                "target_runs_per_team_game": environment["target_runs_per_team_game"],
                "favorite_loss_rate": environment["historical_favorite_loss_rate"],
                "one_run_game_rate": environment["historical_one_run_game_rate"],
            },
        }
        self._persist_simulation(game, plays, stats.values(), result_payload)
        return self.load_game_result(game_id)

    def _persist_simulation(self, game, plays, stats, result_payload):
        game_id = int(game["id"])
        now = datetime.now().isoformat(timespec="seconds")
        stat_rows = list(stats)
        with self._connect() as connection:
            connection.execute("DELETE FROM practice_game_plays WHERE game_id=?", (game_id,))
            connection.execute("DELETE FROM practice_game_player_stats WHERE game_id=?", (game_id,))
            connection.executemany(
                """
                INSERT INTO practice_game_plays (
                    game_id,sequence_no,inning,half,offense_team,batter_id,
                    batter_name,pitcher_id,pitcher_name,result_code,description,
                    runs_scored,managed_score,opponent_score,outs_after
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                [
                    (
                        game_id, play["sequence_no"], play["inning"], play["half"],
                        play["offense_team"], play["batter_id"], play["batter_name"],
                        play["pitcher_id"], play["pitcher_name"], play["result_code"],
                        play["description"], play["runs_scored"],
                        play["managed_score"], play["opponent_score"], play["outs_after"],
                    )
                    for play in plays
                ],
            )
            stat_columns = (
                "team", "player_id", "player_name", "squad_group",
                "batting_order", "position", "plate_appearances", "at_bats",
                "runs", "hits", "doubles", "triples", "home_runs", "walks",
                "strikeouts", "rbi", "innings_outs", "hits_allowed",
                "runs_allowed", "walks_allowed", "strikeouts_pitched", "pitches",
            )
            connection.executemany(
                f"""
                INSERT INTO practice_game_player_stats (
                    game_id,{','.join(stat_columns)}
                ) VALUES ({','.join('?' for _ in range(len(stat_columns) + 1))})
                """,
                [tuple([game_id, *[stat[column] for column in stat_columns]]) for stat in stat_rows],
            )
            connection.execute(
                """
                UPDATE practice_games
                SET status='completed', managed_score=?, opponent_score=?,
                    result_json=?, updated_at=?
                WHERE id=?
                """,
                (
                    result_payload["managed_score"], result_payload["opponent_score"],
                    json.dumps(result_payload, ensure_ascii=False, separators=(",", ":")),
                    now, game_id,
                ),
            )
            for stat in stat_rows:
                if stat["team"] != self.managed_team:
                    continue
                workload = int(stat["innings_outs"]) + int(stat["plate_appearances"])
                if workload <= 0:
                    continue
                fatigue_gain = min(
                    12,
                    2 + int(stat["innings_outs"]) // 3
                    + int(stat["plate_appearances"]) // 2,
                )
                condition_cost = min(10, 2 + fatigue_gain // 2)
                connection.execute(
                    """
                    INSERT OR IGNORE INTO player_simulation_states (
                        save_id,player_id,team,condition,fatigue,training_points,
                        injury_days,match_sharpness,morale,injury_risk,
                        squad_group,injury_type,last_updated
                    ) VALUES (?,?,?,85,0,0,0,55,75,5,?,'',?)
                    """,
                    (
                        self.save_id, stat["player_id"], self.managed_team,
                        stat["squad_group"], game["game_date"],
                    ),
                )
                connection.execute(
                    """
                    UPDATE player_simulation_states
                    SET condition=MAX(35,condition-?),
                        fatigue=MIN(100,fatigue+?),
                        match_sharpness=MIN(100,match_sharpness+5),
                        last_updated=?
                    WHERE save_id=? AND player_id=?
                    """,
                    (
                        condition_cost, fatigue_gain, game["game_date"],
                        self.save_id, stat["player_id"],
                    ),
                )

    def load_game_result(self, game_id):
        game = self.game_details(game_id)
        with self._connect() as connection:
            plays = [
                dict(row) for row in connection.execute(
                    "SELECT * FROM practice_game_plays WHERE game_id=? ORDER BY sequence_no",
                    (int(game_id),),
                ).fetchall()
            ]
            stats = [
                dict(row) for row in connection.execute(
                    """
                    SELECT * FROM practice_game_player_stats
                    WHERE game_id=?
                    ORDER BY team, batting_order=0, batting_order, player_name
                    """,
                    (int(game_id),),
                ).fetchall()
            ]
        try:
            result = json.loads(game.get("result_json") or "{}")
        except json.JSONDecodeError:
            result = {}
        return {"game": game, "plays": plays, "stats": stats, "result": result}

    def start_live_game(self, game_id):
        """결과를 선계산하지 않고 첫 투구 직전의 경기 상태를 만든다."""
        game = self.game_details(game_id)
        if game["status"] == "completed":
            return {"status": "completed", **self.load_game_result(game_id)["result"]}
        existing = self.load_live_state(game_id)
        if existing and existing.get("status") == "live":
            return existing
        if game["status"] not in {"scheduled", "live"}:
            raise PracticeGameError("진행할 수 없는 연습경기입니다.")
        roster = self.prepared_lineup(game_id)
        managed_batters = [
            row for row in roster
            if row["team"] == self.managed_team and row["role"] == "batter"
        ]
        managed_pitcher = next(
            (
                row for row in roster
                if row["team"] == self.managed_team and row["role"] == "pitcher"
            ),
            None,
        )
        if len(managed_batters) != 9 or managed_pitcher is None:
            raise PracticeGameError("선발 타자 9명과 선발투수를 먼저 확정하세요.")
        self._ensure_opponent_lineup(int(game_id), game["opponent_team"])
        roster = self.prepared_lineup(game_id)
        opponent_pitcher = next(
            row for row in roster
            if row["team"] == game["opponent_team"] and row["role"] == "pitcher"
        )
        managed_home = game["venue_type"] != "away"
        away_team = game["opponent_team"] if managed_home else self.managed_team
        home_team = self.managed_team if managed_home else game["opponent_team"]
        batting_orders = {
            team: [
                int(row["player_id"])
                for row in sorted(
                    (
                        row for row in roster
                        if row["team"] == team and row["role"] == "batter"
                    ),
                    key=lambda row: int(row["batting_order"]),
                )
            ]
            for team in (self.managed_team, game["opponent_team"])
        }
        state = {
            "status": "live",
            "game_id": int(game_id),
            "inning": 1,
            "half": "초",
            "outs": 0,
            "balls": 0,
            "strikes": 0,
            "bases": {"1": None, "2": None, "3": None},
            "scores": {self.managed_team: 0, game["opponent_team"]: 0},
            "away_team": away_team,
            "home_team": home_team,
            "offense_team": away_team,
            "defense_team": home_team,
            "batting_orders": batting_orders,
            "batting_index": {self.managed_team: 0, game["opponent_team"]: 0},
            "current_pitcher_ids": {
                self.managed_team: int(managed_pitcher["player_id"]),
                game["opponent_team"]: int(opponent_pitcher["player_id"]),
            },
            "starting_pitcher_ids": {
                self.managed_team: int(managed_pitcher["player_id"]),
                game["opponent_team"]: int(opponent_pitcher["player_id"]),
            },
            "used_pitcher_ids": {
                self.managed_team: [int(managed_pitcher["player_id"])],
                game["opponent_team"]: [int(opponent_pitcher["player_id"])],
            },
            "game_environment": build_game_environment(
                self.save_id,
                int(game_id),
                (self.managed_team, game["opponent_team"]),
                home_team,
            ),
            "pitch_no": 0,
            "last_pitch_type": "",
            "last_pitch_speed": 0,
            "half_start_score": 0,
            "line_score": {self.managed_team: [], game["opponent_team"]: []},
            "pending_steal": False,
            "plays": [],
            "stats": {},
            "last_event": None,
        }
        state = self._refresh_live_participants(state)
        self._save_live_state(game_id, state)
        with self._connect() as connection:
            connection.execute(
                "UPDATE practice_games SET status='live',updated_at=? WHERE id=?",
                (datetime.now().isoformat(timespec="seconds"), int(game_id)),
            )
        return state

    def load_live_state(self, game_id):
        with self._connect() as connection:
            row = connection.execute(
                "SELECT state_json FROM practice_game_live_states WHERE game_id=?",
                (int(game_id),),
            ).fetchone()
        if row is None:
            return None
        try:
            return json.loads(row["state_json"])
        except json.JSONDecodeError:
            return None

    def _save_live_state(self, game_id, state):
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO practice_game_live_states (game_id,state_json,updated_at)
                VALUES (?,?,?)
                ON CONFLICT(game_id) DO UPDATE SET
                    state_json=excluded.state_json,
                    updated_at=excluded.updated_at
                """,
                (
                    int(game_id),
                    json.dumps(state, ensure_ascii=False, separators=(",", ":")),
                    datetime.now().isoformat(timespec="seconds"),
                ),
            )

    def _live_context(self, game_id, state):
        game = self.game_details(game_id)
        teams = (self.managed_team, game["opponent_team"])
        maps = {
            team: {int(player["id"]): player for player in self.available_players(team)}
            for team in teams
        }
        return game, maps

    def _refresh_live_participants(self, state):
        game, maps = self._live_context(state["game_id"], state)
        offense = state["offense_team"]
        defense = state["defense_team"]
        order = state["batting_orders"][offense]
        batter_id = int(order[int(state["batting_index"][offense]) % 9])
        pitcher_id = int(state["current_pitcher_ids"][defense])
        state["batter_id"] = batter_id
        state["batter_name"] = maps[offense][batter_id]["name"]
        state["pitcher_id"] = pitcher_id
        state["pitcher_name"] = maps[defense][pitcher_id]["name"]
        state["managed_score"] = int(state["scores"][self.managed_team])
        state["opponent_score"] = int(state["scores"][game["opponent_team"]])
        return state

    @staticmethod
    def _live_stat(state, team, player):
        key = f"{team}|{int(player['id'])}"
        if key not in state["stats"]:
            order = state["batting_orders"].get(team, [])
            batting_order = order.index(int(player["id"])) + 1 if int(player["id"]) in order else 0
            state["stats"][key] = {
                "team": team, "player_id": int(player["id"]),
                "player_name": player["name"],
                "squad_group": player["squad_group"],
                "batting_order": batting_order,
                "position": "P" if player.get("position_group") == "P" else "",
                "plate_appearances": 0, "at_bats": 0, "runs": 0,
                "hits": 0, "doubles": 0, "triples": 0,
                "home_runs": 0, "walks": 0, "strikeouts": 0, "rbi": 0,
                "innings_outs": 0, "hits_allowed": 0, "runs_allowed": 0,
                "walks_allowed": 0, "strikeouts_pitched": 0, "pitches": 0,
            }
        return state["stats"][key]

    def _live_event(self, state, code, description, *, runs=0):
        game = self.game_details(state["game_id"])
        event = {
            "sequence_no": len(state["plays"]) + 1,
            "inning": int(state["inning"]),
            "half": state["half"],
            "offense_team": state["offense_team"],
            "batter_id": state.get("batter_id"),
            "batter_name": state.get("batter_name", ""),
            "pitcher_id": state.get("pitcher_id"),
            "pitcher_name": state.get("pitcher_name", ""),
            "result_code": code,
            "description": description,
            "runs_scored": int(runs),
            "managed_score": int(state["scores"][self.managed_team]),
            "opponent_score": int(state["scores"][game["opponent_team"]]),
            "outs_after": int(state["outs"]),
            "bases_after": dict(state["bases"]),
            "balls": int(state["balls"]),
            "strikes": int(state["strikes"]),
            "pitch_type": state.get("last_pitch_type", ""),
            "pitch_speed": int(state.get("last_pitch_speed") or 0),
        }
        state["plays"].append(event)
        state["last_event"] = event
        return event

    def request_steal(self, game_id):
        state = self.load_live_state(game_id)
        if not state or state.get("status") != "live":
            raise PracticeGameError("진행 중인 경기가 없습니다.")
        if state["offense_team"] != self.managed_team:
            raise PracticeGameError("우리 팀 공격 때만 도루를 지시할 수 있습니다.")
        if state["bases"]["1"] is None or state["bases"]["2"] is not None:
            raise PracticeGameError("1루 주자가 있고 2루가 비어 있을 때 도루할 수 있습니다.")
        state["pending_steal"] = True
        self._save_live_state(game_id, state)
        return state

    def change_pitcher(self, game_id, player_id):
        state = self.load_live_state(game_id)
        if not state or state.get("status") != "live":
            raise PracticeGameError("진행 중인 경기가 없습니다.")
        if state["defense_team"] != self.managed_team:
            raise PracticeGameError("우리 팀 수비 때만 투수를 교체할 수 있습니다.")
        player = next(
            (
                item for item in self.available_players()
                if int(item["id"]) == int(player_id)
            ),
            None,
        )
        if player is None or player.get("position_group") != "P" or player["injury_days"]:
            raise PracticeGameError("교체 가능한 투수가 아닙니다.")
        state["current_pitcher_ids"][self.managed_team] = int(player_id)
        used = state.setdefault("used_pitcher_ids", {}).setdefault(
            self.managed_team, []
        )
        if int(player_id) not in used:
            used.append(int(player_id))
        state = self._refresh_live_participants(state)
        self._live_event(
            state,
            "PITCH_CHANGE",
            f"감독이 투수를 교체합니다. {player['name']} 등판.",
        )
        self._save_live_state(game_id, state)
        return state

    def advance_live_pitch(self, game_id, offense_strategy="균형", defense_strategy="균형"):
        """한 번 호출할 때 정확히 한 투구 또는 도루 장면만 진행한다."""
        state = self.load_live_state(game_id)
        if state is None:
            state = self.start_live_game(game_id)
        if state.get("status") == "completed":
            return state
        game, maps = self._live_context(game_id, state)
        state = self._refresh_live_participants(state)
        pitching_change = self._maybe_auto_pitcher_change(state, game, maps)
        if pitching_change is not None:
            self._save_live_state(game_id, state)
            return {"state": state, "event": pitching_change}
        offense = state["offense_team"]
        defense = state["defense_team"]
        if offense != self.managed_team:
            offense_strategy = "균형"
        if defense != self.managed_team:
            defense_strategy = "균형"
        batter = maps[offense][int(state["batter_id"])]
        pitcher = maps[defense][int(state["pitcher_id"])]
        batter_stat = self._live_stat(state, offense, batter)
        pitcher_stat = self._live_stat(state, defense, pitcher)
        state["pitch_no"] = int(state["pitch_no"]) + 1
        rng = random.Random(
            f"live:{self.save_id}:{game_id}:{state['pitch_no']}:{state['inning']}:{state['half']}"
        )

        pitch_options = (
            ("포심", "pitch_four_seam", 1.00),
            ("싱커", "pitch_sinker", .96),
            ("커터", "pitch_cutter", .95),
            ("체인지업", "pitch_changeup", .88),
            ("슬라이더", "pitch_slider", .90),
            ("커브", "pitch_curve", .82),
            ("스플리터", "pitch_splitter", .91),
            ("스위퍼", "pitch_sweeper", .87),
            ("너클볼", "pitch_knuckleball", .76),
        )
        available_pitches = [
            (name, max(1, int(pitcher.get(key) or 0)), speed_factor)
            for name, key, speed_factor in pitch_options
            if int(pitcher.get(key) or 0) > 0
        ] or [("포심", 10, 1.0)]
        visual_rng = random.Random(
            f"pitch-meta:{self.save_id}:{game_id}:{state['pitch_no']}"
        )
        selected_pitch = visual_rng.choices(
            available_pitches,
            weights=[pitch[1] for pitch in available_pitches],
            k=1,
        )[0]
        average_velocity = float(
            pitcher.get("pitcher_avg_velocity")
            or (136.0 + float(pitcher.get("pitcher_velocity") or 10) * .65)
        )
        state["last_pitch_type"] = selected_pitch[0]
        state["last_pitch_speed"] = max(
            105,
            round(average_velocity * selected_pitch[2] + visual_rng.uniform(-2.4, 2.4)),
        )

        if state.get("pending_steal"):
            state["pending_steal"] = False
            state["last_pitch_type"] = ""
            state["last_pitch_speed"] = 0
            runner_id = state["bases"]["1"]
            runner = maps[offense][int(runner_id)]
            speed = float(runner.get("speed") or 10)
            success = rng.random() < max(.35, min(.82, .56 + (speed - 10) * .025))
            if success:
                state["bases"]["2"] = runner_id
                state["bases"]["1"] = None
                event = self._live_event(
                    state, "SB", f"{runner['name']} 2루 도루 성공!"
                )
            else:
                state["bases"]["1"] = None
                state["outs"] = int(state["outs"]) + 1
                event = self._live_event(
                    state, "CS", f"{runner['name']} 도루 실패, 태그 아웃."
                )
                if state["outs"] >= 3:
                    self._advance_live_half(state, game)
            state = self._refresh_live_participants(state)
            self._save_live_state(game_id, state)
            return {"state": state, "event": event}

        command = float(pitcher.get("pitcher_command") or 10)
        stuff = float(pitcher.get("pitcher_stuff") or 10)
        contact = float(batter.get("contact") or batter.get("con") or 10)
        eye = float(batter.get("plate_discipline") or batter.get("eye") or 10)
        power = float(batter.get("power") or batter.get("pow") or 10)
        movement = float(pitcher.get("pitcher_movement") or 10)
        environment = state.get("game_environment") or build_game_environment(
            self.save_id,
            int(game_id),
            (self.managed_team, game["opponent_team"]),
            state["home_team"],
        )
        state["game_environment"] = environment
        is_reliever = int(pitcher["id"]) != int(
            state.get("starting_pitcher_ids", {}).get(defense, pitcher["id"])
        )
        form = pitcher_day_form(
            environment,
            self.save_id,
            int(game_id),
            defense,
            int(pitcher["id"]),
            is_reliever=is_reliever,
        )
        adjustments = matchup_adjustments(environment, offense, defense, form)
        if int(state["inning"]) > int(game["innings"]):
            adjustments["offense"] += 1.5
        elif (
            int(state["inning"]) >= 7
            and int(state["scores"][offense]) == 0
        ):
            adjustments["offense"] += 2.0
        fatigue_start = 26 if is_reliever else 76
        fatigue_penalty = max(
            0.0,
            (int(pitcher_stat["pitches"]) - fatigue_start) / 18.0,
        )
        offense_day = adjustments["offense"]
        pitching_day = adjustments["pitching"] - min(3.0, fatigue_penalty)
        # 선수 고유 능력을 당일 폼보다 중심에 둔다. 컨택-구위,
        # 파워-무브먼트, 선구안-제구가 서로 다른 결과를 만들도록 분리한다.
        contact_edge = (
            (contact - stuff) * 1.30
            + (offense_day - pitching_day) * .95
        )
        power_edge = (
            (power - movement) * 1.20
            + (offense_day - pitching_day) * .85
        )
        effective_eye = 10 + (eye - 10) * 1.15 + offense_day * .40
        effective_command = (
            10 + (command - 10) * 1.20 + pitching_day * .75
        )
        ball_probability = max(
            .36,
            min(.60, .49 + (10 - effective_command) * .018),
        )
        if defense_strategy == "유인구":
            ball_probability += .08
        elif defense_strategy == "공격적 승부":
            ball_probability -= .06
        in_zone = rng.random() >= ball_probability
        swing_probability = .66 if in_zone else .30
        if offense_strategy == "적극 타격":
            swing_probability += .18
        elif offense_strategy == "신중 승부":
            swing_probability -= .16
        elif offense_strategy == "번트":
            swing_probability = .88
        if not in_zone:
            # 선구안이 좋은 타자는 존 밖 공을 참아 볼넷을 만들고,
            # 낮은 타자는 같은 공에 더 자주 배트가 나간다.
            swing_probability -= (effective_eye - 10) * .025
        elif int(state["strikes"]) >= 2:
            # 2스트라이크에서는 존 안 공을 적극적으로 커트한다.
            swing_probability += .18
        swing = rng.random() < max(.08, min(.92, swing_probability))
        pitcher_stat["pitches"] += 1

        plate_result = None
        if not swing:
            if in_zone:
                state["strikes"] = int(state["strikes"]) + 1
                description = f"{pitcher['name']}의 공, 스트라이크 콜."
                code = "CALLED_STRIKE"
            else:
                state["balls"] = int(state["balls"]) + 1
                description = "존을 벗어나는 공, 볼."
                code = "BALL"
        else:
            contact_probability = max(
                .40,
                min(.92, .74 + contact_edge * .022),
            )
            if int(state["strikes"]) >= 2:
                contact_probability = min(.975, contact_probability + .16)
            if offense_strategy == "번트":
                contact_probability += .08
            if rng.random() > contact_probability:
                state["strikes"] = int(state["strikes"]) + 1
                description = f"{batter['name']} 배트가 헛돕니다."
                code = "SWINGING_STRIKE"
            elif rng.random() < .50:
                # 2스트라이크 뒤 파울은 삼진이나 인플레이가 아니라
                # 실제 야구처럼 타석과 투구 수를 그대로 연장한다.
                if int(state["strikes"]) < 2:
                    state["strikes"] = int(state["strikes"]) + 1
                description = f"{batter['name']} 파울."
                code = "FOUL"
            else:
                if offense_strategy == "번트":
                    if state["bases"]["1"] is not None and rng.random() < .72:
                        runner_id = state["bases"]["1"]
                        if state["bases"]["2"] is None:
                            state["bases"]["2"] = runner_id
                        state["bases"]["1"] = None
                        plate_result = "SAC"
                        description = f"{batter['name']} 희생번트 성공, 주자가 진루합니다."
                    else:
                        plate_result = "OUT"
                        description = f"{batter['name']} 번트 타구 아웃."
                else:
                    hit_roll = rng.random()
                    home_run_p = max(
                        .010, min(.065, .035 + power_edge * .0025)
                    )
                    double_p = max(
                        .035, min(.085, .056 + power_edge * .0015)
                    )
                    triple_p = max(
                        .003,
                        min(
                            .015,
                            .006
                            + max(0, float(batter.get("speed") or 10) - 12)
                            * .001,
                        ),
                    )
                    single_p = max(
                        .140, min(.270, .210 + contact_edge * .006)
                    )
                    defensive_players = [
                        maps[defense][int(player_id)]
                        for player_id in state["batting_orders"][defense]
                    ]
                    defense_fielding = sum(
                        float(player.get("fielding_judgment") or 10)
                        for player in defensive_players
                    ) / max(1, len(defensive_players))
                    error_p = max(
                        .010, min(.035, .022 + (11 - defense_fielding) * .002)
                    )
                    if hit_roll < home_run_p:
                        plate_result = "HR"
                    elif hit_roll < home_run_p + double_p:
                        plate_result = "2B"
                    elif hit_roll < home_run_p + double_p + triple_p:
                        plate_result = "3B"
                    elif hit_roll < home_run_p + double_p + triple_p + single_p:
                        plate_result = "1B"
                    elif rng.random() < error_p:
                        plate_result = "ROE"
                    else:
                        plate_result = "OUT"
                    description = ""
                code = plate_result

        if int(state["balls"]) >= 4:
            plate_result = "BB"
            code = "BB"
            description = f"{batter['name']} 볼넷 출루."
        elif int(state["strikes"]) >= 3:
            plate_result = "K"
            code = "K"
            description = f"{batter['name']} 삼진 아웃."

        runs = 0
        if plate_result is not None:
            runs = self._resolve_live_plate(
                state, maps, offense, defense, batter, pitcher,
                batter_stat, pitcher_stat, plate_result, rng,
            )
            if plate_result in {"1B", "2B", "3B", "HR"}:
                label = {"1B": "안타", "2B": "2루타", "3B": "3루타", "HR": "홈런"}[plate_result]
                description = f"{batter['name']} {label}!"
                if runs:
                    description += f" {runs}득점."
            elif plate_result == "ROE":
                description = f"{batter['name']}의 타구, 수비 실책으로 출루합니다."
                if runs:
                    description += f" {runs}득점."
            if plate_result == "OUT":
                if runs:
                    description = f"{batter['name']} 희생플라이, 주자가 홈을 밟습니다."
                else:
                    description = f"{batter['name']} 타구, {'내야 땅볼' if rng.random() < .55 else '외야 뜬공'} 아웃."
            state["batting_index"][offense] = int(state["batting_index"][offense]) + 1
            state["balls"] = 0
            state["strikes"] = 0

        event = self._live_event(state, code, description, runs=runs)
        if self._live_game_should_end(state, game):
            self._complete_live_game(state, game)
        elif int(state["outs"]) >= 3:
            self._advance_live_half(state, game)
            if self._live_game_should_end(state, game):
                self._complete_live_game(state, game)
        state = self._refresh_live_participants(state)
        self._save_live_state(game_id, state)
        return {"state": state, "event": event}

    def _maybe_auto_pitcher_change(self, state, game, maps):
        """2025 사용량과 경기 계획을 넘긴 투수를 타석 종료 뒤 교체한다."""
        if (
            int(state.get("balls") or 0) != 0
            or int(state.get("strikes") or 0) != 0
        ):
            return None
        defense = state["defense_team"]
        pitcher_id = int(state["current_pitcher_ids"][defense])
        pitcher = maps[defense][pitcher_id]
        starter_id = int(
            state.get("starting_pitcher_ids", {}).get(defense, pitcher_id)
        )
        is_starter = pitcher_id == starter_id
        stat = self._live_stat(state, defense, pitcher)
        limit = _pitcher_workload_limit(
            pitcher, game.get("pitching_plan"), is_starter
        )
        recorded_outs = int(stat.get("innings_outs") or 0)
        recorded_pitches = int(stat.get("pitches") or 0)
        if is_starter and str(game.get("pitching_plan")) == "정규 선발 운용":
            reached_pitch_target = recorded_pitches >= int(limit["pitches"])
            reached_usage_window = (
                recorded_outs >= int(limit["outs"])
                and recorded_pitches >= round(int(limit["pitches"]) * .72)
            )
            reached_hard_inning_cap = recorded_outs >= 21
            if not (
                reached_pitch_target
                or reached_usage_window
                or reached_hard_inning_cap
            ):
                return None
        elif (
            recorded_outs < int(limit["outs"])
            and recorded_pitches < int(limit["pitches"])
        ):
            return None

        used_by_team = state.setdefault("used_pitcher_ids", {})
        used = {
            int(value)
            for value in used_by_team.setdefault(defense, [starter_id])
        }
        candidates = [
            player for player in maps[defense].values()
            if player.get("position_group") == "P"
            and not player.get("injury_days")
            and int(player["id"]) not in used
        ]
        candidates.sort(
            key=lambda player: (float(player.get("rating") or 0), -int(player["id"])),
            reverse=True,
        )
        if not candidates:
            return None
        replacement = candidates[0]
        replacement_id = int(replacement["id"])
        state["current_pitcher_ids"][defense] = replacement_id
        used_by_team[defense].append(replacement_id)
        self._refresh_live_participants(state)
        return self._live_event(
            state,
            "PITCH_CHANGE",
            (
                f"{pitcher['name']}의 예정 투구량을 채웠습니다. "
                f"{defense}, {replacement['name']}으로 투수를 교체합니다."
            ),
        )

    def _resolve_live_plate(
        self, state, maps, offense, defense, batter, pitcher,
        batter_stat, pitcher_stat, result, rng,
    ):
        batter_stat["plate_appearances"] += 1
        bases = state["bases"]
        scored_ids = []
        if result == "BB":
            batter_stat["walks"] += 1
            pitcher_stat["walks_allowed"] += 1
            if bases["1"] is not None:
                if bases["2"] is not None:
                    if bases["3"] is not None:
                        scored_ids.append(bases["3"])
                    bases["3"] = bases["2"]
                bases["2"] = bases["1"]
            bases["1"] = int(batter["id"])
        elif result in {"1B", "2B", "3B", "HR"}:
            batter_stat["at_bats"] += 1
            batter_stat["hits"] += 1
            pitcher_stat["hits_allowed"] += 1
            if result == "2B":
                batter_stat["doubles"] += 1
            elif result == "3B":
                batter_stat["triples"] += 1
            elif result == "HR":
                batter_stat["home_runs"] += 1
            if result == "1B":
                runner_first = bases["1"]
                runner_second = bases["2"]
                runner_third = bases["3"]
                bases.update({"1": int(batter["id"]), "2": None, "3": None})
                if runner_third is not None:
                    scored_ids.append(runner_third)
                second_scores = .86 + (.08 if int(state["outs"]) == 2 else 0.0)
                if runner_second is not None and rng.random() < second_scores:
                    scored_ids.append(runner_second)
                else:
                    bases["3"] = runner_second
                if runner_first is not None:
                    runner = maps[offense][int(runner_first)]
                    first_to_third = max(
                        .18,
                        min(
                            .50,
                            .43 + (float(runner.get("speed") or 10) - 10) * .018,
                        ),
                    )
                    if bases["3"] is None and rng.random() < first_to_third:
                        bases["3"] = runner_first
                    else:
                        bases["2"] = runner_first
            elif result == "2B":
                runner_first = bases["1"]
                scored_ids.extend(
                    runner for runner in (bases["3"], bases["2"])
                    if runner is not None
                )
                bases["3"] = None
                if runner_first is not None:
                    runner = maps[offense][int(runner_first)]
                    first_scores = max(
                        .30,
                        min(
                            .78,
                            .70
                            + (.08 if int(state["outs"]) == 2 else 0.0)
                            + (float(runner.get("speed") or 10) - 10) * .018,
                        ),
                    )
                    if rng.random() < first_scores:
                        scored_ids.append(runner_first)
                    else:
                        bases["3"] = runner_first
                bases["2"] = int(batter["id"])
                bases["1"] = None
            elif result == "3B":
                scored_ids.extend(runner for runner in bases.values() if runner is not None)
                bases.update({"1": None, "2": None, "3": int(batter["id"])})
            else:
                scored_ids.extend(runner for runner in bases.values() if runner is not None)
                scored_ids.append(int(batter["id"]))
                bases.update({"1": None, "2": None, "3": None})
        elif result == "ROE":
            batter_stat["at_bats"] += 1
            if bases["3"] is not None:
                scored_ids.append(bases["3"])
            bases["3"] = bases["2"]
            bases["2"] = bases["1"]
            bases["1"] = int(batter["id"])
        elif result in {"K", "OUT", "SAC"}:
            if result != "SAC":
                batter_stat["at_bats"] += 1
            outs_before = int(state["outs"])
            if result == "OUT" and outs_before < 2:
                if bases["3"] is not None and rng.random() < .58:
                    scored_ids.append(bases["3"])
                    bases["3"] = None
                if bases["2"] is not None and bases["3"] is None:
                    advancement_roll = rng.random()
                    if advancement_roll < .08:
                        scored_ids.append(bases["2"])
                        bases["2"] = None
                    elif advancement_roll < .38:
                        bases["3"] = bases["2"]
                        bases["2"] = None
                if (
                    bases["1"] is not None
                    and bases["2"] is None
                    and rng.random() < .18
                ):
                    bases["2"] = bases["1"]
                    bases["1"] = None
            state["outs"] = int(state["outs"]) + 1
            pitcher_stat["innings_outs"] += 1
            if result == "K":
                batter_stat["strikeouts"] += 1
                pitcher_stat["strikeouts_pitched"] += 1
        runs = len(scored_ids)
        if runs:
            state["scores"][offense] = int(state["scores"][offense]) + runs
            batter_stat["rbi"] += runs
            pitcher_stat["runs_allowed"] += runs
            for runner_id in scored_ids:
                runner = maps[offense][int(runner_id)]
                self._live_stat(state, offense, runner)["runs"] += 1
        return runs

    def _advance_live_half(self, state, game):
        offense = state["offense_team"]
        inning_runs = int(state["scores"][offense]) - int(state["half_start_score"])
        state["line_score"][offense].append(inning_runs)
        state["outs"] = 0
        state["balls"] = 0
        state["strikes"] = 0
        state["bases"] = {"1": None, "2": None, "3": None}
        if state["half"] == "초":
            state["half"] = "말"
            state["offense_team"] = state["home_team"]
            state["defense_team"] = state["away_team"]
        else:
            state["half"] = "초"
            state["inning"] = int(state["inning"]) + 1
            state["offense_team"] = state["away_team"]
            state["defense_team"] = state["home_team"]
        state["half_start_score"] = int(state["scores"][state["offense_team"]])

    @staticmethod
    def _live_game_should_end(state, game):
        innings = int(game["innings"])
        max_innings = 11
        inning = int(state["inning"])
        home = state["home_team"]
        away = state["away_team"]
        if inning < innings:
            return False
        if (
            state["half"] == "초"
            and int(state["outs"]) >= 3
            and int(state["scores"][home]) > int(state["scores"][away])
        ):
            return True
        if state["half"] == "말" and int(state["scores"][home]) > int(state["scores"][away]):
            return True
        return (
            state["half"] == "말"
            and int(state["outs"]) >= 3
            and (
                int(state["scores"][home]) != int(state["scores"][away])
                or inning >= max_innings
            )
        )

    def _complete_live_game(self, state, game):
        offense = state["offense_team"]
        if int(state["outs"]) >= 3:
            inning_runs = int(state["scores"][offense]) - int(state["half_start_score"])
            if len(state["line_score"][offense]) < int(state["inning"]):
                state["line_score"][offense].append(inning_runs)
        state["status"] = "completed"
        result_payload = {
            "home_team": state["home_team"],
            "away_team": state["away_team"],
            "line_score": state["line_score"],
            "managed_team": self.managed_team,
            "opponent_team": game["opponent_team"],
            "managed_score": int(state["scores"][self.managed_team]),
            "opponent_score": int(state["scores"][game["opponent_team"]]),
            "simulation_model": state["game_environment"]["model"],
            "historical_calibration": {
                "target_runs_per_team_game": state["game_environment"][
                    "target_runs_per_team_game"
                ],
                "favorite_loss_rate": state["game_environment"][
                    "historical_favorite_loss_rate"
                ],
                "one_run_game_rate": state["game_environment"][
                    "historical_one_run_game_rate"
                ],
            },
        }
        self._persist_simulation(
            game, state["plays"], state["stats"].values(), result_payload
        )

    def record_result(self, game_id, managed_score, opponent_score, result=None):
        """향후 경기 엔진이 사용할 결과 저장 진입점."""
        managed_score = int(managed_score)
        opponent_score = int(opponent_score)
        if managed_score < 0 or opponent_score < 0:
            raise PracticeGameError("득점은 0 이상이어야 합니다.")
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT status FROM practice_games
                WHERE id=? AND save_id=? AND managed_team=?
                """,
                (int(game_id), self.save_id, self.managed_team),
            ).fetchone()
            if row is None:
                raise PracticeGameError("연습경기를 찾을 수 없습니다.")
            if row["status"] == "cancelled":
                raise PracticeGameError("취소된 경기에는 결과를 기록할 수 없습니다.")
            connection.execute(
                """
                UPDATE practice_games
                SET status='completed', managed_score=?, opponent_score=?,
                    result_json=?, updated_at=?
                WHERE id=?
                """,
                (
                    managed_score, opponent_score,
                    json.dumps(result or {}, ensure_ascii=False, separators=(",", ":")),
                    datetime.now().isoformat(timespec="seconds"), int(game_id),
                ),
            )

    def calendar_events(self, game_date):
        events = []
        for game in self.games_on(game_date):
            venue = VENUE_TYPES.get(game["venue_type"], game["venue_type"])
            if game["status"] == "completed":
                score = f"{game['managed_score']}–{game['opponent_score']}"
                title = f"연습경기 종료 · {game['opponent_team']} {score}"
                detail = f"{game['stadium']}에서 치른 연습경기가 종료되었습니다."
            else:
                title = (
                    f"진행 중 · {game['opponent_team']}"
                    if game["status"] == "live"
                    else f"연습경기 · {game['opponent_team']}"
                )
                detail = (
                    f"{game['start_time']} · {venue} · {game['innings']}이닝 · "
                    f"{game['stadium']}"
                )
            events.append({
                "event_id": f"practice_game_{game['id']}",
                "category": "연습경기",
                "title": title,
                "detail": detail,
                "task": (
                    "경기 화면으로 돌아가 투구 단위 진행을 계속하세요."
                    if game["status"] == "live"
                    else f"{game['purpose']} · {game['lineup_policy']} · "
                    f"{game['pitching_plan']}"
                ),
                "importance": "high",
                "event_type": "practice_game",
                "practice_game_id": int(game["id"]),
                "practice_game_status": game["status"],
            })
        return tuple(events)

    def _stadium_for(self, opponent_team, venue_type):
        if venue_type == "home":
            return str(TEAM_INFO[self.managed_team]["stadium"])
        if venue_type == "away":
            return str(TEAM_INFO[opponent_team]["stadium"])
        return "2차 스프링캠프 현지 구장"

    @staticmethod
    def _as_date(value):
        if isinstance(value, date):
            return value
        try:
            return date.fromisoformat(str(value))
        except (TypeError, ValueError) as error:
            raise PracticeGameError("날짜 형식이 올바르지 않습니다.") from error

    @staticmethod
    def _validate_time(value):
        try:
            datetime.strptime(value, "%H:%M")
        except ValueError as error:
            raise PracticeGameError("경기 시작 시각은 HH:MM 형식이어야 합니다.") from error
