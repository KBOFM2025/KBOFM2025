"""세이브별 KBO 2차 드래프트 보호 명단과 지명을 처리한다."""

from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from datetime import date, datetime
from pathlib import Path

from app.player_ratings import overall_rating


PROTECTION_LIMIT = 35
DRAFT_PREPARATION_DATE = date(2025, 11, 12)
DRAFT_DATE = date(2025, 11, 19)
DRAFT_ORDER = (
    "키움 히어로즈",
    "두산 베어스",
    "KIA 타이거즈",
    "롯데 자이언츠",
    "KT 위즈",
    "NC 다이노스",
    "삼성 라이온즈",
    "SSG 랜더스",
    "한화 이글스",
    "LG 트윈스",
)
EXTRA_ROUND_TEAMS = set(DRAFT_ORDER[:3])
ROUND_FEES = {1: 400_000_000, 2: 300_000_000, 3: 200_000_000, 4: 100_000_000, 5: 100_000_000}
POSITION_TARGETS = {"P": 24, "C": 5, "IF": 12, "OF": 9}

# 2025년 11월 8일 KBO가 공시한 2026 FA 승인 선수 21명.
FA_APPROVED_2025 = {
    ("LG 트윈스", "김현수"), ("LG 트윈스", "박해민"),
    ("한화 이글스", "김범수"), ("한화 이글스", "손아섭"),
    ("삼성 라이온즈", "김태훈"), ("삼성 라이온즈", "이승현"),
    ("삼성 라이온즈", "강민호"), ("NC 다이노스", "최원준"),
    ("KT 위즈", "강백호"), ("KT 위즈", "장성우"), ("KT 위즈", "황재균"),
    ("롯데 자이언츠", "김상수"), ("KIA 타이거즈", "양현종"),
    ("KIA 타이거즈", "이준영"), ("KIA 타이거즈", "조상우"),
    ("KIA 타이거즈", "한승택"), ("KIA 타이거즈", "박찬호"),
    ("KIA 타이거즈", "최형우"), ("두산 베어스", "이영하"),
    ("두산 베어스", "최원준"), ("두산 베어스", "조수행"),
}

# KBO 공식 2025 2차 드래프트 결과. 군보류·육성선수는 10월 31일 선수 DB에
# 없을 수 있으므로 player_id 없이도 결과 기록과 화면 표시가 가능하다.
ACTUAL_2025_RESULTS = (
    (1, 1, "키움 히어로즈", "한화 이글스", "안치홍", "IF", ""),
    (1, 2, "KIA 타이거즈", "한화 이글스", "이태양", "P", ""),
    (1, 3, "롯데 자이언츠", "LG 트윈스", "김주완", "P", "군보류"),
    (1, 4, "KT 위즈", "NC 다이노스", "안인산", "IF", ""),
    (2, 5, "키움 히어로즈", "두산 베어스", "추재현", "OF", ""),
    (2, 6, "두산 베어스", "NC 다이노스", "이용찬", "P", ""),
    (2, 7, "롯데 자이언츠", "LG 트윈스", "김영준", "P", ""),
    (2, 8, "삼성 라이온즈", "두산 베어스", "장승현", "C", ""),
    (2, 9, "SSG 랜더스", "KT 위즈", "최용준", "P", ""),
    (3, 10, "키움 히어로즈", "한화 이글스", "배동현", "P", ""),
    (3, 11, "KIA 타이거즈", "KT 위즈", "이호연", "IF", ""),
    (3, 12, "롯데 자이언츠", "삼성 라이온즈", "최충연", "P", ""),
    (3, 13, "KT 위즈", "두산 베어스", "이원재", "P", "군보류"),
    (3, 14, "삼성 라이온즈", "KIA 타이거즈", "임기영", "P", ""),
    (3, 15, "SSG 랜더스", "KT 위즈", "문상준", "IF", "육성선수"),
    (4, 16, "키움 히어로즈", "롯데 자이언츠", "박진형", "P", ""),
    (4, 17, "두산 베어스", "한화 이글스", "이상혁", "OF", ""),
)

