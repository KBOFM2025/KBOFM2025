"""모든 구단의 하루를 한 트랜잭션으로 진행하는 오프시즌 시뮬레이션 엔진."""

import hashlib
import json
import math
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta

from app.config import TEAM_INFO
from app.config.season_schedule import SEASON_EVENTS, phase_for
from app.services.team_lineup_engine import (
    TeamLineupEngine,
    availability_score,
    player_ability_score,
)
from app.services.manager_events import ManagerEventService
from database.league_simulation_repository import LeagueSimulationRepository


POSITION_MINIMUMS = {"P": 13, "C": 2, "IF": 6, "OF": 5}
ROSTER_EVALUATION_DATES = {
    "2025-11-03", "2025-11-12", "2025-11-19", "2025-11-21",
    "2025-11-25", "2025-11-27", "2025-11-30", "2025-12-15",
    "2025-12-22", "2025-12-29", "2026-01-02", "2026-01-12",
    "2026-01-19", "2026-01-25", "2026-01-31", "2026-02-07", "2026-02-14",
    "2026-02-19", "2026-02-21", "2026-02-28",
}
INJURIES = (
    ("가벼운 근육통", 3, 6), ("허리 통증", 5, 10), ("발목 염좌", 7, 14),
    ("어깨 피로", 8, 16), ("팔꿈치 염증", 12, 24),
)


def _stable_number(*parts, modulo):
    payload = ":".join(str(part) for part in parts).encode("utf-8")
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big") % modulo


def _clamp(value, low=0, high=100):
    return max(low, min(high, int(value)))


def _sim_log(message):
    print(f"[리그 시뮬레이션] {message}", flush=True)


class DailyTeamDecisionEngine:
    """선수 상태와 구단 성향으로 상대 구단의 1·2군 이동을 판단한다."""

    def choose(
        self, team, players, states, profile, simulation_date,
        recent_decisions=(),
    ):
        first = [p for p in players if int(p.get("status") or 0) == 1]
        second = [p for p in players if int(p.get("status") or 0) == 0]
        if not first or not second:
            return []
        recent_by_player = {
            int(item["player_id"]): item for item in recent_decisions
        }
        decisions, used = [], set()
        for injured in sorted(first, key=lambda p: states[p["id"]]["injury_days"], reverse=True):
            if states[injured["id"]]["injury_days"] <= 0:
                continue
            candidates = [p for p in second if p["id"] not in used
                          and p.get("position_group") == injured.get("position_group")
                          and states[p["id"]]["injury_days"] == 0
                          and not self._on_cooldown(
                              p["id"], recent_by_player, simulation_date
                          )]
            if not candidates:
                continue
            promote = max(
                candidates,
                key=lambda p: (
                    p.get("pos") == injured.get("pos"),
                    self._organizational_value(
                        p, states[p["id"]], profile, is_challenger=True
                    ),
                ),
            )
            reason = f"{injured['name']}의 {states[injured['id']]['injury_type']} 이탈에 따른 대체 등록"
            decisions.extend(self._swap(team, injured, promote, reason))
            used.add(promote["id"])
        if simulation_date.isoformat() not in ROSTER_EVALUATION_DATES:
            return decisions

        changed = {d["player_id"] for d in decisions}
        first = [p for p in first if p["id"] not in changed]
        second = [p for p in second if p["id"] not in changed]
        max_swaps = 2 if profile["roster_aggression"] >= 4 else 1
        proposals = []
        first_counts = Counter(p.get("position_group") for p in first)
        for group, minimum in POSITION_MINIMUMS.items():
            incumbents = [p for p in first if p.get("position_group") == group and states[p["id"]]["injury_days"] == 0]
            challengers = [p for p in second if p.get("position_group") == group and states[p["id"]]["injury_days"] == 0]
            if not incumbents or not challengers:
                continue
            incumbents = [
                player for player in incumbents
                if not self._on_cooldown(
                    player["id"], recent_by_player, simulation_date
                )
            ]
            challengers = [
                player for player in challengers
                if not self._on_cooldown(
                    player["id"], recent_by_player, simulation_date
                )
            ]
            if not incumbents or not challengers:
                continue
            demote = min(
                incumbents,
                key=lambda p: self._organizational_value(
                    p, states[p["id"]], profile, is_challenger=False
                ),
            )
            promote = max(
                challengers,
                key=lambda p: self._organizational_value(
                    p, states[p["id"]], profile, is_challenger=True
                ),
            )
            old_score = self._organizational_value(
                demote, states[demote["id"]], profile, is_challenger=False
            )
            new_score = self._organizational_value(
                promote, states[promote["id"]], profile, is_challenger=True
            )
            threshold = (
                3.8
                - profile["roster_aggression"] * .42
                - profile["development"] * .16
                + profile["stability"] * .18
            )
            depth_pressure = max(0, minimum - first_counts[group]) * 1.5
            advantage = new_score - old_score + depth_pressure
            if advantage > threshold:
                proposals.append(
                    (advantage, group, demote, promote, old_score, new_score)
                )

        for _advantage, group, demote, promote, old_score, new_score in sorted(
            proposals, key=lambda item: item[0], reverse=True
        ):
            if len(decisions) // 2 >= max_swaps:
                break
            if demote["id"] in used or promote["id"] in used:
                continue
            reason = (
                f"정기 전력 평가({group}): {promote['name']} "
                f"{new_score:.1f}, {demote['name']} {old_score:.1f} · "
                f"구단의 즉시전력 {profile['win_now']}/육성 "
                f"{profile['development']} 기조 반영"
            )
            decisions.extend(self._swap(team, demote, promote, reason))
            used.update((demote["id"], promote["id"]))
        return decisions

    @staticmethod
    def _on_cooldown(player_id, recent_by_player, simulation_date):
        recent = recent_by_player.get(int(player_id))
        if not recent:
            return False
        try:
            changed = date.fromisoformat(str(recent["decision_date"]))
        except (TypeError, ValueError):
            return False
        return (simulation_date - changed).days < 21

    @staticmethod
    def _organizational_value(player, state, profile, is_challenger):
        """현재 전력, 성장성, 연봉 효율과 구단 철학을 하나의 평가로 묶는다."""
        ability = player_ability_score(player)
        readiness = availability_score(
            player, state, profile["development"]
        )
        age = int(player.get("age") or 29)
        salary = max(1, int(player.get("salary") or 1))
        youth = max(0, 29 - age) * profile["development"] * 0.18
        veteran = (
            max(0, age - 31) * profile["win_now"] * 0.08
            if ability >= 12
            else -max(0, age - 31) * 0.28
        )
        salary_signal = min(3.0, math.log10(salary) * 0.55)
        salary_burden = (
            max(0.0, math.log10(salary) - 4.4)
            * max(0.0, 12.0 - ability)
            * (6 - profile["risk_tolerance"])
            * 0.35
        )
        role_commitment = 0.7 if player.get("role") not in ("", "선수", None) else 0
        opportunity = 0.45 * profile["development"] if is_challenger and age <= 27 else 0
        return (
            readiness
            + ability * (0.28 + profile["win_now"] * 0.035)
            + youth
            + veteran
            + salary_signal
            + role_commitment
            + opportunity
            - salary_burden
        )

    @staticmethod
    def _swap(team, demote, promote, reason):
        return [
            {"team": team, "player_id": demote["id"], "player_name": demote["name"], "action": "demote", "reason": reason},
            {"team": team, "player_id": promote["id"], "player_name": promote["name"], "action": "promote", "reason": reason},
        ]


