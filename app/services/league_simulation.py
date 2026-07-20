"""모든 구단의 하루를 한 트랜잭션으로 진행하는 오프시즌 시뮬레이션 엔진."""

import hashlib
import json
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta

from app.config import TEAM_INFO
from app.config.season_schedule import SEASON_EVENTS, phase_for
from app.services.team_lineup_engine import TeamLineupEngine, availability_score
from database.league_simulation_repository import LeagueSimulationRepository


POSITION_MINIMUMS = {"P": 13, "C": 2, "IF": 6, "OF": 5}
ROSTER_EVALUATION_DATES = {
    "2025-11-12", "2025-11-27", "2025-12-15", "2025-12-22",
    "2026-01-19", "2026-01-31", "2026-02-07", "2026-02-14",
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

    def choose(self, team, players, states, profile, simulation_date):
        first = [p for p in players if int(p.get("status") or 0) == 1]
        second = [p for p in players if int(p.get("status") or 0) == 0]
        if not first or not second:
            return []
        decisions, used = [], set()
        for injured in sorted(first, key=lambda p: states[p["id"]]["injury_days"], reverse=True):
            if states[injured["id"]]["injury_days"] <= 0:
                continue
            candidates = [p for p in second if p["id"] not in used
                          and p.get("position_group") == injured.get("position_group")
                          and states[p["id"]]["injury_days"] == 0]
            if not candidates:
                continue
            promote = max(candidates, key=lambda p: availability_score(p, states[p["id"]], profile["development"]))
            reason = f"{injured['name']}의 {states[injured['id']]['injury_type']} 이탈에 따른 대체 등록"
            decisions.extend(self._swap(team, injured, promote, reason))
            used.add(promote["id"])
        if simulation_date.isoformat() not in ROSTER_EVALUATION_DATES:
            return decisions

        changed = {d["player_id"] for d in decisions}
        first = [p for p in first if p["id"] not in changed]
        second = [p for p in second if p["id"] not in changed]
        max_swaps = 2 if profile["roster_aggression"] >= 4 else 1
        for group in POSITION_MINIMUMS:
            if len(decisions) // 2 >= max_swaps:
                break
            incumbents = [p for p in first if p.get("position_group") == group and states[p["id"]]["injury_days"] == 0]
            challengers = [p for p in second if p.get("position_group") == group and states[p["id"]]["injury_days"] == 0]
            if not incumbents or not challengers:
                continue
            demote = min(incumbents, key=lambda p: availability_score(p, states[p["id"]], profile["development"]))
            promote = max(challengers, key=lambda p: availability_score(p, states[p["id"]], profile["development"]))
            old_score = availability_score(demote, states[demote["id"]], profile["development"])
            new_score = availability_score(promote, states[promote["id"]], profile["development"])
            threshold = 3.5 - profile["roster_aggression"] * .45 - profile["development"] * .2
            if new_score > old_score + threshold:
                reason = f"정기 전력 평가: {promote['name']}({new_score:.1f})가 {demote['name']}({old_score:.1f})보다 높은 평가"
                decisions.extend(self._swap(team, demote, promote, reason))
        return decisions

    @staticmethod
    def _swap(team, demote, promote, reason):
        return [
            {"team": team, "player_id": demote["id"], "player_name": demote["name"], "action": "demote", "reason": reason},
            {"team": team, "player_id": promote["id"], "player_name": promote["name"], "action": "promote", "reason": reason},
        ]


class LeagueSimulationService:
    def __init__(self, save_database, save_id, player_db_path, managed_team):
        self.save_database = save_database
        self.save_id = save_id
        self.managed_team = managed_team
        self.repository = LeagueSimulationRepository(save_database.db_path, player_db_path)
        self.decision_engine = DailyTeamDecisionEngine()
        self.lineup_engine = TeamLineupEngine()

    def simulate_day(self, simulation_date):
        if isinstance(simulation_date, str):
            simulation_date = date.fromisoformat(simulation_date)
        day = simulation_date.isoformat()
        _sim_log(f"{day} 하루 진행 시작 · 사용자 구단: {self.managed_team}")
        with self.repository.transaction() as connection:
            completed = self.repository.completed_summary(connection, self.save_id, day)
            if completed is not None:
                _sim_log(f"{day}은 이미 처리된 날짜입니다 · 저장된 결과 사용")
                return completed
            self.repository.begin_run(connection, self.save_id, day)
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
            decisions = []
            for team in TEAM_INFO:
                if team == self.managed_team:
                    continue
                selected = self.decision_engine.choose(team, by_team.get(team, []), states, profiles[team], simulation_date)
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

            events = SEASON_EVENTS.get(simulation_date, ())
            queued_count = self._save_events_and_ai_queue(connection, day, events, profiles)
            if events:
                _sim_log(f"일정 이벤트 {len(events)}건 반영 · Qwen 검토 대기 {queued_count}건")
            self.repository.add_league_news(connection, self.save_id, day, decisions)
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
            }
            self._add_daily_report(connection, summary)
            self.repository.complete_run(connection, self.save_id, day, summary)
            _sim_log(f"{day} 트랜잭션 저장 완료 · 엔트리 이동 {len(decisions)}건 · 전체 편성 {lineup_count}건")
            return summary

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
        """모든 구단의 부상과 복귀를 선수별 상세 뉴스로 기록한다."""
        day = simulation_date.isoformat()
        for injury in injuries:
            if injury["squad"] != "1군":
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
            if recovery["squad"] != "1군":
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

        active = connection.execute(
            """SELECT state.team, player.name, player.pos, player.status,
            state.injury_type, state.injury_days
            FROM player_simulation_states state
            JOIN playerdb.players player ON player.id=state.player_id
            WHERE state.save_id=? AND state.injury_days>0 AND player.status=1
            ORDER BY state.team, player.status DESC, state.injury_days DESC, player.name""",
            (self.save_id,),
        ).fetchall()
        if active:
            details = [
                f"• {row['team']} · {row['name']}({row['pos']}, {'1군' if row['status'] else '2군'})"
                f" — {row['injury_type']}, 복귀까지 {row['injury_days']}일"
                for row in active
            ]
            connection.execute(
                """INSERT OR IGNORE INTO daily_news
                (save_id,news_date,category,headline,body,created_at)
                VALUES (?,?, '의료 센터', ?, ?, CURRENT_TIMESTAMP)""",
                (self.save_id, day, f"KBO 부상자 현황 · 총 {len(active)}명", "\n".join(details)),
            )

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

    def _save_events_and_ai_queue(self, connection, day, events, profiles):
        queued = 0
        for team in TEAM_INFO:
            for event in events:
                self.repository.save_schedule_event(connection, self.save_id, day, team, event)
                if team == self.managed_team or event.get("importance") != "high":
                    continue
                context = {"event": event, "profile": profiles[team], "instruction": "구단 성향과 선수단 상태에 맞는 실행안을 생성"}
                cursor = connection.execute(
                    "INSERT OR IGNORE INTO team_ai_decision_queue (save_id,decision_date,team,decision_type,context_json) VALUES (?,?,?,?,?)",
                    (self.save_id, day, team, event["category"], json.dumps(context, ensure_ascii=False)))
                queued += cursor.rowcount
        return queued

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

    def _add_daily_report(self, connection, summary):
        changed = ", ".join(summary["changed_teams"]) or "없음"
        body = (
            f"10개 구단 {summary['player_count']}명 상태 처리 완료 · "
            f"1군 신규 부상 {summary['first_team_injury_count']}명 · "
            f"1군 복귀 {summary['first_team_recovery_count']}명\n"
            f"1·2군 타순/투수 보직 {summary['lineup_assignment_count']}건 편성 · "
            f"엔트리 이동 {summary['roster_decision_count']}건 · 변동 구단: {changed}\n"
            f"중요 일정 AI 검토 {summary['ai_queue_count']}건은 백그라운드에서 진행됩니다."
        )
        connection.execute(
            """INSERT OR IGNORE INTO daily_news
            (save_id,news_date,category,headline,body,created_at)
            VALUES (?,?, '리그 시뮬레이션', ?, ?, CURRENT_TIMESTAMP)""",
            (self.save_id, summary["simulation_date"],
             f"{summary['season_phase']} · 10개 구단 하루 진행 완료", body),
        )