# 10월 31일 최종 소속선수 CSV에서 빠진 군보류·육성선수. 실제 결과 모드를
# 적용할 때만 보수적인 퓨처스 능력치와 KBO 공식 프로필로 선수 DB에 보완한다.
ACTUAL_RESULT_SUPPLEMENT_PLAYERS = (
    {
        "kbo_player_id": "52140", "team": "LG 트윈스", "name": "김주완",
        "pos": "P", "position_group": "P", "age": 22,
        "birth_date": "2003-08-27", "bats_throws": "좌투좌타",
        "height_cm": 189, "weight_kg": 96,
        "career": "감천초-대동중-경남고-LG-군보류",
        "salary": 3100, "ratings": (9, 8, 10, 9, 8),
        "source_url": "https://www.koreabaseball.com/Record/Player/PitcherDetail/Basic.aspx?playerId=52140",
    },
    {
        "kbo_player_id": "52295", "team": "두산 베어스", "name": "이원재",
        "pos": "P", "position_group": "P", "age": 22,
        "birth_date": "2003-05-07", "bats_throws": "좌투좌타",
        "height_cm": 187, "weight_kg": 98,
        "career": "부산수영초-경남중-경남고-두산-상무",
        "salary": 3000, "ratings": (10, 8, 9, 9, 9),
        "source_url": "https://www.koreabaseball.com/Futures/Player/PitcherDetail/Basic.aspx?playerId=52295",
    },
    {
        "kbo_player_id": "50007", "team": "KT 위즈", "name": "문상준",
        "pos": "IF", "position_group": "IF", "age": 24,
        "birth_date": "2001-03-14", "bats_throws": "우투우타",
        "height_cm": 183, "weight_kg": 80,
        "career": "가동초-휘문중-휘문고-KT",
        "salary": 3100, "ratings": (8, 8, 8, 8, 8),
        "source_url": "https://www.koreabaseball.com/Record/Player/HitterDetail/Basic.aspx?playerId=50007",
    },
)


