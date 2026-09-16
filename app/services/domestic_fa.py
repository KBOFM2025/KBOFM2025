"""국내 FA 시장과 에이전트 협상을 처리하는 결정론적 서비스."""

from __future__ import annotations

import sqlite3
from datetime import date

from app.player_ratings import overall_rating
from app.services.salary_cap import salary_cap_summary
from app.services.second_draft import FA_APPROVED_2025


class DomesticFAService:
    MARKET_OPEN_DATE = date(2025, 11, 9)

    def __init__(
        self, saves_db_path, player_db_path, save_id, team,
        current_date=None,
    ):
        self.saves_db_path = str(saves_db_path)
        self.player_db_path = str(player_db_path)
        self.save_id = int(save_id)
        self.team = team
        self.current_date = self._as_date(current_date)
        self._sessions = {}

    @staticmethod
    def _as_date(value):
        if isinstance(value, str):
            return date.fromisoformat(value)
        return value or date(2025, 11, 1)

    def set_game_date(self, value):
        self.current_date = self._as_date(value)

    def market_is_open(self):
        return self.current_date >= self.MARKET_OPEN_DATE

    def market_status(self):
        return {
            "open": self.market_is_open(),
            "open_date": self.MARKET_OPEN_DATE,
            "label": (
                "협상 가능"
                if self.market_is_open() else
                f"{self.MARKET_OPEN_DATE.strftime('%m월 %d일')} 협상 개장"
            ),
        }

    def _market_strategy(self):
        connection = sqlite3.connect(self.saves_db_path)
        try:
            row = connection.execute(
                """
                SELECT decision FROM offseason_strategy_decisions
                WHERE save_id=? AND team=? AND event_id='fa_market_open'
                """,
                (self.save_id, self.team),
            ).fetchone()
            return str(row[0]) if row else ""
        except sqlite3.OperationalError:
            return ""
        finally:
            connection.close()

    def _players(self):
        connection = sqlite3.connect(self.player_db_path)
        connection.row_factory = sqlite3.Row
        try:
            return [dict(row) for row in connection.execute("SELECT * FROM players")]
        finally:
            connection.close()

    @staticmethod
    def _grade(player, players):
        age = int(player.get("age") or 0)
        if age >= 35:
            return "C"
        salary = int(player.get("salary") or 0)
        team_rank = 1 + sum(
            int(other.get("salary") or 0) > salary
            for other in players if other.get("team") == player.get("team")
            and not int(other.get("is_foreign") or 0)
        )
        league_rank = 1 + sum(
            int(other.get("salary") or 0) > salary
            for other in players if not int(other.get("is_foreign") or 0)
        )
        if team_rank <= 3 and league_rank <= 30:
            return "A"
        if team_rank <= 10 and league_rank <= 60:
            return "B"
        return "C"

    @staticmethod
    def _role(overall):
        return "핵심 선수" if overall >= 15 else "주전" if overall >= 12.5 else "로테이션"

    @staticmethod
    def _usage_options(player):
        is_pitcher = (player.get("position_group") or player.get("pos")) == "P"
        if is_pitcher:
            return ("선발 로테이션 고정", "선발 20경기 이상", "필승조 우선", "상황별 기용")
        return ("선발 출장 120경기 이상", "선발 출장 100경기 이상", "플래툰 기용", "출장 보장 없음")

    def market_players(self):
        players = self._players()
        result = []
        for player in players:
            if (player.get("team"), player.get("name")) not in FA_APPROVED_2025:
                continue
            overall = float(overall_rating(player))
            grade = self._grade(player, players)
            compensation_rate = {"A": 2.0, "B": 1.0, "C": 1.5}[grade]
            is_external = player.get("team") != self.team
            result.append({
                **player,
                "overall": round(overall, 1),
                "fa_grade": grade,
                "desired_role": self._role(overall),
                "compensation": int(round(int(player.get("salary") or 0) * compensation_rate)) if is_external else 0,
                "player_compensation": bool(is_external and grade in {"A", "B"}),
                "is_external": is_external,
                "available": (
                    self.market_is_open()
                    and player.get("role") != "FA 영입"
                ),
            })
        strategy = self._market_strategy()
        if strategy == "internal_first":
            key = lambda item: (
                item["is_external"], -item["overall"], item["name"],
            )
        elif strategy == "value":
            key = lambda item: (
                int(item["compensation"])
                + int(item.get("salary") or 0) * 2,
                -item["overall"], item["name"],
            )
        else:
            key = lambda item: (-item["overall"], item["name"])
        return sorted(result, key=key)

    def open_agent_talk(self, player_id):
        if not self.market_is_open():
            raise ValueError(
                "KBO 국내 FA 협상 시장은 2025년 11월 9일에 개장합니다."
            )
        existing = self._sessions.get(int(player_id))
        if existing:
            return dict(existing)
        player = next(item for item in self.market_players() if int(item["id"]) == int(player_id))
        age = int(player.get("age") or 30)
        overall = float(player["overall"])
        current_salary = max(3000, int(player.get("salary") or 3000))
        value_salary = int(round(max(
            current_salary * 1.12,
            max(3000, (overall - 7.5) ** 2 * 2100),
        ) / 100) * 100)
        years = 4 if age <= 29 else 3 if age <= 32 else 2 if age <= 35 else 1
        bonus = int(round(value_salary * (0.35 if overall >= 14 else 0.2) / 100) * 100)
        incentive = int(round(value_salary * years * 0.12 / 100) * 100)
        roster = [p for p in self._players() if p.get("team") == self.team]
        same_position = [
            float(overall_rating(p)) for p in roster
            if (p.get("position_group") or p.get("pos")) ==
               (player.get("position_group") or player.get("pos"))
        ]
        need = max(0, overall - (sum(same_position) / max(1, len(same_position))))
        interest = max(20, min(90, round(48 + need * 4 - max(0, age - 34) * 2)))
        cap_connection = sqlite3.connect(self.player_db_path)
        cap_connection.row_factory = sqlite3.Row
        try:
            cap = salary_cap_summary(
                cap_connection, self.team, 2026,
                value_salary + round((bonus + incentive * 0.55) / max(1, years))
            )
        finally:
            cap_connection.close()
        usage_options = self._usage_options(player)
        desired_usage = usage_options[0] if player["desired_role"] in {"핵심 선수", "주전"} else usage_options[1]
        session = {
            "player": player, "asking_salary": value_salary,
            "asking_years": years, "asking_bonus": bonus,
            "asking_incentive": incentive, "asking_transfer_fee": 0,
            "desired_role": player["desired_role"], "desired_usage": desired_usage,
            "interest": interest,
            "status": "preliminary", "lowballs": 0, "round": 0,
            "salary_cap": cap,
            "discussed_actions": [],
            "can_negotiate": bool(player.get("available", True)),
            "reason": "협상 가능" if player.get("available", True) else "이미 계약이 완료된 선수입니다.",
            "subtitle": f"국내 FA · {player['fa_grade']}등급 · {'외부 영입' if player['is_external'] else '원소속 재계약'}",
            "summary": f"종합 {player['overall']} · FA {player['fa_grade']}등급 · 선수 측 세부 요구는 에이전트 확인 필요",
            "initial_message": (
                "정식 계약 조건을 받기 전에 구단의 영입 의지와 기용 계획을 확인하고 싶습니다. "
                "사전 협의가 끝나면 선수 가치에 근거해 조건을 검토하겠습니다."
            ),
            "currency": "KRW_10K", "fields": (
                "years", "salary", "bonus", "incentive", "role", "usage",
            ),
            "max_value": 500_000, "money_step": 100, "max_years": 6,
            "role_options": ("핵심 선수", "주전", "로테이션", "백업"),
            "usage_options": usage_options,
            "role_guidance": ("투수의 선발 전환은 ‘출장·등판 계획’에서 제안할 수 있습니다. "
                              "계약 후 라인업 편성 → 선발 · 불펜에서 배치하고 저장하세요. "
                              "기용 약속과 실제 선발 적합성은 별개입니다.")
                              if (player.get('position_group') or player.get('pos')) == 'P' else '',
            "demand_revealed": False,
            "demand_message": (
                f"선수의 정확한 요구는 {years}년, 연봉 {value_salary:,}만원, "
                f"계약금 {bonus:,}만원, 성적 옵션 {incentive:,}만원입니다. "
                f"희망 지위는 {player['desired_role']}, "
                f"기용 기대치는 '{desired_usage}'입니다."
            ),
            "rules_summary": (
                f"2026 경쟁균형세: 현재 {cap['current']:,}만원 / 상한 {cap['limit']:,}만원 · "
                + (f"요구안 반영 시 {cap['excess']:,}만원 초과" if cap["excess"]
                   else f"요구안 반영 후 {cap['projected_room']:,}만원 여유")
            ),
        }
        self._sessions[int(player_id)] = session
        return dict(session)

    def agent_message(self, player_id, action):
        session = self._sessions[int(player_id)]
        if not session.get("can_negotiate", True):
            return session.get("reason", "협상을 진행할 수 없습니다.")
        player = session["player"]
        if action == "invite":
            if not session.get("demand_revealed"):
                return "정식 협상 초대 전에 선수 측 요구 조건부터 확인해 주십시오."
            session["status"] = "ready"
            return "선수가 정식 계약 협상에 응하겠습니다. 이제 계약 조건을 제시해 주십시오."
        if action == "later":
            session["status"] = "deferred"
            return "알겠습니다. 선수는 다른 구단의 제안도 검토하며 다시 연락을 기다리겠습니다."
        if action == "reject":
            session["status"] = "withdrawn"
            return "구단의 의사를 선수에게 전달하겠습니다. 이번 사전 협의는 여기서 종료하겠습니다."
        if action in session.get("discussed_actions", []):
            return "이 항목에 대한 선수 측 입장은 이미 전달했습니다. 계약 조건을 제시해 주십시오."
        session.setdefault("discussed_actions", []).append(action)
        session["status"] = "consulting"
        if action == "terms":
            session["demand_revealed"] = True
            session["summary"] = session["demand_message"]
            return session["demand_message"]
        session["interest"] = min(100, session["interest"] + 5)
        return (
            f"{self.team}의 기용 계획은 선수에게 전달하겠습니다. 다만 {player['name']}은 "
            f"{session['desired_role']} 지위와 '{session['desired_usage']}' 수준의 출전 계획이 "
            "계약 합의에 반영되길 원합니다."
        )

    def submit_offer(
        self, player_id, years, salary, bonus, role, usage="", incentive=0,
    ):
        session = self._sessions[int(player_id)]
        if session["status"] in {"withdrawn", "signed"}:
            return {"status": session["status"], "message": "이미 종료된 협상입니다."}
        if session["status"] not in {"ready", "countered", "accepted"}:
            return {"status": session["status"], "message": "먼저 에이전트 사전 협의를 마치고 선수를 계약 협상에 초대해 주십시오."}
        session["round"] += 1
        years, salary = max(1, int(years)), max(0, int(salary))
        bonus, incentive = max(0, int(bonus)), max(0, int(incentive))
        demand_guaranteed = (
            session["asking_salary"] * session["asking_years"]
            + session["asking_bonus"]
        )
        demand_total = demand_guaranteed + round(
            int(session.get("asking_incentive") or 0) * 0.55
        )
        offer_guaranteed = salary * years + bonus
        offer_total = offer_guaranteed + round(incentive * 0.55)
        money_score = offer_total / max(1, demand_total) * 78
        annual_score = min(18, salary / max(1, session["asking_salary"]) * 18)
        guarantee_penalty = max(
            0, (0.82 - offer_guaranteed / max(1, demand_guaranteed)) * 45
        )
        role_score = 12 if role == session["desired_role"] else 5 if role != "백업" else -4
        usage_score = 8 if usage == session.get("desired_usage") else 2 if "보장 없음" not in usage else -6
        interest_score = (session["interest"] - 50) * 0.22
        term_penalty = abs(years - session["asking_years"]) * 4
        score = (
            money_score + annual_score + role_score + usage_score
            + interest_score - term_penalty - guarantee_penalty
        )
        if score >= 102:
            session.update(
                status="accepted", agreed_years=years, agreed_salary=salary,
                agreed_bonus=bonus, agreed_incentive=incentive,
                agreed_role=role, agreed_usage=usage,
            )
            return {"status": "accepted", "message": "에이전트가 선수의 계약 수락 의사를 전달했습니다.", "score": round(score, 1)}
        if score < 68:
            session["lowballs"] += 1
            if session["lowballs"] >= 2:
                session["status"] = "withdrawn"
                return {"status": "withdrawn", "message": "에이전트가 반복된 저가 제안에 협상을 중단했습니다.", "score": round(score, 1)}
        gap = max(0.0, 1.0 - offer_total / max(1, demand_total))
        reduction = min(0.08, session["interest"] / 1500)
        session["asking_salary"] = int(round(session["asking_salary"] * (1 - reduction) / 100) * 100)
        session["asking_bonus"] = int(round(session["asking_bonus"] * (1 - reduction / 2) / 100) * 100)
        # 보장액을 내린 대신 옵션을 넣은 제안이라면 에이전트도 역제안의
        # 일부를 성과급으로 이동한다. 옵션은 기대 달성률 55%만 가치로 본다.
        if incentive > int(session.get("asking_incentive") or 0):
            shifted = min(
                int(session["asking_bonus"] * 0.18),
                max(0, incentive - int(session.get("asking_incentive") or 0)),
            )
            session["asking_bonus"] -= shifted
            session["asking_incentive"] = max(
                int(session.get("asking_incentive") or 0), incentive
            )
        session["status"] = "countered"
        return {
            "status": "countered", "score": round(score, 1),
            "asking_salary": session["asking_salary"], "asking_bonus": session["asking_bonus"],
            "asking_incentive": session["asking_incentive"],
            "asking_years": session["asking_years"], "desired_role": session["desired_role"],
            "desired_usage": session["desired_usage"],
            "message": (
                "조건 차이가 남아 있습니다. 에이전트가 수정 요구안을 제시했습니다. "
                if gap < 0.35 else "현재 제안은 선수 가치와 기대 역할에 미치지 못합니다."
            ),
        }

    def submit_contract_offer(self, player_id, offer):
        """통합 협상 화면에서 사용하는 공통 계약 제안 인터페이스."""
        return self.submit_offer(
            player_id, offer.get("years", 1), offer.get("salary", 0),
            offer.get("bonus", 0), offer.get("role", ""), offer.get("usage", ""),
            offer.get("incentive", 0),
        )

    def contract_talk_ready(self, player_id):
        session = self._sessions.get(int(player_id))
        return bool(session and session.get("status") in {"ready", "countered", "accepted", "signed"})

    def finalize(self, player_id):
        session = self._sessions[int(player_id)]
        if session.get("status") != "accepted":
            return False, "아직 선수 측의 계약 동의를 얻지 못했습니다."
        player = session["player"]
        all_players = self._players()
        external_signed = sum(
            p.get("team") == self.team
            and str(p.get("contract_note") or "").startswith("외부 FA 영입")
            for p in all_players
        )
        if player["is_external"] and external_signed >= 3:
            return False, "타 구단 FA 영입 한도 3명을 이미 채웠습니다."
        connection = sqlite3.connect(self.player_db_path)
        connection.row_factory = sqlite3.Row
        try:
            cap = salary_cap_summary(
                connection, self.team, 2026,
                session["agreed_salary"]
                + round(
                    (session["agreed_bonus"] + session.get("agreed_incentive", 0) * 0.55)
                    / max(1, session["agreed_years"])
                ),
            )
            connection.execute(
                """
                UPDATE players SET team=?, salary=?, status=0, lineup_pos=0,
                    role='FA 영입', contract_start_date=?,
                    contract_end_date=?, contract_years=?, contract_total=?,
                    contract_salary=?, contract_bonus=?, contract_option=?,
                    contract_note=? WHERE id=?
                """,
                (
                    self.team, session["agreed_salary"],
                    self.current_date.isoformat(),
                    f"{2025 + session['agreed_years']}-11-30", session["agreed_years"],
                    (
                        session["agreed_salary"] * session["agreed_years"]
                        + session["agreed_bonus"]
                        + session.get("agreed_incentive", 0)
                    ) * 10_000,
                    session["agreed_salary"] * 10_000, session["agreed_bonus"] * 10_000,
                    session.get("agreed_incentive", 0) * 10_000,
                    (
                        ("외부 FA 영입" if player["is_external"] else "원소속 FA 재계약")
                        + f" · {session.get('agreed_role', '')} · {session.get('agreed_usage', '')}"
                    ),
                    player["id"],
                ),
            )
            connection.commit()
        finally:
            connection.close()
        with sqlite3.connect(self.saves_db_path) as save:
            save.execute(
                """
                UPDATE player_simulation_states SET team=?, squad_group='2군', morale=80
                WHERE save_id=? AND player_id=?
                """,
                (self.team, self.save_id, player["id"]),
            )
            if player["is_external"]:
                save.execute(
                """
                CREATE TABLE IF NOT EXISTS club_finance_transactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    save_id INTEGER NOT NULL, team TEXT NOT NULL,
                    amount_10k INTEGER NOT NULL, category TEXT NOT NULL,
                    details TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
                )
                save.execute(
                """
                INSERT INTO club_finance_transactions (
                    save_id, team, amount_10k, category, details
                ) VALUES (?, ?, ?, 'FA 보상', ?)
                """,
                (
                    self.save_id, self.team, -int(player["compensation"]),
                    f"{player['name']} FA 영입 보상금 · {player['team']} 지급",
                ),
                )
            if player["player_compensation"]:
                save.execute(
                    """
                    CREATE TABLE IF NOT EXISTS fa_compensation_obligations (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        save_id INTEGER NOT NULL, acquiring_team TEXT NOT NULL,
                        former_team TEXT NOT NULL, player_id INTEGER NOT NULL,
                        player_name TEXT NOT NULL, fa_grade TEXT NOT NULL,
                        protection_limit INTEGER NOT NULL,
                        status TEXT NOT NULL DEFAULT 'pending',
                        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(save_id, player_id)
                    )
                    """
                )
                save.execute(
                    """
                    INSERT OR REPLACE INTO fa_compensation_obligations (
                        save_id, acquiring_team, former_team, player_id,
                        player_name, fa_grade, protection_limit, status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, 'pending')
                    """,
                    (
                        self.save_id, self.team, player["team"], player["id"],
                        player["name"], player["fa_grade"],
                        20 if player["fa_grade"] == "A" else 25,
                    ),
                )
        session["status"] = "signed"
        compensation_text = (
            f" 보상금 {player['compensation']:,}만원"
            + ("과 보상선수 1명이 필요합니다." if player["player_compensation"] else "이 반영됩니다.")
            if player["is_external"] else " 원소속 구단 재계약이므로 FA 보상은 없습니다."
        )
        return True, (
            f"{player['name']}과 {session['agreed_years']}년 계약을 체결했습니다. "
            + compensation_text
            + (f" 경쟁균형세 초과 예상액은 {cap['excess']:,}만원입니다." if cap["excess"] else "")
        )

    def finalize_contract(self, player_id):
        """통합 협상 화면에서 사용하는 공통 서명 인터페이스."""
        return self.finalize(player_id)