class LeagueSimulationService:
    def __init__(
        self,
        save_database,
        save_id,
        player_db_path,
        managed_team,
        progress_callback=None,
    ):
        self.save_database = save_database
        self.save_id = save_id
        self.managed_team = managed_team
        self.progress_callback = progress_callback
        self.repository = LeagueSimulationRepository(save_database.db_path, player_db_path)
        self.decision_engine = DailyTeamDecisionEngine()
        self.lineup_engine = TeamLineupEngine()

    def _progress(self, team=None, status="", detail="", state="working"):
        """UI가 구단별 처리 상황을 표시할 수 있도록 안전하게 알린다."""
        if self.progress_callback is None:
            return
        try:
            self.progress_callback(
                {
                    "team": team,
                    "status": status,
                    "detail": detail,
                    "state": state,
                }
            )
        except Exception as error:
            _sim_log(f"진행 화면 알림 생략 · {error!r}")

    def simulate_day(self, simulation_date):
        if isinstance(simulation_date, str):
            simulation_date = date.fromisoformat(simulation_date)
        day = simulation_date.isoformat()
        _sim_log(f"{day} 하루 진행 시작 · 사용자 구단: {self.managed_team}")
        with self.repository.transaction() as connection:
            completed = self.repository.completed_summary(connection, self.save_id, day)
            if completed is not None:
                _sim_log(f"{day}은 이미 처리된 날짜입니다 · 저장된 결과 사용")
                for team in TEAM_INFO:
                    self._progress(
                        team,
                        "저장 결과 확인",
                        "이미 처리된 구단 일정을 불러왔습니다.",
                        "done",
                    )
                return completed
            self.repository.begin_run(connection, self.save_id, day)
            weekly_report_due = self._weekly_report_due(connection)
            self._progress(
                status="선수 컨디션과 부상 상태를 계산하고 있습니다.",
                state="global",
            )
            activated_rookies = self._activate_incoming_rookies(
                connection, simulation_date
            )
            players = [dict(r) for r in connection.execute("SELECT * FROM playerdb.players ORDER BY team, id")]
            _sim_log(f"선수 DB 로드 완료 · {len(players)}명")
            objectives = self._load_objectives(connection)
            profiles = self._seed_profiles(connection, objectives)
            _sim_log(f"구단 운영 성향 로드 완료 · {len(profiles)}개 구단")
            injury_events, recovery_events = self._advance_player_states(connection, players, simulation_date)
            injury_count, recovery_count = len(injury_events), len(recovery_events)
            _sim_log(f"선수 상태 진행 완료 · 신규 부상 {injury_count}명 · 복귀 {recovery_count}명")
            self._add_medical_news(connection, simulation_date, injury_events, recovery_events)
            states = self._load_states(connection)
            by_team = self._group_players(players)
            recent_decisions = self._load_recent_decisions(
                connection, simulation_date
            )
            decisions = []
            for team in TEAM_INFO:
                if team == self.managed_team:
                    continue
                self._progress(
                    team,
                    "엔트리 검토",
                    "구단 AI가 1·2군 경쟁과 부상 대체 자원을 검토합니다.",
                    "roster",
                )
                selected = self.decision_engine.choose(
                    team, by_team.get(team, []), states, profiles[team],
                    simulation_date, recent_decisions.get(team, ()),
                )
                self._apply_decisions(connection, day, selected)
                decisions.extend(selected)
                if selected:
                    changes = ", ".join(f"{item['player_name']} {'콜업' if item['action'] == 'promote' else '강등'}" for item in selected)
                    _sim_log(f"{team} 엔트리 조정 · {changes}")

            players = [dict(r) for r in connection.execute("SELECT * FROM playerdb.players ORDER BY team, id")]
            by_team = self._group_players(players)
            phase_name, _ = phase_for(simulation_date)
            lineup_count = 0
            for team in TEAM_INFO:
                self._progress(
                    team,
                    (
                        "감독 운영 반영"
                        if team == self.managed_team
                        else "훈련·라인업"
                    ),
                    (
                        "사용자 감독의 선수단 운영 상태를 반영합니다."
                        if team == self.managed_team
                        else "구단 성향에 따라 훈련과 포지션 경쟁을 정리합니다."
                    ),
                    "planning",
                )
                roster = by_team.get(team, [])
                self._refresh_squad_groups(connection, roster, states, phase_name)
                self._save_training_plan(connection, day, team, phase_name, profiles[team])
                team_lineup_count = self._save_lineups(connection, day, team, roster, states, profiles[team], team != self.managed_team)
                lineup_count += team_lineup_count
                self.repository.save_team_state(connection, self.save_id, day, self._team_state(team, roster, states, phase_name))
                first_count = sum(int(player.get("status") or 0) == 1 for player in roster)
                injured = sum(states[player["id"]]["injury_days"] > 0 for player in roster)
                control = "감독 직접 운영" if team == self.managed_team else "구단 AI 운영"
                _sim_log(f"{team} 완료 · 1군 {first_count}명 · 2군 {len(roster)-first_count}명 · 부상 {injured}명 · 편성 {team_lineup_count}건 · {control}")
                team_moves = [
                    (
                        f"{decision['player_name']} "
                        f"{'콜업' if decision['action'] == 'promote' else '강등'}"
                    )
                    for decision in decisions
                    if decision["team"] == team
                ]
                move_summary = " · ".join(team_moves[:2])
                if len(team_moves) > 2:
                    move_summary += f" 외 {len(team_moves) - 2}건"
                status = (
                    f"완료 · {move_summary}"
                    if team_moves
                    else "완료 · 엔트리 유지"
                )
                self._progress(
                    team,
                    status,
                    (
                        f"1군 {first_count}명 · 2군 {len(roster)-first_count}명 · "
                        f"부상 {injured}명 · 편성 {team_lineup_count}건"
                        + (
                            f" · {' / '.join(team_moves)}"
                            if team_moves else ""
                        )
                    ),
                    "done",
                )

            events = SEASON_EVENTS.get(simulation_date, ())
            self._progress(
                status="구단 소식과 다음 일정을 수신함에 정리하고 있습니다.",
                state="global",
            )
            queued_count = self._save_events_and_ai_queue(
                connection, day, events, profiles, by_team, states, phase_name
            )
            ManagerEventService.generate_daily(
                connection,
                self.save_id,
                self.managed_team,
                simulation_date,
                players,
                states,
                injuries=injury_events,
                schedule_events=events,
            )
            if events:
                _sim_log(f"일정 이벤트 {len(events)}건 반영 · Qwen 검토 대기 {queued_count}건")
            connection.execute(
                "UPDATE game_saves SET current_date=?, season_day=season_day+1, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (day, self.save_id),
            )
            summary = {
                "simulation_date": day, "processed_teams": len(TEAM_INFO), "player_count": len(players),
                "injury_count": injury_count, "recovery_count": recovery_count,
                "first_team_injury_count": sum(event["squad"] == "1군" for event in injury_events),
                "first_team_recovery_count": sum(event["squad"] == "1군" for event in recovery_events),
                "roster_decision_count": len(decisions), "lineup_assignment_count": lineup_count,
                "ai_queue_count": queued_count, "changed_teams": sorted({d["team"] for d in decisions}),
                "season_phase": phase_name, "schedule_event_count": len(events),
                "activated_rookie_count": activated_rookies,
            }
            if weekly_report_due:
                self._add_weekly_report(connection, summary, simulation_date)
            self.repository.complete_run(connection, self.save_id, day, summary)
            _sim_log(f"{day} 트랜잭션 저장 완료 · 엔트리 이동 {len(decisions)}건 · 전체 편성 {lineup_count}건")
            return summary

    def _activate_incoming_rookies(self, connection, simulation_date):
        """입단 예정일이 되면 공식 지명 신인을 각 구단 2군에 합류시킨다."""
        day = simulation_date.isoformat()
        rows = connection.execute(
            """
            SELECT * FROM incoming_rookies
            WHERE save_id=? AND status='incoming' AND arrival_date<=?
            ORDER BY overall_pick
            """,
            (self.save_id, day),
        ).fetchall()
        if not rows:
            return 0

        player_columns = {
            row["name"]
            for row in connection.execute(
                "PRAGMA playerdb.table_info(players)"
            ).fetchall()
        }
        for column, declaration in (
            ("draft_year", "INTEGER"),
            ("draft_pick", "INTEGER"),
            ("school", "TEXT DEFAULT ''"),
            ("arrival_date", "TEXT"),
        ):
            if column not in player_columns:
                connection.execute(
                    f"ALTER TABLE playerdb.players ADD COLUMN "
                    f"{column} {declaration}"
                )

        for rookie in rows:
            ratings = self._rookie_ratings(rookie)
            values = {
                "player_uid": (
                    f"DRAFT-{rookie['draft_year']}-"
                    f"{int(rookie['overall_pick']):03d}"
                ),
                "kbo_player_id": (
                    f"DRAFT-{rookie['draft_year']}-"
                    f"{int(rookie['overall_pick']):03d}"
                ),
                "team": rookie["team"],
                "name": rookie["player_name"],
                "pos": rookie["position_group"],
                "age": 22 if "대" in rookie["school"] else 19,
                "birth_date": "",
                "bats_throws": "",
                "career": f"{rookie['school']}-{rookie['team']}",
                **ratings,
                "status": 0,
                "lineup_pos": 0,
                "role": "신인 육성",
                "salary": 3000,
                "snapshot_date": day,
                "position_group": rookie["position_group"],
                "is_rookie": 1,
                "is_foreign": 0,
                "profile_complete": 0,
                "source_note": (
                    "2026 KBO 신인 드래프트 공식 지명 · "
                    "프로 표본 미확보"
                ),
                "source_url": rookie["source_url"],
                "draft_year": rookie["draft_year"],
                "draft_pick": rookie["overall_pick"],
                "school": rookie["school"],
                "arrival_date": day,
            }
            player_schema = {
                row["name"]: dict(row)
                for row in connection.execute(
                    "PRAGMA playerdb.table_info(players)"
                ).fetchall()
            }
            self._fill_required_player_values(values, player_schema)
            columns = tuple(values)
            connection.execute(
                f"""
                INSERT OR IGNORE INTO playerdb.players
                ({', '.join(columns)})
                VALUES ({', '.join('?' for _ in columns)})
                """,
                tuple(values[column] for column in columns),
            )
            connection.execute(
                """
                UPDATE incoming_rookies
                SET status='activated'
                WHERE save_id=? AND draft_year=? AND overall_pick=?
                """,
                (
                    self.save_id, rookie["draft_year"],
                    rookie["overall_pick"],
                ),
            )

        connection.execute(
            """
            INSERT OR IGNORE INTO daily_news (
                save_id, news_date, category, headline, body, created_at
            ) VALUES (?, ?, 'KBO', ?, ?, CURRENT_TIMESTAMP)
            """,
            (
                self.save_id, day,
                f"2026 신인 선수 {len(rows)}명 구단 합류",
                "2025년 9월 신인 드래프트에서 지명된 선수들이 각 구단 "
                "2군 선수단에 합류했습니다. 프로 표본이 없는 능력치는 "
                "지명 순위와 포지션을 바탕으로 보수적으로 평가되며, 향후 "
                "훈련과 실전 기록에 따라 조정됩니다.",
            ),
        )
        _sim_log(f"2026 신인 자동 합류 · {len(rows)}명")
        return len(rows)

    @staticmethod
    def _fill_required_player_values(values, schema):
        """세이브마다 다른 players 필수 열을 스키마에 맞춰 보완한다."""
        for column, info in schema.items():
            if column in values or column == "id":
                continue
            if (
                not int(info.get("notnull") or 0)
                or info.get("dflt_value") is not None
            ):
                continue
            column_type = str(info.get("type") or "").upper()
            if "INT" in column_type:
                values[column] = 0
            elif any(
                kind in column_type
                for kind in ("REAL", "FLOA", "DOUB", "NUM")
            ):
                values[column] = 0.0
            else:
                values[column] = ""

    def _rookie_ratings(self, rookie):
        """프로 표본이 없는 신인은 지명 순위 기반의 보수적 초기값을 쓴다."""
        pick = int(rookie["overall_pick"])
        round_no = int(rookie["round_no"])
        seed = _stable_number(
            self.save_id, rookie["draft_year"], pick, modulo=2 ** 31
        )
        base = max(6, min(12, 12 - (round_no - 1) // 2))

        def value(offset, adjustment=0):
            noise = ((seed >> offset) % 3) - 1
            return max(1, min(20, base + adjustment + noise))

        ratings: dict[str, object] = {
            "con": value(0),
            "pow": value(2),
            "eye": value(4),
            "def": value(6),
        }
        hitter_columns = (
            "contact", "power", "plate_discipline", "bat_control",
            "timing", "bunt", "speed", "baserunning_judgment",
            "fielding_range", "catching", "throwing_power",
            "throwing_accuracy", "fielding_judgment", "composure",
            "leadership", "aggressiveness",
        )
        pitcher_columns = (
            "pitcher_velocity", "pitcher_stuff", "pitcher_command",
            "pitcher_movement", "pitcher_stamina",
            "pitcher_pitchability", "pitcher_strikeout",
            "pitcher_walk_control", "pitcher_composure",
        )
        if rookie["position_group"] == "P":
            ratings.update({column: None for column in hitter_columns})
            ratings.update({
                column: value(index * 2, 1 if index < 2 else 0)
                for index, column in enumerate(pitcher_columns)
            })
        else:
            ratings.update({
                column: value(
                    index * 2,
                    2 if column == "catching"
                    and rookie["position_group"] == "C"
                    else 1 if column in (
                        "fielding_range", "fielding_judgment"
                    ) and rookie["position_group"] in ("C", "IF")
                    else 0,
                )
                for index, column in enumerate(hitter_columns)
            })
            ratings.update({column: None for column in pitcher_columns})
        return ratings

    @staticmethod
    def _group_players(players):
        result = defaultdict(list)
        for player in players:
            result[player["team"]].append(player)
        return result

    def _load_states(self, connection):
        return {r["player_id"]: dict(r) for r in connection.execute(
            "SELECT * FROM player_simulation_states WHERE save_id=?", (self.save_id,))}

    @staticmethod
    def _load_objectives(connection):
        result = defaultdict(dict)
        for row in connection.execute("SELECT club_name, objective_key, initial_level FROM gm_objective_defaults"):
            result[row["club_name"]][row["objective_key"]] = int(row["initial_level"])
        return result

    def _seed_profiles(self, connection, objectives):
        now, profiles = datetime.now().isoformat(timespec="seconds"), {}
        for team in TEAM_INFO:
            values = objectives.get(team, {})
            profile = {
                "win_now": values.get("season_result", 3),
                "development": values.get("long_term_vision", 3),
                "roster_aggression": values.get("roster_balance", values.get("front_office", 3)),
                "stability": values.get("club_identity", 3),
                "risk_tolerance": values.get("financial_management", 3),
            }
            style = TEAM_INFO[team].get("front_office_style", "")
            if "우승" in style or "즉시 전력" in style:
                profile["win_now"] += 1
            if "육성" in style or "유망주" in style or "성장" in style:
                profile["development"] += 1
            if "과감" in style or "적극" in style or "트레이드" in style:
                profile["roster_aggression"] += 1
            if "안정" in style or "연속성" in style or "조직력" in style:
                profile["stability"] += 1
            if "효율" in style or "재정" in style or "가치" in style:
                profile["risk_tolerance"] -= 1
            profile = {
                key: max(1, min(5, int(value)))
                for key, value in profile.items()
            }
            profiles[team] = profile
            connection.execute(
                """INSERT INTO team_ai_profiles
                (save_id,team,win_now,development,roster_aggression,stability,risk_tolerance,updated_at)
                VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(save_id,team) DO UPDATE SET
                win_now=excluded.win_now,development=excluded.development,
                roster_aggression=excluded.roster_aggression,stability=excluded.stability,
                risk_tolerance=excluded.risk_tolerance,updated_at=excluded.updated_at""",
                (self.save_id, team, profile["win_now"], profile["development"], profile["roster_aggression"],
                 profile["stability"], profile["risk_tolerance"], now),
            )
        return profiles

    def _load_recent_decisions(self, connection, simulation_date):
        cutoff = (simulation_date - timedelta(days=21)).isoformat()
        rows = connection.execute(
            """
            SELECT decision_date, team, player_id, action, reason
            FROM team_roster_decisions
            WHERE save_id=? AND decision_date>=?
            ORDER BY decision_date DESC, id DESC
            """,
            (self.save_id, cutoff),
        ).fetchall()
        result = defaultdict(list)
        seen = set()
        for row in rows:
            key = (row["team"], row["player_id"])
            if key in seen:
                continue
            seen.add(key)
            result[row["team"]].append(dict(row))
        return result

    def _advance_player_states(self, connection, players, simulation_date):
        day, (phase, _) = simulation_date.isoformat(), phase_for(simulation_date)
        intensity = 4 if phase == "1차 캠프" else 5 if phase == "2차 캠프" else 2
        injuries, recoveries = [], []
        for player in players:
            initial_condition = 78 + _stable_number(self.save_id, player["id"], "condition", modulo=18)
            initial_sharpness = 42 + _stable_number(self.save_id, player["id"], "sharpness", modulo=19)
            connection.execute(
                """INSERT OR IGNORE INTO player_simulation_states
                (save_id,player_id,team,condition,fatigue,training_points,injury_days,
                match_sharpness,morale,injury_risk,squad_group,injury_type,last_updated)
                VALUES (?,?,?,?,0,0,0,?,75,5,?,'','')""",
                (self.save_id, player["id"], player["team"], initial_condition, initial_sharpness,
                 "1군" if player.get("status") else "2군"),
            )
            state = dict(connection.execute(
                "SELECT * FROM player_simulation_states WHERE save_id=? AND player_id=?",
                (self.save_id, player["id"])).fetchone())
            if state["last_updated"] == day:
                continue
            old_days = int(state["injury_days"])
            injury_days, injury_type = max(0, old_days - 1), state["injury_type"]
            recovery_event = None
            if old_days == 1:
                recovery_event = {
                    "team": player["team"], "player_id": player["id"], "name": player["name"],
                    "position": player.get("pos") or player.get("position_group") or "-",
                    "age": player.get("age") or "-", "injury_type": injury_type or "부상",
                    "squad": "1군" if player.get("status") else "2군",
                    "condition": int(state["condition"]),
                }
                injury_type = ""
                connection.execute("UPDATE player_injury_events SET status='recovered' WHERE save_id=? AND player_id=? AND status='active'", (self.save_id, player["id"]))
            variation = _stable_number(self.save_id, player["id"], day, "daily", modulo=5) - 2
            training_gain = max(1, intensity - int(state["fatigue"]) // 35)
            fatigue = _clamp(int(state["fatigue"]) + intensity - 2 + max(0, -variation))
            condition = _clamp(int(state["condition"]) + variation + (intensity <= 2) - fatigue // 45, 45, 100)
            sharpness = _clamp(int(state["match_sharpness"]) + (2 if phase in ("1차 캠프", "2차 캠프") else 0) + (simulation_date.day % 3 == 0), 25, 100)
            risk = _clamp(3 + fatigue // 12 + (3 if int(player.get("age") or 0) >= 35 else 0), 1, 30)
            morale = _clamp(int(state["morale"]) + (1 if condition >= 88 else -1 if condition < 65 else 0), 40, 100)
            injury_roll = _stable_number(self.save_id, player["id"], day, "injury", modulo=10000)
            if old_days == 0 and injury_days == 0 and injury_roll < risk * intensity:
                injury_name, minimum, maximum = INJURIES[_stable_number(player["id"], day, modulo=len(INJURIES))]
                injury_days = minimum + _stable_number(self.save_id, player["id"], day, modulo=maximum-minimum+1)
                injury_type, condition, morale = injury_name, min(condition, 62), max(40, morale-4)
                injuries.append({
                    "team": player["team"], "player_id": player["id"], "name": player["name"],
                    "position": player.get("pos") or player.get("position_group") or "-",
                    "age": player.get("age") or "-", "injury_type": injury_name,
                    "expected_days": injury_days, "condition": condition, "fatigue": fatigue,
                    "squad": "1군" if player.get("status") else "2군",
                })
                connection.execute(
                    """INSERT OR IGNORE INTO player_injury_events
                    (save_id,event_date,team,player_id,player_name,injury_type,expected_days)
                    VALUES (?,?,?,?,?,?,?)""",
                    (self.save_id, day, player["team"], player["id"], player["name"], injury_name, injury_days),
                )
            if recovery_event is not None:
                recovery_event["condition"] = condition
                recoveries.append(recovery_event)
            connection.execute(
                """UPDATE player_simulation_states SET condition=?,fatigue=?,training_points=training_points+?,
                injury_days=?,match_sharpness=?,morale=?,injury_risk=?,injury_type=?,last_updated=?
                WHERE save_id=? AND player_id=?""",
                (condition, fatigue, training_gain, injury_days, sharpness, morale, risk, injury_type,
                 day, self.save_id, player["id"]),
            )
        return injuries, recoveries

    def _add_medical_news(self, connection, simulation_date, injuries, recoveries):
        """타 구단 1군 신규 부상은 주간 보고를 기다리지 않고 속보로 기록한다."""
        day = simulation_date.isoformat()
        for injury in injuries:
            if (
                injury["squad"] != "1군"
                or injury["team"] == self.managed_team
            ):
                continue
            expected_return = simulation_date + timedelta(days=injury["expected_days"])
            return_date = f"{expected_return.year}년 {expected_return.month}월 {expected_return.day}일"
            headline = (
                f"{injury['team']} {injury['name']}, "
                f"{injury['injury_type']}로 {injury['expected_days']}일 이탈"
            )
            body = (
                f"{injury['team']}의 {injury['name']}({injury['position']}·{injury['age']}세)가 "
                f"{injury['injury_type']} 진단을 받았습니다.\n"
                f"발생 당시 소속은 {injury['squad']}, 컨디션 {injury['condition']}, "
                f"피로도 {injury['fatigue']}였습니다. 예상 이탈 기간은 "
                f"{injury['expected_days']}일이며 예상 복귀일은 {return_date}입니다."
            )
            connection.execute(
                """INSERT OR IGNORE INTO daily_news
                (save_id,news_date,category,headline,body,created_at)
                VALUES (?,?, '의료 센터', ?, ?, CURRENT_TIMESTAMP)""",
                (self.save_id, day, headline, body),
            )
            _sim_log(f"부상 뉴스 · {headline}")

        for recovery in recoveries:
            if (
                recovery["squad"] != "1군"
                or recovery["team"] != self.managed_team
            ):
                continue
            headline = f"{recovery['team']} {recovery['name']}, {recovery['injury_type']}에서 회복"
            body = (
                f"{recovery['team']}의 {recovery['name']}({recovery['position']}·{recovery['age']}세)가 "
                f"{recovery['injury_type']} 재활을 마쳤습니다.\n"
                f"현재 컨디션은 {recovery['condition']}이며 기존 {recovery['squad']} 선수단의 "
                "훈련에 단계적으로 합류합니다. 당일 라인업 편성 시 현재 상태가 반영됩니다."
            )
            connection.execute(
                """INSERT OR IGNORE INTO daily_news
                (save_id,news_date,category,headline,body,created_at)
                VALUES (?,?, '의료 센터', ?, ?, CURRENT_TIMESTAMP)""",
                (self.save_id, day, headline, body),
            )
            _sim_log(f"복귀 뉴스 · {headline}")

    def _apply_decisions(self, connection, day, decisions):
        for decision in decisions:
            status = 1 if decision["action"] == "promote" else 0
            connection.execute("UPDATE playerdb.players SET status=?,lineup_pos=0,role='' WHERE id=? AND team=?",
                               (status, decision["player_id"], decision["team"]))
            self.repository.save_roster_decision(connection, self.save_id, day, decision)

    def _refresh_squad_groups(self, connection, players, states, phase):
        for player in players:
            state = states[player["id"]]
            if state["injury_days"] > 0:
                group = "재활조"
            elif phase in ("1차 캠프", "2차 캠프"):
                group = phase if player.get("status") else "잔류조"
            else:
                group = "1군" if player.get("status") else "2군"
            state["squad_group"] = group
            connection.execute("UPDATE player_simulation_states SET squad_group=? WHERE save_id=? AND player_id=?",
                               (group, self.save_id, player["id"]))

    def _save_training_plan(self, connection, day, team, phase, profile):
        focus, base = {"1차 캠프": ("체력·기본기", 4), "2차 캠프": ("실전·전술", 5),
                       "캠프 준비": ("개인 컨디셔닝", 3)}.get(phase, ("회복·기술 유지", 2))
        intensity = _clamp(base + (profile["win_now"] >= 4) - (profile["stability"] >= 4), 1, 5)
        note = f"{phase} · 육성 {profile['development']} · 즉시전력 {profile['win_now']}"
        connection.execute(
            """INSERT INTO team_training_plans VALUES (?,?,?,?,?,?,?)
            ON CONFLICT(save_id,plan_date,team) DO UPDATE SET season_phase=excluded.season_phase,
            focus=excluded.focus,intensity=excluded.intensity,note=excluded.note""",
            (self.save_id, day, team, phase, focus, intensity, note))

    def _save_lineups(self, connection, day, team, players, states, profile, overwrite):
        count = 0
        if overwrite:
            connection.execute("UPDATE playerdb.players SET lineup_pos=0,role='' WHERE team=?", (team,))
        for level in (1, 0):
            batting, pitching = self.lineup_engine.build(players, states, level, profile["development"])
            if not overwrite and level == 1:
                active_tactic = connection.execute(
                    """
                    SELECT batting_json, pitching_json
                    FROM team_tactic_versions
                    WHERE save_id=? AND team=? AND is_active=1
                    ORDER BY updated_at DESC LIMIT 1
                    """,
                    (self.save_id, team),
                ).fetchone()
                players_by_id = {int(player["id"]): player for player in players}
                if active_tactic:
                    tactic_batting = []
                    for item in json.loads(active_tactic["batting_json"] or "[]"):
                        player = players_by_id.get(int(item["player_id"]))
                        if (
                            player
                            and int(player.get("status") or 0) == 1
                            and player.get("position_group") != "P"
                            and player.get("pos") != "P"
                            and states[player["id"]]["injury_days"] == 0
                        ):
                            tactic_batting.append(
                                {
                                    "batting_order": int(item["order"]),
                                    "player_id": player["id"],
                                    "player_name": player["name"],
                                    "defensive_position": item.get("position") or player.get("pos") or "DH",
                                    "selection_score": round(
                                        availability_score(
                                            player, states[player["id"]], profile["development"]
                                        ),
                                        2,
                                    ),
                                }
                            )
                    tactic_pitching = []
                    for item in json.loads(active_tactic["pitching_json"] or "[]"):
                        player = players_by_id.get(int(item["player_id"]))
                        if (
                            player
                            and int(player.get("status") or 0) == 1
                            and (
                                player.get("position_group") == "P"
                                or player.get("pos") == "P"
                            )
                            and states[player["id"]]["injury_days"] == 0
                        ):
                            tactic_pitching.append(
                                {
                                    "role_order": int(item["role_order"]),
                                    "role": item["role"],
                                    "player_id": player["id"],
                                    "player_name": player["name"],
                                    "selection_score": round(
                                        availability_score(
                                            player, states[player["id"]], profile["development"]
                                        ),
                                        2,
                                    ),
                                }
                            )
                    if tactic_batting:
                        batting = sorted(
                            tactic_batting, key=lambda item: item["batting_order"]
                        )
                    if tactic_pitching:
                        pitching = sorted(
                            tactic_pitching, key=lambda item: item["role_order"]
                        )
                else:
                    saved_batting = sorted(
                        (p for p in players if int(p.get("status") or 0) == 1
                         and int(p.get("lineup_pos") or 0) > 0
                         and p.get("position_group") != "P"
                         and states[p["id"]]["injury_days"] == 0),
                        key=lambda p: int(p["lineup_pos"]),
                    )
                    if saved_batting:
                        batting = [
                            {"batting_order": int(p["lineup_pos"]), "player_id": p["id"],
                             "player_name": p["name"], "defensive_position": p.get("pos") or "DH",
                             "selection_score": round(availability_score(p, states[p["id"]], profile["development"]), 2)}
                            for p in saved_batting[:9]
                        ]
                    saved_pitching = [p for p in players if int(p.get("status") or 0) == 1
                                      and p.get("position_group") == "P"
                                      and p.get("role") and p.get("role") != "선수"
                                      and states[p["id"]]["injury_days"] == 0]
                    if saved_pitching:
                        pitching = [
                            {"role_order": index + 1, "role": p["role"], "player_id": p["id"],
                             "player_name": p["name"],
                             "selection_score": round(availability_score(p, states[p["id"]], profile["development"]), 2)}
                            for index, p in enumerate(saved_pitching)
                        ]
            connection.execute("DELETE FROM team_lineups WHERE save_id=? AND lineup_date=? AND team=? AND squad_level=?", (self.save_id, day, team, level))
            connection.execute("DELETE FROM team_pitching_roles WHERE save_id=? AND assignment_date=? AND team=? AND squad_level=?", (self.save_id, day, team, level))
            for item in batting:
                connection.execute("INSERT INTO team_lineups VALUES (?,?,?,?,?,?,?,?,?)",
                    (self.save_id, day, team, level, item["batting_order"], item["player_id"], item["player_name"], item["defensive_position"], item["selection_score"]))
                if overwrite and level == 1:
                    connection.execute("UPDATE playerdb.players SET lineup_pos=? WHERE id=?", (item["batting_order"], item["player_id"]))
                count += 1
            for item in pitching:
                connection.execute("INSERT INTO team_pitching_roles VALUES (?,?,?,?,?,?,?,?,?)",
                    (self.save_id, day, team, level, item["role_order"], item["role"], item["player_id"], item["player_name"], item["selection_score"]))
                if overwrite and level == 1:
                    connection.execute("UPDATE playerdb.players SET role=? WHERE id=?", (item["role"], item["player_id"]))
                count += 1
        return count

    def _save_events_and_ai_queue(
        self, connection, day, events, profiles, by_team, states, phase,
    ):
        queued = 0
        for team in TEAM_INFO:
            for event in events:
                self.repository.save_schedule_event(connection, self.save_id, day, team, event)
                if team == self.managed_team or event.get("importance") != "high":
                    continue
                context = self._team_ai_context(
                    connection, day, team, event, profiles[team],
                    by_team.get(team, ()), states, phase,
                )
                cursor = connection.execute(
                    "INSERT OR IGNORE INTO team_ai_decision_queue (save_id,decision_date,team,decision_type,context_json) VALUES (?,?,?,?,?)",
                    (self.save_id, day, team, event["category"], json.dumps(context, ensure_ascii=False)))
                queued += cursor.rowcount
        return queued

    def _team_ai_context(
        self, connection, day, team, event, profile, players, states, phase,
    ):
        """작은 로컬 모델이 근거 있는 결정을 내릴 수 있는 압축 구단 보고서."""
        healthy = [
            player for player in players
            if int(states[player["id"]]["injury_days"]) == 0
        ]
        ranked = sorted(
            healthy,
            key=lambda player: player_ability_score(player),
            reverse=True,
        )
        prospects = sorted(
            (player for player in healthy if int(player.get("age") or 99) <= 27),
            key=lambda player: (
                player_ability_score(player)
                + max(0, 27 - int(player.get("age") or 27)) * .3
            ),
            reverse=True,
        )
        group_summary = {}
        for group in POSITION_MINIMUMS:
            group_players = [
                player for player in healthy
                if player.get("position_group") == group
            ]
            first = [
                player for player in group_players
                if int(player.get("status") or 0) == 1
            ]
            group_summary[group] = {
                "first_team": len(first),
                "total": len(group_players),
                "top3_ability": round(
                    sum(
                        sorted(
                            (player_ability_score(p) for p in group_players),
                            reverse=True,
                        )[:3]
                    ) / max(1, min(3, len(group_players))),
                    1,
                ),
                "minimum_first_team": POSITION_MINIMUMS[group],
            }
        recent = [
            {
                "date": row["decision_date"],
                "player": row["player_name"],
                "action": row["action"],
                "reason": row["reason"],
            }
            for row in connection.execute(
                """
                SELECT decision_date, player_name, action, reason
                FROM team_roster_decisions
                WHERE save_id=? AND team=? AND decision_date<?
                ORDER BY decision_date DESC, id DESC LIMIT 6
                """,
                (self.save_id, team, day),
            )
        ]

        def player_brief(player):
            state = states[player["id"]]
            return {
                "name": player["name"],
                "position": player.get("pos") or player.get("position_group"),
                "age": int(player.get("age") or 0),
                "squad": "1군" if player.get("status") else "2군",
                "ability": round(player_ability_score(player), 1),
                "condition": int(state["condition"]),
                "salary_10k_krw": int(player.get("salary") or 0),
            }

        info = TEAM_INFO[team]
        return {
            "event": event,
            "club": {
                "team": team,
                "general_manager": info.get("general_manager"),
                "season_goal": info.get("season_goal"),
                "long_term_goal": info.get("long_term_goal"),
                "front_office_style": info.get("front_office_style"),
            },
            "simulation": {"date": day, "phase": phase},
            "profile_1_to_5": profile,
            "roster": {
                "first_team": sum(
                    int(player.get("status") or 0) == 1 for player in players
                ),
                "second_team": sum(
                    int(player.get("status") or 0) == 0 for player in players
                ),
                "injured": sum(
                    int(states[player["id"]]["injury_days"]) > 0
                    for player in players
                ),
                "payroll_10k_krw": sum(
                    int(player.get("salary") or 0) for player in players
                ),
                "position_depth": group_summary,
                "key_players": [player_brief(player) for player in ranked[:5]],
                "prospects": [
                    player_brief(player) for player in prospects[:5]
                ],
            },
            "recent_roster_decisions": recent,
            "instruction": (
                "이 자료에 존재하는 선수와 수치만 근거로 한 가지 실행안을 "
                "정한다. 구단 철학, 당장의 약점, 장기 목표, 비용과 위험을 "
                "함께 비교하고 최근 결정을 불필요하게 뒤집지 않는다."
            ),
        }

    @staticmethod
    def _team_state(team, players, states, phase):
        first = [p for p in players if int(p.get("status") or 0) == 1]
        counts = Counter(p.get("position_group") for p in first)
        needs = [g for g, minimum in POSITION_MINIMUMS.items() if counts[g] < minimum]
        conditions = [states[p["id"]]["condition"] for p in players]
        return {"team": team, "season_phase": phase, "first_team_count": len(first),
                "second_team_count": len(players)-len(first),
                "average_condition": round(sum(conditions)/len(conditions), 1) if conditions else 0,
                "injured_count": sum(states[p["id"]]["injury_days"] > 0 for p in players),
                "roster_need": ",".join(needs)}

    def _weekly_report_due(self, connection):
        """완료된 리그 진행 7일마다 정기 보고서를 생성한다."""
        row = connection.execute(
            """
            SELECT COUNT(*) AS completed_days
            FROM simulation_runs
            WHERE save_id=? AND status='completed'
            """,
            (self.save_id,),
        ).fetchone()
        completed_days = int(row["completed_days"] if row else 0)
        return (completed_days + 1) % 7 == 0

    def _weekly_team_changes(self, connection, report_date):
        """최근 7일의 구단별 유의미한 변동을 사람이 읽을 수 있게 정리한다."""
        period_start = report_date - timedelta(days=6)
        start_day = period_start.isoformat()
        end_day = report_date.isoformat()
        baseline_day = (period_start - timedelta(days=1)).isoformat()

        decisions = connection.execute(
            """
            SELECT team, player_name, action
            FROM team_roster_decisions
            WHERE save_id=? AND decision_date BETWEEN ? AND ?
            ORDER BY decision_date, id
            """,
            (self.save_id, start_day, end_day),
        ).fetchall()
        injuries = connection.execute(
            """
            SELECT team, player_name, injury_type, expected_days
            FROM player_injury_events
            WHERE save_id=? AND event_date BETWEEN ? AND ?
            ORDER BY event_date, id
            """,
            (self.save_id, start_day, end_day),
        ).fetchall()
        current_rows = connection.execute(
            """
            SELECT * FROM team_daily_states
            WHERE save_id=? AND simulation_date=?
            """,
            (self.save_id, end_day),
        ).fetchall()
        baseline_rows = connection.execute(
            """
            SELECT state.*
            FROM team_daily_states state
            JOIN (
                SELECT team, MAX(simulation_date) AS simulation_date
                FROM team_daily_states
                WHERE save_id=? AND simulation_date<=?
                GROUP BY team
            ) latest
              ON latest.team=state.team
             AND latest.simulation_date=state.simulation_date
            WHERE state.save_id=?
            """,
            (self.save_id, baseline_day, self.save_id),
        ).fetchall()

        by_team_decisions = defaultdict(list)
        for row in decisions:
            action = "1군 콜업" if row["action"] == "promote" else "2군 이동"
            by_team_decisions[row["team"]].append(
                f"{row['player_name']} {action}"
            )
        by_team_injuries = defaultdict(list)
        for row in injuries:
            by_team_injuries[row["team"]].append(
                f"{row['player_name']} {row['injury_type']} "
                f"({int(row['expected_days'])}일)"
            )

        current = {row["team"]: dict(row) for row in current_rows}
        baseline = {row["team"]: dict(row) for row in baseline_rows}
        result = {}
        for team in TEAM_INFO:
            changes = []
            moves = by_team_decisions.get(team, [])
            if moves:
                shown = ", ".join(moves[:3])
                if len(moves) > 3:
                    shown += f" 외 {len(moves) - 3}건"
                changes.append(f"엔트리: {shown}")
            new_injuries = by_team_injuries.get(team, [])
            if new_injuries:
                shown = ", ".join(new_injuries[:2])
                if len(new_injuries) > 2:
                    shown += f" 외 {len(new_injuries) - 2}명"
                changes.append(f"신규 부상: {shown}")

            before = baseline.get(team)
            after = current.get(team)
            if before and after:
                before_injured = int(before["injured_count"])
                after_injured = int(after["injured_count"])
                if before_injured != after_injured:
                    changes.append(
                        f"부상자 {before_injured}명→{after_injured}명"
                    )
                before_need = str(before.get("roster_need") or "")
                after_need = str(after.get("roster_need") or "")
                if before_need != after_need:
                    changes.append(
                        f"보강 과제: {after_need or '해소'}"
                    )
            result[team] = " · ".join(changes) if changes else "변동 없음"
        return period_start, result

    def _add_weekly_report(self, connection, summary, report_date):
        period_start, team_changes = self._weekly_team_changes(
            connection, report_date
        )
        changed_count = sum(
            detail != "변동 없음" for detail in team_changes.values()
        )
        team_lines = "\n".join(
            f"• {team}: {team_changes[team]}" for team in TEAM_INFO
        )
        body = (
            f"보고 기간: {period_start:%Y.%m.%d} ~ {report_date:%Y.%m.%d}\n"
            f"10개 구단 {summary['player_count']}명 상태 처리 완료 · "
            f"변동 구단 {changed_count}개 · 변동 없음 {len(TEAM_INFO) - changed_count}개\n"
            f"주간 엔트리 이동과 부상 변동을 전일 및 직전 보고 상태와 비교했습니다.\n\n"
            f"[구단별 변동]\n{team_lines}"
        )
        connection.execute(
            """INSERT OR IGNORE INTO daily_news
            (save_id,news_date,category,headline,body,created_at)
            VALUES (?,?, '리그 시뮬레이션', ?, ?, CURRENT_TIMESTAMP)""",
            (
                self.save_id,
                summary["simulation_date"],
                f"{summary['season_phase']} · 10개 구단 주간 진행 보고",
                body,
            ),
        )