class SecondDraftService:
    """AI 보호 명단 산출, 실제 결과 모드, 선수 이동을 한 트랜잭션으로 관리한다."""

    def __init__(self, save_database, save_id, player_db_path):
        self.save_database = save_database
        self.save_id = int(save_id)
        self.player_db_path = Path(player_db_path)
        self._ensure_settings()

    def _ensure_settings(self):
        with self.save_database.connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO second_draft_settings (
                    save_id, mode, status, source_note
                ) VALUES (?, 'ai', 'not_prepared', ?)
                """,
                (
                    self.save_id,
                    "KBO 2025 2차 드래프트 규정 · 보호선수 최대 35명",
                ),
            )

    def settings(self):
        with self.save_database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM second_draft_settings WHERE save_id = ?",
                (self.save_id,),
            ).fetchone()
        return dict(row) if row else {
            "save_id": self.save_id, "mode": "ai", "status": "not_prepared"
        }

    def set_mode(self, mode):
        if mode not in {"ai", "actual"}:
            raise ValueError("지원하지 않는 2차 드래프트 모드입니다.")
        state = self.settings()
        if state.get("status") == "completed":
            return False
        with self.save_database.connect() as connection:
            connection.execute(
                "UPDATE second_draft_settings SET mode = ? WHERE save_id = ?",
                (mode, self.save_id),
            )
        return True

    @staticmethod
    def _entry_year(player):
        player_id = str(player.get("kbo_player_id") or "")
        decade = {"5": 2020, "6": 2010, "7": 2000, "8": 1990, "9": 1980}
        if len(player_id) >= 2 and player_id[0] in decade and player_id[1].isdigit():
            return decade[player_id[0]] + int(player_id[1])
        return None

    @staticmethod
    def _deterministic_noise(*values):
        payload = ":".join(str(value) for value in values).encode("utf-8")
        return hashlib.sha256(payload).digest()[0] / 255

    @staticmethod
    def _automatic_exemption(player, entry_year, service_year):
        if int(player.get("is_foreign") or 0):
            return "외국인선수 자동 제외"
        if (player.get("team"), player.get("name")) in FA_APPROVED_2025:
            return "당해 연도 FA 승인 선수 자동 제외"
        if service_year is not None and service_year <= 3:
            return f"입단 {service_year}년 차 자동 제외"
        career = str(player.get("career") or "")
        military_history = "상무" in career or "경찰" in career
        if service_year == 4 and military_history:
            return "입단 4년 차·군보류 이력 자동 제외"
        if int(player.get("is_rookie") or 0):
            return "신인선수 자동 제외"
        return ""

    def _evaluate_player(self, player, team_counts, simulation_state):
        overall = float(overall_rating(player))
        age = int(player.get("age") or 0)
        salary = int(player.get("salary") or 0)
        position = str(player.get("position_group") or "")
        first_team = int(bool(player.get("status")))

        age_upside = max(0.0, min(6.0, (31 - age) * 0.75))
        potential = max(1.0, min(20.0, overall + age_upside))
        target = POSITION_TARGETS.get(position, 8)
        position_count = max(1, int(team_counts.get(position, 0)))
        scarcity = max(0.0, min(8.0, (target - position_count) / target * 10))
        utilization = 10.0 if first_team else 2.0
        squad_group = str((simulation_state or {}).get("squad_group") or "")
        if squad_group == "1군":
            utilization = max(utilization, 10.0)
        elif squad_group == "2군":
            utilization = min(utilization, 3.0)

        salary_signal = min(5.0, math.log10(max(1, salary)) * 1.15)
        salary_burden = 0.0
        if age >= 32 and salary >= 50_000 and overall < 13:
            salary_burden = min(14.0, (salary / 50_000) + (13 - overall) * 2.0)
        noise = self._deterministic_noise(
            self.save_id, player.get("id"), player.get("team")
        )
        score = (
            overall * 3.4
            + potential * 0.8
            + utilization
            + scarcity
            + salary_signal
            - salary_burden
            + noise
        )
        return {
            "overall": round(overall, 1),
            "potential": round(potential, 1),
            "score": round(score, 2),
            "components": {
                "ability": round(overall * 3.4, 2),
                "potential": round(potential * 0.8, 2),
                "utilization": round(utilization, 2),
                "position_scarcity": round(scarcity, 2),
                "salary_signal": round(salary_signal, 2),
                "salary_burden": round(salary_burden, 2),
            },
        }

    def prepare_pool(self, force=False, news_date=None):
        state = self.settings()
        if state.get("status") == "completed":
            return self.list_pool()
        if state.get("status") == "prepared" and not force:
            return self.list_pool()

        player_connection = sqlite3.connect(self.player_db_path)
        player_connection.row_factory = sqlite3.Row
        try:
            players = [
                dict(row) for row in player_connection.execute(
                    "SELECT * FROM players ORDER BY team, id"
                )
            ]
        finally:
            player_connection.close()

        simulation_states = self.save_database.get_player_simulation_states(
            self.save_id
        )
        team_counts = {}
        for player in players:
            counts = team_counts.setdefault(player["team"], {})
            position = str(player.get("position_group") or "")
            counts[position] = counts.get(position, 0) + 1

        evaluated_by_team = {}
        rows = []
        for player in players:
            entry_year = self._entry_year(player)
            service_year = 2025 - entry_year + 1 if entry_year else None
            exemption = self._automatic_exemption(
                player, entry_year, service_year
            )
            evaluation = self._evaluate_player(
                player,
                team_counts.get(player["team"], {}),
                simulation_states.get(player["id"]),
            )
            row = {
                "player": player,
                "entry_year": entry_year,
                "service_year": service_year,
                "exemption": exemption,
                **evaluation,
            }
            rows.append(row)
            if not exemption:
                evaluated_by_team.setdefault(player["team"], []).append(row)

        protected_ids = set()
        for candidates in evaluated_by_team.values():
            candidates.sort(
                key=lambda item: (
                    item["score"], item["potential"],
                    item["overall"], -int(item["player"].get("age") or 0),
                ),
                reverse=True,
            )
            protected_ids.update(
                item["player"]["id"] for item in candidates[:PROTECTION_LIMIT]
            )

        now = datetime.now().isoformat(timespec="seconds")
        with self.save_database.connect() as connection:
            connection.execute(
                "DELETE FROM second_draft_pool WHERE save_id = ?",
                (self.save_id,),
            )
            for item in rows:
                player = item["player"]
                if item["exemption"]:
                    classification = "automatic_exempt"
                    reason = item["exemption"]
                elif player["id"] in protected_ids:
                    classification = "protected"
                    reason = "AI 보호선수 35명 선정"
                else:
                    classification = "available"
                    reason = "보호선수 35명 외 지명 가능 선수"
                connection.execute(
                    """
                    INSERT INTO second_draft_pool (
                        save_id, player_id, kbo_player_id, player_name,
                        original_team, position_group, age, entry_year,
                        service_year, roster_status, salary, overall,
                        potential, protection_score, classification, reason,
                        component_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        self.save_id, player["id"],
                        str(player.get("kbo_player_id") or ""),
                        player.get("name") or "",
                        player.get("team") or "",
                        player.get("position_group") or "",
                        int(player.get("age") or 0), item["entry_year"],
                        item["service_year"], int(bool(player.get("status"))),
                        int(player.get("salary") or 0), item["overall"],
                        item["potential"], item["score"], classification, reason,
                        json.dumps(
                            item["components"], ensure_ascii=False,
                            separators=(",", ":"),
                        ),
                    ),
                )
            connection.execute(
                """
                UPDATE second_draft_settings
                SET status = 'prepared', prepared_at = ?
                WHERE save_id = ?
                """,
                (now, self.save_id),
            )
        self.save_database.add_daily_news(
            self.save_id,
            (
                news_date.isoformat()
                if isinstance(news_date, date)
                else str(news_date or DRAFT_PREPARATION_DATE.isoformat())
            ),
            "KBO",
            "2차 드래프트 보호선수 및 지명 대상 명단 확정",
            "10개 구단 AI가 능력치·잠재력·연봉·1군 활용도·포지션 희소성을 "
            "반영해 보호선수 최대 35명을 확정했습니다. 이 소식의 명단 확인을 "
            "누르면 구단별 지명 가능 선수를 확인할 수 있습니다.",
        )
        return self.list_pool()

    def list_pool(self, classification=None, team=None):
        conditions = ["save_id = ?"]
        parameters = [self.save_id]
        if classification:
            conditions.append("classification = ?")
            parameters.append(classification)
        if team:
            conditions.append("original_team = ?")
            parameters.append(team)
        with self.save_database.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT * FROM second_draft_pool
                WHERE {' AND '.join(conditions)}
                ORDER BY original_team,
                         CASE classification
                           WHEN 'available' THEN 0
                           WHEN 'protected' THEN 1
                           ELSE 2
                         END,
                         protection_score DESC, player_name
                """,
                parameters,
            ).fetchall()
        return [dict(row) for row in rows]

    def list_results(self, mode=None):
        mode = mode or self.settings().get("mode", "ai")
        if mode == "actual":
            with self.save_database.connect() as connection:
                stored = connection.execute(
                    """
                    SELECT * FROM second_draft_results
                    WHERE save_id = ? AND mode = 'actual'
                    ORDER BY pick_order
                    """,
                    (self.save_id,),
                ).fetchall()
            if stored:
                return [dict(row) for row in stored]
            return [
                {
                    "round_no": round_no, "pick_order": pick_order,
                    "selecting_team": selecting_team,
                    "original_team": original_team, "player_name": player_name,
                    "position_group": position_group,
                    "fee": ROUND_FEES[round_no], "note": note,
                }
                for (
                    round_no, pick_order, selecting_team, original_team,
                    player_name, position_group, note
                ) in ACTUAL_2025_RESULTS
            ]
        with self.save_database.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM second_draft_results
                WHERE save_id = ? AND mode = ?
                ORDER BY pick_order
                """,
                (self.save_id, mode),
            ).fetchall()
        return [dict(row) for row in rows]

    def _team_need(self, players, team, position):
        group = [
            player for player in players
            if player.get("team") == team
            and player.get("position_group") == position
        ]
        target = POSITION_TARGETS.get(position, 8)
        shortage = max(0.0, (target - len(group)) / target)
        quality = (
            sum(float(overall_rating(player)) for player in group) / len(group)
            if group else 0.0
        )
        return shortage * 16 + max(0.0, 11.5 - quality) * 2.2

    def _run_ai_draft(self, players):
        available = self.list_pool("available")
        players_by_id = {player["id"]: player for player in players}
        picked_ids = set()
        losses = {}
        incoming_positions = {}
        results = []
        pick_order = 0

        for round_no in range(1, 6):
            teams = DRAFT_ORDER if round_no <= 3 else tuple(
                team for team in DRAFT_ORDER if team in EXTRA_ROUND_TEAMS
            )
            for selecting_team in teams:
                candidates = []
                for candidate in available:
                    if (
                        candidate["player_id"] in picked_ids
                        or candidate["original_team"] == selecting_team
                        or losses.get(candidate["original_team"], 0) >= 4
                    ):
                        continue
                    player = players_by_id.get(candidate["player_id"], {})
                    need = self._team_need(
                        players, selecting_team, candidate["position_group"]
                    )
                    salary_penalty = max(
                        0.0,
                        math.log10(max(1, candidate["salary"])) - 4.5,
                    ) * 3.0
                    utility = (
                        candidate["overall"] * 4.2
                        + candidate["potential"] * 1.5
                        + need
                        + (4 if candidate["roster_status"] else 0)
                        - incoming_positions.get(
                            (selecting_team, candidate["position_group"]), 0
                        ) * 7
                        - salary_penalty
                        + self._deterministic_noise(
                            self.save_id, selecting_team,
                            candidate["player_id"], round_no,
                        ) * 2
                    )
                    candidates.append((utility, candidate, player))
                if not candidates:
                    continue
                candidates.sort(key=lambda item: item[0], reverse=True)
                utility, candidate, _player = candidates[0]
                threshold = {1: 62, 2: 60, 3: 58, 4: 56, 5: 55}[round_no]
                if utility < threshold:
                    continue
                pick_order += 1
                picked_ids.add(candidate["player_id"])
                losses[candidate["original_team"]] = (
                    losses.get(candidate["original_team"], 0) + 1
                )
                position_key = (
                    selecting_team, candidate["position_group"]
                )
                incoming_positions[position_key] = (
                    incoming_positions.get(position_key, 0) + 1
                )
                results.append(
                    {
                        "round_no": round_no,
                        "pick_order": pick_order,
                        "selecting_team": selecting_team,
                        "original_team": candidate["original_team"],
                        "player_id": candidate["player_id"],
                        "kbo_player_id": candidate["kbo_player_id"],
                        "player_name": candidate["player_name"],
                        "position_group": candidate["position_group"],
                        "fee": ROUND_FEES[round_no],
                        "note": f"AI 지명 가치 {utility:.1f}",
                    }
                )
        return results

    def _actual_results_for_database(self, players):
        player_lookup = {
            (player.get("team"), player.get("name")): player
            for player in players
        }
        results = []
        for (
            round_no, pick_order, selecting_team, original_team,
            player_name, position_group, note,
        ) in ACTUAL_2025_RESULTS:
            player = player_lookup.get((original_team, player_name))
            results.append(
                {
                    "round_no": round_no, "pick_order": pick_order,
                    "selecting_team": selecting_team,
                    "original_team": original_team,
                    "player_id": player.get("id") if player else None,
                    "kbo_player_id": (
                        str(player.get("kbo_player_id") or "") if player else ""
                    ),
                    "player_name": player_name,
                    "position_group": position_group,
                    "fee": ROUND_FEES[round_no],
                    "note": note or ("선수 DB 외 군보류·육성선수" if not player else ""),
                }
            )
        return results

    @staticmethod
    def _ensure_actual_result_players(connection):
        for player in ACTUAL_RESULT_SUPPLEMENT_PLAYERS:
            existing = connection.execute(
                "SELECT id FROM players WHERE kbo_player_id = ?",
                (player["kbo_player_id"],),
            ).fetchone()
            if existing:
                continue
            is_pitcher = player["position_group"] == "P"
            rating_one, rating_two, rating_three, rating_four, rating_five = (
                player["ratings"]
            )
            connection.execute(
                """
                INSERT INTO players (
                    player_uid, kbo_player_id, team, name, pos, age,
                    birth_date, bats_throws, height_cm, weight_kg, career,
                    con, pow, eye, def, contact, power, plate_discipline,
                    bat_control, timing, pitcher_stuff, pitcher_command,
                    pitcher_movement, pitcher_stamina, pitcher_pitchability,
                    status, lineup_pos, role, salary, snapshot_date,
                    position_group, is_rookie, is_foreign, profile_complete,
                    ability_source_level, ability_formula_version,
                    pitcher_source_level, pitcher_confidence,
                    pitcher_formula_version, source_note, source_url
                ) VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    0, 0, '군보류·육성선수', ?, '2025-11-19',
                    ?, 0, 0, 1, ?, ?, ?, ?, ?, ?, ?
                )
                """,
                (
                    f"KBO-{player['kbo_player_id']}",
                    player["kbo_player_id"], player["team"], player["name"],
                    player["pos"], player["age"], player["birth_date"],
                    player["bats_throws"], player["height_cm"],
                    player["weight_kg"], player["career"],
                    rating_one, rating_two, rating_three, rating_four,
                    None if is_pitcher else rating_one,
                    None if is_pitcher else rating_two,
                    None if is_pitcher else rating_three,
                    None if is_pitcher else rating_four,
                    None if is_pitcher else rating_five,
                    rating_one if is_pitcher else None,
                    rating_two if is_pitcher else None,
                    rating_three if is_pitcher else None,
                    rating_four if is_pitcher else None,
                    rating_five if is_pitcher else None,
                    player["salary"], player["position_group"],
                    "KBO 퓨처스" if not is_pitcher else None,
                    "kbo-second-draft-supplement-v1" if not is_pitcher else None,
                    "KBO 퓨처스" if is_pitcher else None,
                    "low" if is_pitcher else None,
                    "kbo-second-draft-supplement-v1" if is_pitcher else None,
                    "KBO 공식 2025 2차 드래프트 결과 보완 선수",
                    player["source_url"],
                ),
            )

    def execute_draft(self, event_date=None):
        state = self.settings()
        if state.get("status") == "completed":
            return self.list_results(state.get("mode"))
        if state.get("status") != "prepared":
            self.prepare_pool(news_date=event_date)
        mode = self.settings().get("mode", "ai")

        player_connection = sqlite3.connect(self.player_db_path)
        player_connection.row_factory = sqlite3.Row
        try:
            if mode == "actual":
                self._ensure_actual_result_players(player_connection)
                player_connection.commit()
            players = [
                dict(row) for row in player_connection.execute(
                    "SELECT * FROM players"
                )
            ]
            results = (
                self._actual_results_for_database(players)
                if mode == "actual" else self._run_ai_draft(players)
            )
        finally:
            player_connection.close()

        now = datetime.now().isoformat(timespec="seconds")
        with self.save_database.connect() as save_connection:
            save_connection.execute(
                "ATTACH DATABASE ? AS playerdb",
                (str(self.player_db_path),),
            )
            try:
                save_connection.execute("BEGIN IMMEDIATE")
                save_connection.execute(
                    "DELETE FROM second_draft_results WHERE save_id = ? AND mode = ?",
                    (self.save_id, mode),
                )
                for result in results:
                    save_connection.execute(
                        """
                        INSERT INTO second_draft_results (
                            save_id, mode, round_no, pick_order,
                            selecting_team, original_team, player_id,
                            kbo_player_id, player_name, position_group,
                            fee, note
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            self.save_id, mode, result["round_no"],
                            result["pick_order"], result["selecting_team"],
                            result["original_team"], result["player_id"],
                            result["kbo_player_id"], result["player_name"],
                            result["position_group"], result["fee"],
                            result["note"],
                        ),
                    )
                    if result["player_id"] is not None:
                        save_connection.execute(
                            """
                            UPDATE playerdb.players
                            SET team = ?, status = 0, lineup_pos = 0,
                                role = '2차 드래프트 영입'
                            WHERE id = ?
                            """,
                            (result["selecting_team"], result["player_id"]),
                        )
                        save_connection.execute(
                            """
                            UPDATE player_simulation_states
                            SET team = ?, squad_group = '2군',
                                last_updated = ?
                            WHERE save_id = ? AND player_id = ?
                            """,
                            (
                                result["selecting_team"], now,
                                self.save_id, result["player_id"],
                            ),
                        )
                save_connection.execute(
                    """
                    UPDATE second_draft_settings
                    SET status = 'completed', completed_at = ?
                    WHERE save_id = ?
                    """,
                    (now, self.save_id),
                )
                save_connection.commit()
            except Exception:
                save_connection.rollback()
                raise
            finally:
                save_connection.execute("DETACH DATABASE playerdb")

        mode_name = "실제 2025 결과" if mode == "actual" else "구단 AI 시뮬레이션"
        self.save_database.add_daily_news(
            self.save_id,
            (
                event_date.isoformat()
                if isinstance(event_date, date)
                else str(event_date or DRAFT_DATE.isoformat())
            ),
            "KBO",
            f"2025 KBO 2차 드래프트 종료 · {len(results)}명 지명",
            f"{mode_name} 방식으로 2차 드래프트가 종료됐습니다. "
            "지명 선수는 새 구단 2군 선수단으로 이동했습니다. 이 소식의 결과 "
            "확인을 누르면 라운드별 이적과 양도금을 확인할 수 있습니다.",
        )
        return results

    def process_date(self, game_date):
        """일일 진행에서 공식 일정 당일에 한 번만 준비·지명을 수행한다."""
        if isinstance(game_date, str):
            game_date = date.fromisoformat(game_date)
        state = self.settings()
        if (
            game_date >= DRAFT_PREPARATION_DATE
            and state["status"] != "completed"
        ):
            self.set_mode("ai")
            state = self.settings()
        if game_date >= DRAFT_PREPARATION_DATE and state["status"] == "not_prepared":
            self.prepare_pool(news_date=game_date)
            state = self.settings()
        if game_date >= DRAFT_DATE and state["status"] == "prepared":
            self.execute_draft(event_date=game_date)
