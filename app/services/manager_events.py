"""날짜 진행에서 발생하는 감독 의사결정 이벤트 생성·해결 서비스."""

import hashlib
import json
import sqlite3
from datetime import date, timedelta

from app.player_ratings import overall_rating
from app.services.negotiation_rules import (
    player_meeting_rule_delta,
    player_meeting_rule_reply,
)


INITIAL_EVENT_SCHEDULE = {
    "2025-11-09": "fa",
    "2025-11-06": "player_meeting",
}

# KBO 선수계약 양도 가능 기간은 포스트시즌 종료 다음 날부터
# 다음 해 7월 31일까지다. 2025 한국시리즈는 10월 31일 종료됐다.
TRADE_WINDOWS = (
    (date(2025, 11, 1), date(2026, 7, 31)),
)
FIRST_TRADE_EVENT_DATE = date(2025, 11, 4)

FUTURE_PLAYER_OBLIGATION_SQL = """
    CREATE TABLE IF NOT EXISTS trade_future_player_obligations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        save_id INTEGER NOT NULL,
        managed_team TEXT NOT NULL,
        other_team TEXT NOT NULL,
        due_date TEXT NOT NULL,
        candidate_pool_json TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending',
        selection_event_created INTEGER NOT NULL DEFAULT 0,
        selected_player_id INTEGER,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
"""

NEGOTIATION_RULES = {
    "fa_opportunity": {
        "title": "FA 계약 협상",
        "counterpart_role": "선수 에이전트",
        "initial_score": 44,
        "target_score": 70,
        "max_rounds": 5,
        "opening": (
            "관심은 감사하지만 선수에게 맞는 역할과 대우가 분명해야 합니다. "
            "왜 이 구단을 선택해야 하는지 설명해 주시죠."
        ),
        "demand": "적정한 대우 · 명확한 보직 · 구단의 경쟁력",
    },
    "trade_offer": {
        "title": "구단 간 트레이드 협상",
        "counterpart_role": "우리 구단 단장",
        "initial_score": 48,
        "target_score": 72,
        "max_rounds": 99,
        "opening": (
            "상대 구단에서 트레이드 제안이 들어왔습니다. "
            "조건을 검토해 보시고 감독님의 생각을 말씀해 주십시오."
        ),
        "demand": "감독 의견 정리 · 상대 구단 전달 · 협상 결과 보고",
    },
    "player_complaint": {
        "title": "선수 개인 면담",
        "counterpart_role": "면담 요청 선수",
        "initial_score": 42,
        "target_score": 65,
        "max_rounds": 5,
        "opening": (
            "감독님과 제 역할에 대해 솔직하게 이야기하고 싶습니다. "
            "앞으로 제가 어떤 기회를 받을 수 있는지 알고 싶습니다."
        ),
        "demand": "기용 계획 · 공정한 경쟁 · 구체적인 성장 경로",
    },
}


def _stable_number(*parts, modulo):
    payload = ":".join(str(part) for part in parts).encode("utf-8")
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big") % modulo


def _choice(key, label, description):
    return {"key": key, "label": label, "description": description}


class ManagerEventService:
    """시즌 일정에 맞춘 감독 의사결정 이벤트를 관리한다."""

    def __init__(self, saves_db_path, player_db_path):
        self.saves_db_path = str(saves_db_path)
        self.player_db_path = str(player_db_path)

    @staticmethod
    def _format_trade_cash(amount_10k):
        amount = max(0, int(amount_10k or 0))
        if amount >= 10000:
            billions, remainder = divmod(amount, 10000)
            if remainder:
                return f"{billions}억 {remainder:,}만원"
            return f"{billions}억원"
        return f"{amount:,}만원"

    def _trade_player_rows(self, payload):
        """현재 제안 선수와 상대 구단의 실제 추가 보상 후보를 조회한다."""
        connection = sqlite3.connect(self.player_db_path)
        connection.row_factory = sqlite3.Row
        try:
            ids = (
                int(payload.get("incoming_id") or 0),
                int(payload.get("outgoing_id") or 0),
            )
            primary = {
                int(row["id"]): dict(row)
                for row in connection.execute(
                    "SELECT * FROM players WHERE id IN (?, ?)", ids
                ).fetchall()
            }
            counterpart_candidates = [
                dict(row)
                for row in connection.execute(
                    """
                    SELECT * FROM players
                    WHERE team = ? AND id != ? AND COALESCE(status, 0) = 0
                    """,
                    (
                        payload.get("other_team"),
                        int(payload.get("incoming_id") or 0),
                    ),
                ).fetchall()
            ]
            user_candidates = [
                dict(row)
                for row in connection.execute(
                    """
                    SELECT * FROM players
                    WHERE team = ? AND id != ? AND COALESCE(status, 0) = 0
                    """,
                    (
                        payload.get("managed_team"),
                        int(payload.get("outgoing_id") or 0),
                    ),
                ).fetchall()
            ]
            return primary, counterpart_candidates, user_candidates
        finally:
            connection.close()

    def _team_position_needs(self, team):
        minimums = {"P": 13, "C": 2, "IF": 6, "OF": 5}
        connection = sqlite3.connect(self.player_db_path)
        connection.row_factory = sqlite3.Row
        try:
            rows = connection.execute(
                """
                SELECT COALESCE(position_group, pos) AS position_group,
                       COUNT(*) AS player_count
                FROM players
                WHERE team=? AND COALESCE(status, 0)=1
                GROUP BY COALESCE(position_group, pos)
                """,
                (team,),
            ).fetchall()
        finally:
            connection.close()
        counts = {str(row["position_group"]): int(row["player_count"]) for row in rows}
        return {
            group for group, minimum in minimums.items()
            if counts.get(group, 0) < minimum
        }

    @staticmethod
    def _trade_asset_value(player, destination_needs=()):
        """능력·나이·계약·연봉·포지션 수요를 합친 100점 내부 가치."""
        if not player:
            return 0.0
        ability = float(overall_rating(player)) * 5.0
        age = int(player.get("age") or 29)
        if age <= 22:
            age_value = 12
        elif age <= 25:
            age_value = 9
        elif age <= 28:
            age_value = 5
        elif age <= 31:
            age_value = 1
        elif age <= 34:
            age_value = -4
        else:
            age_value = -9
        contract_years = max(0, int(player.get("contract_years") or 0))
        control_value = min(8, contract_years * 2)
        salary = max(0, int(player.get("salary") or player.get("contract_salary") or 0))
        expected_salary = max(3000, int(ability * 700))
        efficiency = max(-8, min(8, (expected_salary - salary) / 7000))
        group = str(player.get("position_group") or player.get("pos") or "")
        need_value = 7 if group in set(destination_needs) else 0
        return round(max(10, min(100, ability + age_value + control_value + efficiency + need_value)), 1)

    def _trade_response_terms(
        self, payload, manager_message, round_number, action=None,
    ):
        """감독의 의견을 실제 선수·금액 데이터에 맞는 상대 구단 답변으로 바꾼다."""
        message = str(manager_message or "")
        existing = dict(payload.get("trade_terms") or {})
        primary, candidates, user_candidates = self._trade_player_rows(payload)
        incoming = primary.get(int(payload.get("incoming_id") or 0), {})
        outgoing = primary.get(int(payload.get("outgoing_id") or 0), {})
        incoming_rating = overall_rating(incoming) if incoming else int(
            payload.get("incoming_rating") or 0
        )
        outgoing_rating = overall_rating(outgoing) if outgoing else int(
            payload.get("outgoing_rating") or 0
        )
        incoming_salary = int(incoming.get("salary") or 0)
        outgoing_salary = int(outgoing.get("salary") or 0)
        managed_needs = self._team_position_needs(payload.get("managed_team"))
        counterpart_needs = self._team_position_needs(payload.get("other_team"))
        incoming_value = self._trade_asset_value(incoming, managed_needs)
        outgoing_value = self._trade_asset_value(outgoing, counterpart_needs)
        value_gap = max(0, outgoing_value - incoming_value)
        salary_gap = max(0, outgoing_salary - incoming_salary)
        raw_cash = 8000 + value_gap * 3000 + round(salary_gap * 0.2)
        raw_cash += max(0, int(round_number) - 1) * 2000
        cash_offer = max(5000, min(50000, int(round(raw_cash / 1000) * 1000)))

        base = {
            "status": "original",
            "incoming_name": payload.get("incoming_name", "-"),
            "outgoing_name": payload.get("outgoing_name", "-"),
            "incoming_rating": incoming_rating,
            "outgoing_rating": outgoing_rating,
            "incoming_salary": incoming_salary,
            "outgoing_salary": outgoing_salary,
            "incoming_value": incoming_value,
            "outgoing_value": outgoing_value,
            "additional_incoming_id": None,
            "additional_incoming_name": "",
            "additional_incoming_rating": 0,
            "additional_incoming_salary": 0,
            "additional_outgoing_id": None,
            "additional_outgoing_name": "",
            "additional_outgoing_rating": 0,
            "additional_outgoing_salary": 0,
            "future_player_pool": [],
            "future_player_pool_outgoing": [],
            "future_player_due_days": 0,
            "cash_to_user_10k": 0,
            "cash_from_user_10k": 0,
            "cash_label": "없음",
            "cash_from_user_label": "없음",
            "compensation_type": "none",
            "compensation_direction": "none",
            "summary": "선수 1대1 교환",
            "round": int(round_number),
        }
        if existing:
            base.update(existing)
            base["round"] = int(round_number)

        def clear_counterpart_demands():
            base.update({
                "additional_outgoing_id": None,
                "additional_outgoing_name": "",
                "additional_outgoing_rating": 0,
                "additional_outgoing_salary": 0,
                "future_player_pool_outgoing": [],
                "cash_from_user_10k": 0,
                "cash_from_user_label": "없음",
            })

        def clear_user_demands():
            base.update({
                "additional_incoming_id": None,
                "additional_incoming_name": "",
                "additional_incoming_rating": 0,
                "additional_incoming_salary": 0,
                "future_player_pool": [],
                "future_player_due_days": 0,
                "cash_to_user_10k": 0,
                "cash_label": "없음",
            })

        action = str(action or "")
        accepts = action == "accept" or any(
            term in message
            for term in (
                "수락", "받아들이", "진행해", "진행하", "성사시", "합의하",
                "동의한다", "동의해", "이 조건으로", "최종 승인",
            )
        )
        rejects = action == "reject" or any(
            term in message
            for term in (
                "거절", "철회", "협상 중단", "받지 않", "진행하지 않",
                "합의하지 않", "조건이 불가능",
            )
        )
        # "진행하지 않겠습니다" 안의 "진행하"처럼 부정문이 수락으로
        # 오인되지 않도록 종료 의사를 항상 우선한다.
        accepts = accepts and not rejects
        requests_original = action == "original" or (
            "1대1" in message
            and any(term in message for term in ("원안", "추가 조건 없이", "현재 두 선수"))
        )
        requests_counter_cash_reduction = action == "reduce_cash" or any(
            term in message for term in ("현금 부담을 낮", "현금 금액이 과", "현금 감액")
        )
        requests_remove_counter_player = action == "remove_player" or any(
            term in message for term in ("추가 선수는 포함할 수 없", "추가 선수 없이")
        )
        requests_cash_conversion = action == "protect_prospect" or any(
            term in message for term in ("유망주는 보호", "현금 보상 방식으로 바꿔")
        )
        requests_revaluation = action == "revalue" or all(
            term in message for term in ("나이", "계약 기간", "연봉")
        ) or "가치 재검토" in message
        requests_player = action in {"request_player", "request_mixed"} or any(
            term in message
            for term in ("추가 선수", "다른 선수", "더 좋은 선수", "선수를 포함")
        )
        requests_mixed = action == "request_mixed" or any(
            term in message
            for term in (
                "선수+현금", "선수와 현금", "선수랑 현금",
                "복합 보상", "둘 다", "현금도 함께",
            )
        )
        requests_future = action == "request_future" or any(
            term in message
            for term in (
                "추후 지명", "추후지명", "나중에 지명",
                "추후 선수", "지명 선수",
            )
        )
        requests_player = requests_player or requests_mixed
        requests_compensation = (
            action in {"request_cash", "salary_cash"}
            or requests_player
            or any(
                term in message
                for term in (
                    "추가 보상", "보상 추가", "보상", "현금", "금액",
                    "금전", "얼마", "돈",
                    "지명권", "1라운드", "1라운더",
                )
            )
        )

        if accepts:
            base["status"] = "accepted"
            base["summary"] = existing.get("summary", "선수 1대1 교환")
            base["reply"] = (
                f"감독님의 수락 의사를 {payload.get('other_team', '상대 구단')}에 "
                f"전달했습니다. 상대 구단도 ‘{base['summary']}’ 조건을 최종 "
                "확인했고, 이 조건으로 트레이드를 진행하겠다고 답했습니다."
            )
            base["attitude_delta"] = 15
            return base
        if rejects:
            base["status"] = "rejected"
            base["reply"] = (
                f"거절 의사를 {payload.get('other_team', '상대 구단')}에 전달했습니다. "
                "상대 구단도 제안을 철회하며 이번 협상을 종료하겠다고 답했습니다."
            )
            base["attitude_delta"] = -5
            return base
        if requests_original:
            clear_counterpart_demands()
            clear_user_demands()
            base.update({
                "status": "reviewing",
                "compensation_type": "none",
                "compensation_direction": "none",
                "summary": "선수 1대1 교환",
                "attitude_delta": 3 if abs(incoming_value - outgoing_value) <= 6 else -1,
            })
            if abs(incoming_value - outgoing_value) <= 6:
                base["reply"] = (
                    f"{payload.get('other_team', '상대 구단')}이 추가 조건을 제외한 "
                    "1대1 원안으로 돌아가는 데 동의했습니다. 이 조건을 최종 "
                    "수락하면 트레이드를 진행할 수 있습니다."
                )
            else:
                base["reply"] = (
                    f"{payload.get('other_team', '상대 구단')}은 두 선수의 내부 자산가치 "
                    f"차이가 {abs(incoming_value - outgoing_value):.1f}점이라며 1대1 원안은 "
                    "받기 어렵다고 답했습니다. 현금 또는 선수 보상 조정이 필요합니다."
                )
            return base
        if requests_counter_cash_reduction:
            current_cash = int(base.get("cash_from_user_10k") or 0)
            if current_cash <= 0:
                base["status"] = "reviewing"
                base["attitude_delta"] = 0
                base["reply"] = (
                    "현재 상대 구단의 조건에는 우리 구단이 지급할 현금이 없습니다. "
                    "감액할 항목이 없으므로 다른 수정 방향을 선택해 주십시오."
                )
                return base
            reduced = max(
                3000,
                int(round(current_cash * 0.75 / 1000) * 1000),
            )
            label = self._format_trade_cash(reduced)
            base.update({
                "status": "counter_offer",
                "cash_from_user_10k": reduced,
                "cash_from_user_label": label,
                "summary": (
                    f"{payload.get('incoming_name')} 영입 / {payload.get('outgoing_name')} + "
                    f"현금 {label} 이적"
                ),
                "attitude_delta": 2,
            })
            base["reply"] = (
                f"현금 감액 요청을 전달했습니다. {payload.get('other_team', '상대 구단')}은 "
                f"기존 요구액에서 25% 낮춘 {label}을 최종 조정안으로 제시했습니다."
            )
            return base
        if requests_remove_counter_player:
            has_counter_player = bool(
                base.get("additional_outgoing_id")
                or base.get("future_player_pool_outgoing")
            )
            if not has_counter_player:
                base["status"] = "reviewing"
                base["attitude_delta"] = 0
                base["reply"] = (
                    "현재 상대 구단의 조건에는 추가 선수 요구가 없습니다. "
                    "원안 유지, 현금 조정 또는 다른 보상 유형을 선택할 수 있습니다."
                )
                return base
            clear_counterpart_demands()
            replacement_cash = max(3000, int(round(raw_cash * 0.6 / 1000) * 1000))
            label = self._format_trade_cash(replacement_cash)
            base.update({
                "status": "counter_offer",
                "cash_from_user_10k": replacement_cash,
                "cash_from_user_label": label,
                "compensation_type": "cash",
                "compensation_direction": "counterpart",
                "summary": (
                    f"{payload.get('incoming_name')} 영입 / {payload.get('outgoing_name')} + "
                    f"현금 {label} 이적"
                ),
                "attitude_delta": 1,
            })
            base["reply"] = (
                f"추가 선수 제외 요청을 받아들여 {payload.get('other_team', '상대 구단')}이 "
                f"선수 대신 현금 {label}을 요구하는 수정안을 보냈습니다."
            )
            return base
        if requests_cash_conversion:
            if base.get("compensation_direction") != "counterpart" or not (
                base.get("additional_outgoing_id")
                or base.get("future_player_pool_outgoing")
            ):
                base["status"] = "reviewing"
                base["attitude_delta"] = 0
                base["reply"] = (
                    "현재 상대 구단이 우리 유망주를 요구한 상태가 아닙니다. "
                    "선수 보상 요구가 들어오면 현금 전환안을 다시 제시할 수 있습니다."
                )
                return base
            clear_counterpart_demands()
            replacement_cash = max(3000, int(round(raw_cash * 0.7 / 1000) * 1000))
            label = self._format_trade_cash(replacement_cash)
            base.update({
                "status": "counter_offer",
                "cash_from_user_10k": replacement_cash,
                "cash_from_user_label": label,
                "compensation_type": "cash",
                "compensation_direction": "counterpart",
                "summary": (
                    f"{payload.get('incoming_name')} 영입 / {payload.get('outgoing_name')} + "
                    f"현금 {label} 이적"
                ),
                "attitude_delta": 2,
            })
            base["reply"] = (
                f"유망주 보호 방침을 전달했습니다. 상대 구단은 선수 요구를 철회하고 "
                f"현금 {label}으로 전환한 조건을 제시했습니다."
            )
            return base
        if action == "salary_cash":
            salary_burden = max(0, incoming_salary - outgoing_salary)
            if salary_burden <= 0:
                base["status"] = "reviewing"
                base["attitude_delta"] = 0
                base["reply"] = (
                    "영입 대상의 연봉이 이적 대상보다 높지 않아 별도의 연봉 부담 "
                    "보상을 요구할 근거가 약합니다. 다른 보상 유형을 선택해 주십시오."
                )
                return base
            clear_counterpart_demands()
            salary_cash = max(
                3000,
                min(
                    50000,
                    int(round(salary_burden * 0.3 / 1000) * 1000),
                ),
            )
            label = self._format_trade_cash(salary_cash)
            base.update({
                "status": "counter_offer",
                "cash_to_user_10k": salary_cash,
                "cash_label": label,
                "compensation_type": "cash",
                "compensation_direction": "user",
                "summary": (
                    f"{payload.get('incoming_name')} + 현금 {label} 영입 / "
                    f"{payload.get('outgoing_name')} 이적"
                ),
                "attitude_delta": 3 if outgoing_value >= incoming_value else 1,
            })
            base["reply"] = (
                f"연봉 차이 {salary_burden:,}만원을 근거로 보상을 요청했습니다. "
                f"{payload.get('other_team', '상대 구단')}은 현금 {label}을 "
                "부담하는 수정안을 보내왔습니다."
            )
            return base
        if requests_revaluation:
            base["status"] = "reviewing"
            base["attitude_delta"] = 1
            base["reply"] = (
                f"양 구단이 자산가치를 다시 계산했습니다. 우리 영입 대상은 "
                f"{incoming_value:.1f}점, 이적 대상은 {outgoing_value:.1f}점입니다. "
                f"나이·잔여 계약·연봉 효율·포지션 수요를 반영한 결과이며 현재 "
                f"조건은 ‘{base.get('summary', '선수 1대1 교환')}’입니다."
            )
            return base
        requests_compensation = (
            requests_compensation or requests_mixed or requests_future
        )

        def counterpart_demand():
            """상대 구단이 우리 구단에 요구할 실제 역제안 조건을 만든다."""
            clear_user_demands()
            opponent_gap = max(0, incoming_value - outgoing_value)
            opponent_salary_gap = max(0, incoming_salary - outgoing_salary)
            requested_cash = 8000 + opponent_gap * 3000
            requested_cash += round(opponent_salary_gap * 0.2)
            requested_cash += max(0, int(round_number) - 1) * 2000
            requested_cash = max(
                5000,
                min(
                    50000,
                    int(round(requested_cash / 1000) * 1000),
                ),
            )
            target_value = max(35, min(90, opponent_gap + 45))
            ranked_user_candidates = sorted(
                user_candidates,
                key=lambda player: (
                    abs(self._trade_asset_value(player, counterpart_needs) - target_value),
                    _stable_number(
                        payload.get("outgoing_id"),
                        round_number,
                        player["id"],
                        modulo=1000,
                    ),
                ),
            )
            if opponent_gap >= 12 and ranked_user_candidates:
                demand_type = 2 if opponent_salary_gap >= 5000 else 1
            elif opponent_gap >= 6 and ranked_user_candidates:
                demand_type = 1
            elif opponent_salary_gap >= 5000:
                demand_type = 0
            elif int(round_number) >= 3 and ranked_user_candidates:
                demand_type = 3
            else:
                demand_type = _stable_number(
                    payload.get("incoming_id"),
                    payload.get("outgoing_id"),
                    round_number,
                    "counterpart_demand",
                    modulo=4,
                )
            if not ranked_user_candidates and demand_type in {1, 2, 3}:
                demand_type = 0
            other_team = payload.get("other_team", "상대 구단")
            managed_team = payload.get("managed_team", "우리 구단")
            if demand_type == 0:
                cash_label = self._format_trade_cash(requested_cash)
                base.update({
                    "status": "counter_offer",
                    "additional_outgoing_id": None,
                    "additional_outgoing_name": "",
                    "additional_outgoing_rating": 0,
                    "additional_outgoing_salary": 0,
                    "future_player_pool_outgoing": [],
                    "cash_from_user_10k": requested_cash,
                    "cash_from_user_label": cash_label,
                    "compensation_type": "cash",
                    "compensation_direction": "counterpart",
                    "summary": (
                        f"{payload.get('incoming_name')} 영입 / "
                        f"{payload.get('outgoing_name')} + 현금 {cash_label} 이적"
                    ),
                    "attitude_delta": -2,
                })
                base["reply"] = (
                    f"{other_team}은 원안만으로는 합의하기 어렵다며 "
                    f"{managed_team}이 현금 {cash_label}을 추가해 달라는 "
                    "역제안을 보내왔습니다."
                )
                return base
            if demand_type == 1:
                candidate = ranked_user_candidates[0]
                base.update({
                    "status": "counter_offer",
                    "additional_outgoing_id": int(candidate["id"]),
                    "additional_outgoing_name": candidate["name"],
                    "additional_outgoing_rating": overall_rating(candidate),
                    "additional_outgoing_salary": int(candidate.get("salary") or 0),
                    "future_player_pool_outgoing": [],
                    "cash_from_user_10k": 0,
                    "cash_from_user_label": "없음",
                    "compensation_type": "player",
                    "compensation_direction": "counterpart",
                    "summary": (
                        f"{payload.get('incoming_name')} 영입 / "
                        f"{payload.get('outgoing_name')} + {candidate['name']} 이적"
                    ),
                    "attitude_delta": -3,
                })
                base["reply"] = (
                    f"{other_team}은 추가 선수로 {candidate['name']}을 포함해야 "
                    "합의할 수 있다는 1대2 역제안을 보내왔습니다."
                )
                return base
            if demand_type == 2:
                candidate = ranked_user_candidates[0]
                mixed_cash = max(
                    3000,
                    int(round(requested_cash * 0.5 / 1000) * 1000),
                )
                cash_label = self._format_trade_cash(mixed_cash)
                base.update({
                    "status": "counter_offer",
                    "additional_outgoing_id": int(candidate["id"]),
                    "additional_outgoing_name": candidate["name"],
                    "additional_outgoing_rating": overall_rating(candidate),
                    "additional_outgoing_salary": int(candidate.get("salary") or 0),
                    "future_player_pool_outgoing": [],
                    "cash_from_user_10k": mixed_cash,
                    "cash_from_user_label": cash_label,
                    "compensation_type": "player_cash",
                    "compensation_direction": "counterpart",
                    "summary": (
                        f"{payload.get('incoming_name')} 영입 / "
                        f"{payload.get('outgoing_name')} + {candidate['name']} + "
                        f"현금 {cash_label} 이적"
                    ),
                    "attitude_delta": -4,
                })
                base["reply"] = (
                    f"{other_team}은 {candidate['name']}과 현금 {cash_label}을 "
                    f"{managed_team}이 함께 추가하는 복합 보상을 요구했습니다."
                )
                return base
            pool = [
                {
                    "id": int(player["id"]),
                    "name": player["name"],
                    "rating": overall_rating(player),
                    "salary": int(player.get("salary") or 0),
                }
                for player in ranked_user_candidates[:3]
            ]
            names = ", ".join(player["name"] for player in pool)
            base.update({
                "status": "counter_offer",
                "additional_outgoing_id": None,
                "additional_outgoing_name": "",
                "additional_outgoing_rating": 0,
                "additional_outgoing_salary": 0,
                "future_player_pool_outgoing": pool,
                "future_player_due_days": 30,
                "cash_from_user_10k": 0,
                "cash_from_user_label": "없음",
                "compensation_type": "future_player",
                "compensation_direction": "counterpart",
                "summary": (
                    f"{payload.get('incoming_name')} 영입 / "
                    f"{payload.get('outgoing_name')} + 30일 이내 "
                    "추후 지명 선수 1명 이적"
                ),
                "attitude_delta": -3,
            })
            base["reply"] = (
                f"{other_team}은 {managed_team} 후보군 {names} 중 한 명을 "
                "30일 이내 직접 확정할 수 있는 추후 지명 조건을 요구했습니다."
            )
            return base

        if requests_compensation and value_gap <= 0 and salary_gap < 2000:
            return counterpart_demand()
        ranked_candidates = sorted(
            candidates,
            key=lambda player: (
                abs(
                    self._trade_asset_value(player, managed_needs)
                    - max(35, min(90, value_gap + 45))
                ),
                _stable_number(
                    payload.get("incoming_id"),
                    round_number,
                    player["id"],
                    modulo=1000,
                ),
            ),
        )
        if requests_future and ranked_candidates:
            clear_counterpart_demands()
            pool = [
                {
                    "id": int(player["id"]),
                    "name": player["name"],
                    "rating": overall_rating(player),
                    "salary": int(player.get("salary") or 0),
                }
                for player in ranked_candidates[:3]
            ]
            names = ", ".join(player["name"] for player in pool)
            base.update({
                "status": "counter_offer",
                "additional_incoming_id": None,
                "additional_incoming_name": "",
                "additional_incoming_rating": 0,
                "additional_incoming_salary": 0,
                "future_player_pool": pool,
                "future_player_due_days": 30,
                "cash_to_user_10k": 0,
                "cash_label": "없음",
                "compensation_type": "future_player",
                "compensation_direction": "user",
                "summary": (
                    f"{payload.get('incoming_name')} 영입 + 30일 이내 "
                    f"추후 지명 선수 1명 / {payload.get('outgoing_name')} 이적"
                ),
                "attitude_delta": 5,
            })
            base["reply"] = (
                f"추후 지명 선수 요구를 {payload.get('other_team', '상대 구단')}에 "
                f"전달했습니다. 상대 구단은 후보군 {names} 중 한 명을 "
                "30일 이내에 직접 확정하는 조건을 제시했습니다."
            )
            return base
        if requests_mixed and ranked_candidates and value_gap >= 3:
            clear_counterpart_demands()
            candidate = ranked_candidates[0]
            mixed_cash = max(
                3000, int(round(cash_offer * 0.5 / 1000) * 1000)
            )
            cash_label = self._format_trade_cash(mixed_cash)
            base.update({
                "status": "counter_offer",
                "additional_incoming_id": int(candidate["id"]),
                "additional_incoming_name": candidate["name"],
                "additional_incoming_rating": overall_rating(candidate),
                "additional_incoming_salary": int(candidate.get("salary") or 0),
                "future_player_pool": [],
                "future_player_due_days": 0,
                "cash_to_user_10k": mixed_cash,
                "cash_label": cash_label,
                "compensation_type": "player_cash",
                "compensation_direction": "user",
                "summary": (
                    f"{payload.get('incoming_name')} + {candidate['name']} + "
                    f"현금 {cash_label} 영입 / {payload.get('outgoing_name')} 이적"
                ),
                "attitude_delta": 6,
            })
            base["reply"] = (
                f"복합 보상 요구를 {payload.get('other_team', '상대 구단')}에 "
                f"전달했습니다. 상대 구단은 {candidate['name']}과 현금 "
                f"{cash_label}을 함께 추가하는 조건으로 역제안했습니다."
            )
            return base
        if requests_player and candidates and value_gap >= 4:
            clear_counterpart_demands()
            target_value = max(35, min(90, value_gap + 45))
            candidate = min(
                candidates,
                key=lambda player: (
                    abs(
                        self._trade_asset_value(player, managed_needs)
                        - target_value
                    ),
                    _stable_number(
                        payload.get("incoming_id"),
                        round_number,
                        player["id"],
                        modulo=1000,
                    ),
                ),
            )
            base.update({
                "status": "counter_offer",
                "additional_incoming_id": int(candidate["id"]),
                "additional_incoming_name": candidate["name"],
                "additional_incoming_rating": overall_rating(candidate),
                "additional_incoming_salary": int(candidate.get("salary") or 0),
                "future_player_pool": [],
                "future_player_due_days": 0,
                "cash_to_user_10k": 0,
                "cash_label": "없음",
                "compensation_type": "player",
                "compensation_direction": "user",
                "summary": (
                    f"{payload.get('incoming_name')} + {candidate['name']} 영입 / "
                    f"{payload.get('outgoing_name')} 이적"
                ),
                "attitude_delta": 5,
            })
            base["reply"] = (
                f"추가 선수 보상 요구를 {payload.get('other_team', '상대 구단')}에 "
                f"전달했습니다. 상대 구단은 {candidate['name']}을 추가하는 "
                f"2대1 조건을 역제안했습니다. 현금 보상은 포함하지 않겠다는 "
                "입장입니다."
            )
            return base
        if requests_compensation:
            clear_counterpart_demands()
            cash_label = self._format_trade_cash(cash_offer)
            base.update({
                "status": "counter_offer",
                "additional_incoming_id": None,
                "additional_incoming_name": "",
                "additional_incoming_rating": 0,
                "additional_incoming_salary": 0,
                "future_player_pool": [],
                "future_player_due_days": 0,
                "cash_to_user_10k": cash_offer,
                "cash_label": cash_label,
                "compensation_type": "cash",
                "compensation_direction": "user",
                "summary": (
                    f"{payload.get('incoming_name')} + 현금 {cash_label} 영입 / "
                    f"{payload.get('outgoing_name')} 이적"
                ),
                "attitude_delta": 5,
            })
            requested_pick = any(
                term in message for term in ("지명권", "1라운드", "1라운더")
            )
            prefix = (
                "지명권 양도는 어렵지만 그 대신 "
                if requested_pick else ""
            )
            base["reply"] = (
                f"추가 보상 요구를 {payload.get('other_team', '상대 구단')}에 "
                f"전달했습니다. 상대 구단은 {prefix}현금 {cash_label}을 "
                f"추가하는 조건으로 수정 제안을 보내왔습니다."
            )
            return base

        if base.get("compensation_direction") == "counterpart":
            base["status"] = "counter_offer"
            base["attitude_delta"] = -1
            base["reply"] = (
                f"{payload.get('other_team', '상대 구단')}은 감독님의 설명을 "
                f"검토했지만 현재 역제안인 ‘{base.get('summary')}’ 조건을 "
                "유지하겠다고 답했습니다. 조건을 수락하거나 구체적인 수정안을 "
                "제시해 달라는 입장입니다."
            )
            return base
        spontaneous_counter = (
            int(round_number) >= 2
            and _stable_number(
                payload.get("incoming_id"),
                payload.get("outgoing_id"),
                round_number,
                "spontaneous_counter",
                modulo=100,
            ) < 35
        )
        if incoming_value > outgoing_value or spontaneous_counter:
            return counterpart_demand()
        base["status"] = "reviewing"
        base["reply"] = (
            f"말씀하신 평가를 {payload.get('other_team', '상대 구단')}에 "
            "전달했습니다. 상대 구단은 현재 선수 교환 원안을 유지하되, "
            "원하는 보상 유형을 구체적으로 알려주면 다시 검토하겠다고 답했습니다."
        )
        base["attitude_delta"] = 2
        return base

    @staticmethod
    def _new_negotiation(event_type, payload=None):
        rule = NEGOTIATION_RULES[event_type]
        opening = rule["opening"]
        if event_type == "trade_offer" and payload:
            opening = (
                f"{payload.get('other_team', '상대 구단')}에서 "
                f"{payload.get('incoming_name', '선수')}을 보내는 대신 "
                f"{payload.get('outgoing_name', '우리 선수')}을 원한다는 "
                "제안이 들어왔습니다. 감독님은 어떻게 생각하십니까?"
            )
        return {
            "score": rule["initial_score"],
            "target_score": rule["target_score"],
            "round": 0,
            "max_rounds": rule["max_rounds"],
            "status": "active",
            "transcript": [
                {
                    "speaker": "counterpart",
                    "text": opening,
                }
            ],
        }

    @staticmethod
    def _normalize_negotiation(event_type, state, payload=None):
        """구버전 AI의 메타 발언과 협상 주체 역전을 기존 기록에서도 정리한다."""
        transcript = list(state.get("transcript", []))
        previous_manager_text = ""
        meta_phrases = (
            "현재 설득도",
            "이전 대화",
            "적절한 방향으로",
            "평가 기준",
            "프롬프트",
        )
        asset_terms = (
            "1라운드", "1라운더", "지명권", "더 좋은 선수", "추가 선수",
        )
        for turn in transcript:
            text = str(turn.get("text") or "")
            if turn.get("speaker") == "manager":
                previous_manager_text = text
                continue
            sentences = [
                sentence.strip()
                for sentence in text.replace("!", ".").split(".")
                if sentence.strip()
                and not any(phrase in sentence for phrase in meta_phrases)
            ]
            cleaned = ". ".join(sentences)
            if cleaned and not cleaned.endswith((".", "?", "!")):
                cleaned += "."
            reversed_assets = (
                event_type == "trade_offer"
                and any(term in previous_manager_text for term in asset_terms)
                and any(term in cleaned for term in asset_terms)
                and any(
                    phrase in cleaned
                    for phrase in ("주시면", "주십시오", "달라", "보내주", "내놓")
                )
            )
            if reversed_assets:
                if any(
                    term in previous_manager_text
                    for term in ("1라운드", "1라운더", "지명권")
                ):
                    cleaned = (
                        "1라운드 지명권까지 추가하는 역제안은 부담이 너무 "
                        "큽니다. 현재 두 선수의 교환 범위에서 "
                        "가치 차이를 다시 설명해 주십시오."
                    )
                else:
                    cleaned = (
                        "더 좋은 선수를 추가로 보내라는 요구는 현재 "
                        "제안의 균형과 맞지 않습니다. 지금 거론된 두 선수의 "
                        "가치 안에서 조건을 다시 설명해 주십시오."
                    )
                turn["delta"] = min(int(turn.get("delta", 0)), -3)
            turn["text"] = cleaned or "그 제안은 조금 더 검토해 보겠습니다."
        if (
            event_type == "player_complaint"
            and payload is not None
            and payload.get("player_scoring_mode") != "dialogue_v4"
        ):
            corrected_score = NEGOTIATION_RULES[event_type]["initial_score"]
            previous_manager_text = ""
            meeting_round = 0
            for turn in transcript:
                if turn.get("speaker") == "manager":
                    previous_manager_text = str(turn.get("text") or "")
                    meeting_round += 1
                    continue
                if not previous_manager_text:
                    continue
                corrected_delta = player_meeting_rule_delta(
                    previous_manager_text
                )
                turn["delta"] = corrected_delta
                turn["text"] = player_meeting_rule_reply(
                    previous_manager_text,
                    {
                        "round": meeting_round,
                        "player_context": {
                            "player_name": payload.get("player_name"),
                            "team": payload.get("managed_team"),
                            "squad": payload.get("squad"),
                            "position": payload.get("position"),
                            "age": payload.get("age"),
                            "morale": payload.get("morale"),
                        },
                    },
                )
                corrected_score += corrected_delta
                previous_manager_text = ""
            target = int(state.get("target_score", 65))
            state["score"] = max(0, min(target - 1, corrected_score))
            payload["player_scoring_mode"] = "dialogue_v4"
        if (
            event_type == "trade_offer"
            and payload is not None
            and payload.get("trade_dialogue_mode") != "gm_mediated_v1"
        ):
            other_team = payload.get("other_team", "상대 구단")
            counterpart_turns = [
                turn for turn in transcript
                if turn.get("speaker") == "counterpart"
            ]
            for index, turn in enumerate(counterpart_turns):
                if index == 0:
                    turn["text"] = (
                        f"{other_team}에서 "
                        f"{payload.get('incoming_name', '선수')}을 보내는 대신 "
                        f"{payload.get('outgoing_name', '우리 선수')}을 원한다는 "
                        "제안이 들어왔습니다. 감독님은 어떻게 생각하십니까?"
                    )
                else:
                    turn["text"] = (
                        f"말씀하신 내용을 {other_team} 측에 전달했습니다. "
                        f"상대 구단은 다음과 같이 답했습니다.\n“{turn['text']}”"
                    )
            payload["trade_dialogue_mode"] = "gm_mediated_v1"
        if event_type == "trade_offer":
            state["max_rounds"] = 99
        state["transcript"] = transcript
        return state

    def negotiation_state(self, save_id, event_id):
        """이벤트와 저장된 협상 진행 상태를 함께 반환한다."""
        connection = sqlite3.connect(self.saves_db_path)
        connection.row_factory = sqlite3.Row
        try:
            row = connection.execute(
                """
                SELECT * FROM manager_events
                WHERE save_id = ? AND id = ?
                """,
                (save_id, event_id),
            ).fetchone()
            if row is None:
                raise ValueError("협상 이벤트를 찾을 수 없습니다.")
            event_type = row["event_type"]
            if event_type not in NEGOTIATION_RULES:
                raise ValueError("대화형 협상을 지원하지 않는 이벤트입니다.")
            payload = json.loads(row["payload_json"])
            if event_type == "trade_offer":
                payload.setdefault("offer_date", row["event_date"])
                primary, _candidates, _user_candidates = (
                    self._trade_player_rows(payload)
                )
                incoming = primary.get(
                    int(payload.get("incoming_id") or 0), {}
                )
                outgoing = primary.get(
                    int(payload.get("outgoing_id") or 0), {}
                )
                if incoming:
                    payload["incoming_rating"] = overall_rating(incoming)
                    payload["incoming_salary"] = int(
                        incoming.get("salary") or 0
                    )
                if outgoing:
                    payload["outgoing_rating"] = overall_rating(outgoing)
                    payload["outgoing_salary"] = int(
                        outgoing.get("salary") or 0
                    )
                payload.setdefault("trade_terms", {
                    "status": "original",
                    "incoming_name": payload.get("incoming_name", "-"),
                    "outgoing_name": payload.get("outgoing_name", "-"),
                    "incoming_rating": payload.get("incoming_rating", 0),
                    "outgoing_rating": payload.get("outgoing_rating", 0),
                    "incoming_salary": payload.get("incoming_salary", 0),
                    "outgoing_salary": payload.get("outgoing_salary", 0),
                    "additional_incoming_id": None,
                    "additional_incoming_name": "",
                    "additional_incoming_rating": 0,
                    "additional_incoming_salary": 0,
                    "additional_outgoing_id": None,
                    "additional_outgoing_name": "",
                    "additional_outgoing_rating": 0,
                    "additional_outgoing_salary": 0,
                    "future_player_pool": [],
                    "future_player_pool_outgoing": [],
                    "future_player_due_days": 0,
                    "cash_to_user_10k": 0,
                    "cash_from_user_10k": 0,
                    "cash_label": "없음",
                    "cash_from_user_label": "없음",
                    "compensation_type": "none",
                    "compensation_direction": "none",
                    "summary": "선수 1대1 교환",
                    "round": 0,
                })
            state = payload.get("negotiation")
            if not isinstance(state, dict):
                state = self._new_negotiation(event_type, payload)
            state = self._normalize_negotiation(event_type, state, payload)
            return {
                "event_type": event_type,
                "headline": row["headline"],
                "body": row["body"],
                "event_date": row["event_date"],
                "payload": payload,
                "rule": dict(NEGOTIATION_RULES[event_type]),
                "negotiation": state,
                "resolved": row["status"] == "resolved",
                "result_text": row["result_text"],
            }
        finally:
            connection.close()

    def negotiation_context(self, save_id, event_id, manager_message):
        data = self.negotiation_state(save_id, event_id)
        state = data["negotiation"]
        payload = data["payload"]
        deal_terms = {}
        if data["event_type"] == "trade_offer":
            authorized_response = self._trade_response_terms(
                payload,
                manager_message,
                int(state.get("round", 0)) + 1,
            )
            deal_terms = {
                "user_club": payload.get("managed_team"),
                "counterpart_club": payload.get("other_team"),
                "counterpart_gives": payload.get("incoming_name"),
                "user_club_gives": payload.get("outgoing_name"),
                "current_terms": dict(payload.get("trade_terms") or {}),
                "authorized_response": authorized_response,
                "instruction": (
                    "authorized_response은 게임 엔진이 실제 선수 DB와 가치 차이로 "
                    "확정한 상대 구단 답변이다. 선수명과 현금 금액을 바꾸거나 "
                    "새 자산을 추가하지 말고 그대로 감독에게 보고한다."
                ),
            }
        player_context = {}
        if data["event_type"] == "player_complaint":
            player_context = {
                "player_name": payload.get("player_name"),
                "team": payload.get("managed_team"),
                "squad": payload.get("squad"),
                "position": payload.get("position"),
                "age": payload.get("age"),
                "morale": payload.get("morale"),
                "complaint": data["body"],
            }
        return {
            "request_type": "manager_negotiation_turn",
            "event_type": data["event_type"],
            "headline": data["headline"],
            "situation": data["body"],
            "counterpart_role": data["rule"]["counterpart_role"],
            "core_demand": data["rule"]["demand"],
            "current_score": int(state["score"]),
            "target_score": int(state["target_score"]),
            "round": int(state["round"]) + 1,
            "max_rounds": int(state["max_rounds"]),
            "recent_transcript": list(state.get("transcript", []))[-6:],
            "role_contract": (
                "manager_message는 사용자 구단 감독의 발언이다. "
                "trade_offer에서는 당신이 사용자 구단의 단장으로서 의견을 "
                "정리해 상대 구단에 전달하고 그 답변을 감독에게 보고한다."
            ),
            "deal_terms": deal_terms,
            "player_context": player_context,
            "manager_message": manager_message,
        }

    def rule_based_negotiation_response(
        self, save_id, event_id, manager_message, manager_choice=None,
    ):
        """로컬 모델 없이 선수 면담·트레이드의 즉시 응답을 계산한다."""
        data = self.negotiation_state(save_id, event_id)
        event_type = data["event_type"]
        state = data["negotiation"]
        payload = data["payload"]
        round_number = int(state.get("round", 0)) + 1

        if event_type == "trade_offer":
            action = str((manager_choice or {}).get("action") or "")
            terms = self._trade_response_terms(
                payload, manager_message, round_number, action
            )
            return {
                "reply": terms["reply"],
                "attitude_delta": int(terms.get("attitude_delta", 0)),
                "trade_terms": terms,
                "engine": "trade_rules_v2",
                "factors": {
                    "incoming_rating": terms.get("incoming_rating", 0),
                    "outgoing_rating": terms.get("outgoing_rating", 0),
                    "incoming_salary": terms.get("incoming_salary", 0),
                    "outgoing_salary": terms.get("outgoing_salary", 0),
                    "incoming_value": terms.get("incoming_value", 0),
                    "outgoing_value": terms.get("outgoing_value", 0),
                    "compensation_type": terms.get("compensation_type", "none"),
                },
            }

        if event_type != "player_complaint":
            raise ValueError("이 이벤트에는 규칙 기반 대화 엔진을 사용할 수 없습니다.")

        message = str(manager_message or "")
        delta = player_meeting_rule_delta(message)
        choice_number = int((manager_choice or {}).get("number") or 0)
        choice_adjustments = {
            1: 2, 2: 3, 3: 1, 4: -3,
            5: 2, 6: 3, 7: 2, 8: 1,
        }
        delta += choice_adjustments.get(choice_number, 0)

        morale = int(payload.get("morale") or 70)
        squad = str(payload.get("squad") or "")
        age = int(payload.get("age") or 28)
        current_score = int(state.get("score", 42))
        target_score = int(state.get("target_score", 65))
        transcript = list(state.get("transcript", []))
        previous_manager_messages = [
            str(turn.get("text") or "")
            for turn in transcript if turn.get("speaker") == "manager"
        ]

        # 같은 말의 반복, 지키기 어려운 출전 보장, 선수 상황별 민감도를 반영한다.
        if message in previous_manager_messages:
            delta -= 5
        if round_number >= 4:
            delta -= round_number - 3
        is_empathy = any(term in message for term in ("듣", "이해", "입장", "인정"))
        is_concrete = any(term in message for term in ("기준", "시점", "항목", "수비", "체력", "기록"))
        is_promise = any(term in message for term in ("약속", "기회", "출전", "1군"))
        is_harsh = any(term in message for term in ("권한", "특별 대우", "다른 선택", "의미가 없다"))
        if morale < 60 and is_empathy:
            delta += 2
        if morale < 60 and is_harsh:
            delta -= 3
        if squad == "2군" and is_concrete:
            delta += 2
        if age <= 26 and any(term in message for term in ("성장", "목표", "보완")):
            delta += 2
        if is_promise and not is_concrete:
            delta -= 2
        if current_score >= target_score - 8 and is_harsh:
            delta -= 2
        delta = max(-12, min(15, delta))

        context = {
            "round": round_number,
            "player_context": {
                "player_name": payload.get("player_name"),
                "team": payload.get("managed_team"),
                "squad": squad,
                "position": payload.get("position"),
                "age": age,
                "morale": morale,
            },
        }
        reply = player_meeting_rule_reply(message, context)
        projected_score = max(0, min(100, current_score + delta))
        if projected_score >= target_score:
            reply = (
                f"{reply} 감독님이 말씀하신 기준과 시점을 믿고 준비하겠습니다. "
                "오늘 면담에서 제 역할에 대한 답을 들었습니다."
            )
        elif delta <= -5:
            reply = (
                f"{reply} 지금 답변으로는 상황이 나아질 것이라는 확신을 갖기 어렵습니다."
            )
        return {
            "reply": reply,
            "attitude_delta": delta,
            "engine": "player_meeting_rules_v2",
            "factors": {
                "choice": choice_number,
                "morale": morale,
                "squad": squad,
                "age": age,
                "empathy": is_empathy,
                "concrete": is_concrete,
                "promise": is_promise,
                "harsh": is_harsh,
                "repeated": message in previous_manager_messages,
            },
        }

    def record_negotiation_turn(
        self, save_id, event_id, manager_message, ai_response,
    ):
        """한 라운드를 저장하고 설득 성공·실패 여부를 판정한다."""
        connection = sqlite3.connect(self.saves_db_path)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT event_type, event_date, payload_json, status
                FROM manager_events WHERE save_id = ? AND id = ?
                """,
                (save_id, event_id),
            ).fetchone()
            if row is None:
                raise ValueError("협상 이벤트를 찾을 수 없습니다.")
            if row["status"] != "open":
                raise ValueError("이미 종료된 협상입니다.")
            event_type = row["event_type"]
            payload = json.loads(row["payload_json"])
            if event_type == "trade_offer":
                payload.setdefault("offer_date", row["event_date"])
            state = payload.get("negotiation")
            if not isinstance(state, dict):
                state = self._new_negotiation(event_type, payload)
            state = self._normalize_negotiation(event_type, state, payload)
            if state.get("status") != "active":
                return state

            trade_terms = None
            if event_type == "trade_offer":
                trade_terms = self._trade_response_terms(
                    payload,
                    manager_message,
                    int(state.get("round", 0)) + 1,
                )
                payload["trade_terms"] = trade_terms
                ai_response = {
                    **dict(ai_response),
                    "reply": trade_terms["reply"],
                    "attitude_delta": trade_terms["attitude_delta"],
                    "trade_terms": trade_terms,
                }
            delta = max(
                -12, min(15, int(ai_response.get("attitude_delta", 0)))
            )
            state["round"] = int(state.get("round", 0)) + 1
            state["score"] = max(
                0, min(100, int(state.get("score", 0)) + delta)
            )
            transcript = list(state.get("transcript", []))
            transcript.extend(
                (
                    {"speaker": "manager", "text": manager_message},
                    {
                        "speaker": "counterpart",
                        "text": str(ai_response.get("reply") or ""),
                        "delta": delta,
                        **({"terms": trade_terms} if trade_terms else {}),
                    },
                )
            )
            state["transcript"] = (
                transcript[-40:]
                if event_type == "trade_offer"
                else transcript[-14:]
            )
            if trade_terms and trade_terms.get("status") == "accepted":
                state["score"] = max(
                    int(state["score"]), int(state["target_score"])
                )
                state["status"] = "accepted"
            elif trade_terms and trade_terms.get("status") == "rejected":
                state["status"] = "rejected"
            elif (
                event_type != "trade_offer"
                and state["score"] >= int(state["target_score"])
            ):
                state["status"] = "accepted"
            elif (
                event_type != "trade_offer"
                and state["round"] >= int(state["max_rounds"])
            ):
                state["status"] = "rejected"
            payload["negotiation"] = state
            connection.execute(
                """
                UPDATE manager_events SET payload_json = ?
                WHERE save_id = ? AND id = ?
                """,
                (json.dumps(payload, ensure_ascii=False), save_id, event_id),
            )
            connection.commit()
            return state
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def finish_negotiation(self, save_id, event_id, accepted):
        """협상 판정을 기존 선수 이동·사기 반영 트랜잭션에 연결한다."""
        data = self.negotiation_state(save_id, event_id)
        event_type = data["event_type"]
        state = data["negotiation"]
        if accepted and state.get("status") != "accepted":
            raise ValueError("아직 상대를 충분히 설득하지 못했습니다.")
        choice = {
            ("fa_opportunity", True): "sign",
            ("fa_opportunity", False): "pass",
            ("trade_offer", True): "accept",
            ("trade_offer", False): "reject",
            ("player_complaint", True): "promise",
            ("player_complaint", False): "firm",
        }[(event_type, bool(accepted))]
        return self.resolve(save_id, event_id, choice)

    @staticmethod
    def _insert_event(
        connection, save_id, event_date, category, event_type, headline,
        body, choices=(), payload=None, priority="normal", required=False,
    ):
        connection.execute(
            """
            INSERT OR IGNORE INTO manager_events (
                save_id, event_date, category, event_type, headline, body,
                priority, requires_action, choices_json, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                save_id,
                event_date,
                category,
                event_type,
                headline,
                body,
                priority,
                int(required),
                json.dumps(list(choices), ensure_ascii=False),
                json.dumps(payload or {}, ensure_ascii=False),
            ),
        )

    @staticmethod
    def _recent_player_ids(
        connection, save_id, event_type, keys, limit=12,
    ):
        rows = connection.execute(
            """
            SELECT payload_json FROM manager_events
            WHERE save_id = ? AND event_type = ?
            ORDER BY event_date DESC, id DESC
            LIMIT ?
            """,
            (save_id, event_type, int(limit)),
        ).fetchall()
        result = set()
        for row in rows:
            try:
                payload = json.loads(row["payload_json"])
            except (TypeError, json.JSONDecodeError):
                continue
            for key in keys:
                if payload.get(key) is not None:
                    result.add(int(payload[key]))
        return result

    @staticmethod
    def trade_window_for(simulation_date):
        """해당 날짜가 속한 KBO 선수 양도 가능 기간을 반환한다."""
        if isinstance(simulation_date, str):
            simulation_date = date.fromisoformat(simulation_date)
        return next(
            (
                (window_start, window_end)
                for window_start, window_end in TRADE_WINDOWS
                if window_start <= simulation_date <= window_end
            ),
            None,
        )

    @staticmethod
    def _last_event_date(connection, save_id, event_type):
        row = connection.execute(
            """
            SELECT MAX(event_date) AS last_date
            FROM manager_events
            WHERE save_id = ? AND event_type = ?
            """,
            (save_id, event_type),
        ).fetchone()
        value = row["last_date"] if row else None
        return date.fromisoformat(value) if value else None

    @classmethod
    def _should_generate_trade(cls, connection, save_id, simulation_date):
        """거래 기간·최근 제안·마감 임박도를 반영해 제안 발생을 결정한다."""
        window = cls.trade_window_for(simulation_date)
        if window is None:
            return False
        if simulation_date < FIRST_TRADE_EVENT_DATE:
            return False
        if simulation_date == FIRST_TRADE_EVENT_DATE:
            return True

        _window_start, window_end = window
        days_to_deadline = (window_end - simulation_date).days
        deadline_rush = days_to_deadline <= 16
        minimum_gap = 7 if deadline_rush else 21
        last_event = cls._last_event_date(
            connection, save_id, "trade_offer"
        )
        if last_event and simulation_date < last_event + timedelta(days=minimum_gap):
            return False

        # 저장 ID와 날짜로 결정하므로 다시 불러와도 같은 날 같은 결과가 난다.
        chance = 28 if deadline_rush else 12
        return _stable_number(
            save_id,
            simulation_date.isoformat(),
            "trade_offer_day",
            modulo=100,
        ) < chance

    @classmethod
    def _settle_future_player_obligations(
        cls, connection, save_id, simulation_date,
    ):
        """기한이 된 추후 지명 선수를 상대 구단 AI가 확정하고 이적시킨다."""
        connection.execute(FUTURE_PLAYER_OBLIGATION_SQL)
        day = simulation_date.isoformat()
        rows = connection.execute(
            """
            SELECT * FROM trade_future_player_obligations
            WHERE save_id = ? AND status = 'pending'
              AND due_date <= ?
            ORDER BY due_date, id
            """,
            (save_id, day),
        ).fetchall()
        for row in rows:
            try:
                candidates = json.loads(row["candidate_pool_json"])
            except (TypeError, json.JSONDecodeError):
                candidates = []
            valid_ids = {
                int(player_row["id"])
                for player_row in connection.execute(
                    "SELECT id FROM playerdb.players WHERE team = ?",
                    (row["other_team"],),
                ).fetchall()
            }
            candidates = [
                player for player in candidates
                if int(player.get("id") or 0) in valid_ids
            ]
            if not candidates:
                connection.execute(
                    """
                    UPDATE trade_future_player_obligations
                    SET status = 'cancelled'
                    WHERE id = ?
                    """,
                    (row["id"],),
                )
                continue
            selected = min(
                candidates,
                key=lambda player: (
                    int(player.get("rating") or 0),
                    _stable_number(
                        save_id, row["id"], player["id"], modulo=1000
                    ),
                ),
            )
            player_id = int(selected["id"])
            connection.execute(
                """
                UPDATE playerdb.players
                SET team=?,status=0,lineup_pos=0,role='추후 지명 이적'
                WHERE id=?
                """,
                (row["managed_team"], player_id),
            )
            connection.execute(
                """
                UPDATE player_simulation_states
                SET team=?,squad_group='2군'
                WHERE save_id=? AND player_id=?
                """,
                (row["managed_team"], save_id, player_id),
            )
            connection.execute(
                """
                UPDATE trade_future_player_obligations
                SET status='completed', selected_player_id=?
                WHERE id=?
                """,
                (player_id, row["id"]),
            )
            connection.execute(
                """
                INSERT OR IGNORE INTO daily_news (
                    save_id, news_date, category, headline, body, created_at
                ) VALUES (?, ?, '트레이드', ?, ?, CURRENT_TIMESTAMP)
                """,
                (
                    save_id,
                    day,
                    f"추후 지명 선수 확정 · {selected['name']}",
                    (
                        f"트레이드 합의에 따라 추후 지명 선수로 "
                        f"{selected['name']}이 확정됐습니다. 선수는 "
                        f"{row['managed_team']} 2군으로 합류합니다."
                    ),
                ),
            )

    @classmethod
    def generate_daily(
        cls, connection, save_id, managed_team, simulation_date, players,
        states, injuries=(), schedule_events=(),
    ):
        """현재 구현 범위의 날짜별 이벤트를 결정적으로 생성한다."""
        if isinstance(simulation_date, str):
            simulation_date = date.fromisoformat(simulation_date)
        day = simulation_date.isoformat()
        managed = [p for p in players if p["team"] == managed_team]
        cls._settle_future_player_obligations(
            connection, save_id, simulation_date
        )

        event_kind = INITIAL_EVENT_SCHEDULE.get(day)
        if event_kind == "fa":
            cls._generate_fa(
                connection, save_id, managed_team, day, players, states
            )
        elif event_kind == "player_meeting":
            cls._generate_complaint(
                connection, save_id, managed_team, day, managed, states
            )
        if cls._should_generate_trade(
            connection, save_id, simulation_date
        ):
            cls._generate_trade(
                connection, save_id, managed_team, day, players, states
            )
        cls._generate_schedule(
            connection, save_id, managed_team, day, schedule_events
        )
        cls._generate_injuries(
            connection, save_id, managed_team, day, injuries
        )

    @classmethod
    def _generate_schedule(
        cls, connection, save_id, team, day, schedule_events,
    ):
        for event in schedule_events:
            if not event.get("inbox", True):
                continue
            headline = event["title"]
            body = (
                f"{event['detail']}\n\n감독 업무: {event['task']}"
            )
            inbox_category = (
                "선수단 관리"
                if event.get("event_id") == "roster_audit"
                else "경기 일정"
            )
            cls._insert_event(
                connection, save_id, day, inbox_category, "schedule",
                headline,
                body,
                (
                    _choice(
                        "acknowledge",
                        "일정 확인",
                        "업무 내용을 확인하고 수신함으로 돌아갑니다.",
                    ),
                ),
                payload={
                    "schedule_event": event,
                    "team": team,
                    "event_date": day,
                },
                priority=event.get("importance", "normal"),
                required=bool(event.get("requires_action", False)),
            )
            connection.execute(
                """
                INSERT OR IGNORE INTO daily_news (
                    save_id, news_date, category, headline, body, created_at
                ) VALUES (?, ?, '경기 일정', ?, ?, CURRENT_TIMESTAMP)
                """,
                (save_id, day, headline, body),
            )

    @classmethod
    def _generate_injuries(cls, connection, save_id, team, day, injuries):
        for injury in injuries:
            if injury["team"] != team or injury["squad"] != "1군":
                continue
            choices = (
                _choice(
                    "full_rest", "완전 휴식",
                    "재발 위험을 낮추고 컨디션 회복에 집중합니다.",
                ),
                _choice(
                    "rehab", "재활조 편성",
                    "복귀 시점을 조금 앞당기지만 훈련 강도를 제한합니다.",
                ),
                _choice(
                    "play_through", "출전 가능 상태로 관리",
                    "이탈 기간은 줄지만 재발 위험과 피로가 크게 증가합니다.",
                ),
            )
            cls._insert_event(
                connection, save_id, day, "부상", "injury",
                f"{injury['name']} 부상 이탈… {injury['expected_days']}일 결장 전망",
                (
                    f"{injury['name']}이(가) {injury['injury_type']} 진단을 받아 "
                    f"약 {injury['expected_days']}일 이탈할 전망입니다. "
                    "메디컬 센터는 재발 방지를 최우선으로 치료 계획을 검토하고 있으며, "
                    "팬들도 선수의 빠르고 안전한 복귀를 기다리고 있습니다."
                ),
                choices,
                {
                    "player_id": injury["player_id"],
                    "player_name": injury["name"],
                    "team": team,
                    "injury_type": injury["injury_type"],
                    "expected_days": injury["expected_days"],
                    "position": injury.get("position") or "-",
                    "age": injury.get("age") or "-",
                    "squad": injury.get("squad") or "1군",
                    "condition": injury.get("condition"),
                    "fatigue": injury.get("fatigue"),
                },
                priority="critical",
                required=True,
            )

    @classmethod
    def _generate_board(
        cls, connection, save_id, team, day, players, states,
    ):
        first = [p for p in players if int(p.get("status") or 0) == 1]
        injured = sum(
            int(states.get(p["id"], {}).get("injury_days", 0)) > 0
            for p in first
        )
        average_condition = round(
            sum(int(states.get(p["id"], {}).get("condition", 80)) for p in first)
            / max(1, len(first))
        )
        choices = (
            _choice(
                "accept", "이사회 요구 수용",
                "목표 달성을 약속해 이사회 신뢰를 높입니다.",
            ),
            _choice(
                "negotiate", "현실적인 조정 요청",
                "현재 선수단 상태를 근거로 목표 수준을 조정합니다.",
            ),
            _choice(
                "challenge", "현장 권한 강조",
                "감독 권한을 지키지만 이사회 관계가 악화될 수 있습니다.",
            ),
        )
        cls._insert_event(
            connection, save_id, day, "이사회", "board_review",
            f"{team} 월간 운영 보고 요청",
            (
                f"현재 1군 {len(first)}명, 부상 {injured}명, 평균 컨디션 "
                f"{average_condition}입니다. 이사회가 선수단 운영 방향과 "
                "다가오는 일정의 성과 기준에 대한 답변을 요청했습니다."
            ),
            choices,
            {
                "team": team,
                "first_team_count": len(first),
                "injured_count": injured,
                "average_condition": average_condition,
            },
            priority="high",
            required=True,
        )

    @classmethod
    def _generate_complaint(
        cls, connection, save_id, team, day, players, states,
    ):
        recently_discussed = cls._recent_player_ids(
            connection, save_id, "player_complaint", ("player_id",), limit=4
        )
        candidates = []
        for player in players:
            if player["id"] in recently_discussed:
                continue
            state = states.get(player["id"], {})
            morale = int(state.get("morale", 75))
            is_second = int(player.get("status") or 0) == 0
            pressure = (100 - morale) + (12 if is_second else 0)
            pressure += max(0, int(overall_rating(player)) - 11)
            candidates.append((pressure, player, state))
        if not candidates:
            return
        _pressure, player, state = max(candidates, key=lambda item: item[0])
        reason = (
            "1군 기회를 받지 못하고 있는 점"
            if int(player.get("status") or 0) == 0
            else "최근 역할과 훈련 운영 방식"
        )
        choices = (
            _choice(
                "promise", "기회를 약속한다",
                "선수 사기가 크게 오르지만 향후 기용 약속이 생깁니다.",
            ),
            _choice(
                "explain", "경쟁 원칙을 설명한다",
                "감독 리더십에 따라 선수가 결정을 받아들일 수 있습니다.",
            ),
            _choice(
                "firm", "팀 결정임을 강조한다",
                "질서를 세우지만 선수의 불만이 커질 수 있습니다.",
            ),
        )
        cls._insert_event(
            connection, save_id, day, "선수 면담", "player_complaint",
            f"{player['name']}, 감독 면담 요청",
            (
                f"{player['name']}은(는) {reason}에 불만을 표시했습니다. "
                f"현재 사기는 {state.get('morale', 75)}, 소속은 "
                f"{'1군' if player.get('status') else '2군'}입니다."
            ),
            choices,
            {
                "player_id": player["id"],
                "player_name": player["name"],
                "managed_team": team,
                "squad": "1군" if player.get("status") else "2군",
                "morale": state.get("morale", 75),
                "position": player.get("pos") or player.get("position_group"),
                "age": player.get("age"),
                "player_scoring_mode": "dialogue_v4",
            },
            priority="high",
            required=True,
        )

    @classmethod
    def _generate_entry(
        cls, connection, save_id, team, day, players, states,
    ):
        injured_first = [
            p for p in players
            if int(p.get("status") or 0) == 1
            and int(states.get(p["id"], {}).get("injury_days", 0)) > 0
        ]
        healthy_second = [
            p for p in players
            if int(p.get("status") or 0) == 0
            and int(states.get(p["id"], {}).get("injury_days", 0)) == 0
        ]
        if not injured_first or not healthy_second:
            cls._insert_event(
                connection, save_id, day, "엔트리", "entry_review",
                "1군 엔트리 정기 점검",
                "등록 마감 전 1군 엔트리를 확인했습니다. 즉시 교체가 필요한 부상자는 없습니다.",
                (
                    _choice("submit_current", "현재 엔트리 제출", "현재 1군 구성을 확정합니다."),
                    _choice("delegate", "수석코치에게 위임", "현재 전력 평가를 기준으로 제출합니다."),
                ),
                {"team": team},
                priority="high",
                required=True,
            )
            return
        demote = max(
            injured_first,
            key=lambda p: int(states[p["id"]]["injury_days"]),
        )
        same_position = [
            p for p in healthy_second
            if p.get("position_group") == demote.get("position_group")
        ] or healthy_second
        promote = max(same_position, key=overall_rating)
        month = int(str(day)[5:7])
        roster_reason = {
            11: "포스트시즌 종료 뒤 선수단 뎁스와 회복 상태를 재점검한 결과",
            12: "비시즌 전력 구상과 내년 캠프 경쟁 구도를 검토한 결과",
            1: "스프링캠프 준비 상태와 선수별 훈련 성과를 평가한 결과",
            2: "실전 캠프 점검과 개막 엔트리 경쟁력을 반영한 결과",
            3: "개막 직전 컨디션과 최근 실전 경기력을 반영한 결과",
        }.get(month, "최근 경기력과 포지션별 선수단 수요를 종합한 결과")
        cls._insert_event(
            connection, save_id, day, "엔트리", "entry_review",
            f"{team} {promote['name']}, 1군 콜업 예정",
            (
                f"{team}은 {roster_reason} {promote['name']}을(를) 1군에 등록하는 안을 "
                f"마련했습니다. {demote['name']}의 부상 공백과 포지션 구성을 고려한 결정이며, "
                "최종 엔트리는 현장 점검 뒤 확정될 예정입니다."
            ),
            (
                _choice("recommended_swap", "추천 교체안 제출", f"{promote['name']}을 1군에 등록합니다."),
                _choice("keep_current", "현재 엔트리 유지", "추가 검토 없이 기존 엔트리를 유지합니다."),
            ),
            {
                "team": team,
                "demote_id": demote["id"],
                "demote_name": demote["name"],
                "promote_id": promote["id"],
                "promote_name": promote["name"],
            },
            priority="critical",
            required=True,
        )

    @classmethod
    def _generate_trade(
        cls, connection, save_id, team, day, players, states,
    ):
        recently_proposed = cls._recent_player_ids(
            connection,
            save_id,
            "trade_offer",
            ("outgoing_id", "incoming_id"),
            limit=5,
        )
        outgoing = [
            p for p in players
            if p["team"] == team and int(p.get("status") or 0) == 0
            and int(states.get(p["id"], {}).get("injury_days", 0)) == 0
            and p["id"] not in recently_proposed
        ]
        incoming = [
            p for p in players
            if p["team"] != team and int(p.get("status") or 0) == 0
            and int(states.get(p["id"], {}).get("injury_days", 0)) == 0
            and p["id"] not in recently_proposed
        ]
        if not outgoing or not incoming:
            return
        outgoing.sort(key=lambda p: (overall_rating(p), p["name"]), reverse=True)
        give = outgoing[min(2, len(outgoing) - 1)]
        target_score = overall_rating(give)
        receive = min(
            incoming,
            key=lambda p: (
                abs(overall_rating(p) - target_score),
                _stable_number(save_id, day, p["id"], modulo=1000),
            ),
        )
        choices = (
            _choice("accept", "트레이드 수락", "두 선수의 소속을 즉시 맞바꿉니다."),
            _choice("counter", "추가 조건 요구", "협상은 종료되지만 프런트 관계를 유지합니다."),
            _choice("reject", "제안 거절", "현재 선수단을 유지합니다."),
        )
        cls._insert_event(
            connection, save_id, day, "트레이드", "trade_offer",
            f"{receive['team']}, {receive['name']} 트레이드 제안",
            (
                f"{receive['team']}이(가) {receive['name']}을 보내는 대신 "
                f"{give['name']}을 요구했습니다. 양 선수의 내부 종합 평가는 "
                f"{overall_rating(receive)}와 {overall_rating(give)}입니다."
            ),
            choices,
            {
                "managed_team": team,
                "other_team": receive["team"],
                "offer_date": str(day),
                "outgoing_id": give["id"],
                "outgoing_name": give["name"],
                "incoming_id": receive["id"],
                "incoming_name": receive["name"],
                "outgoing_rating": overall_rating(give),
                "incoming_rating": overall_rating(receive),
                "outgoing_salary": int(give.get("salary") or 0),
                "incoming_salary": int(receive.get("salary") or 0),
                "trade_terms": {
                    "status": "original",
                    "incoming_name": receive["name"],
                    "outgoing_name": give["name"],
                    "additional_incoming_id": None,
                    "additional_incoming_name": "",
                    "additional_incoming_rating": 0,
                    "additional_incoming_salary": 0,
                    "additional_outgoing_id": None,
                    "additional_outgoing_name": "",
                    "additional_outgoing_rating": 0,
                    "additional_outgoing_salary": 0,
                    "future_player_pool": [],
                    "future_player_pool_outgoing": [],
                    "future_player_due_days": 0,
                    "cash_to_user_10k": 0,
                    "cash_from_user_10k": 0,
                    "cash_label": "없음",
                    "cash_from_user_label": "없음",
                    "compensation_type": "none",
                    "compensation_direction": "none",
                    "summary": "선수 1대1 교환",
                    "round": 0,
                },
            },
            priority="high",
            required=True,
        )

    @classmethod
    def _generate_fa(
        cls, connection, save_id, team, day, players, states,
    ):
        recently_recommended = cls._recent_player_ids(
            connection, save_id, "fa_opportunity", ("player_id",), limit=8
        )
        candidates = [
            p for p in players
            if p["team"] != team
            and int(p.get("age") or 0) >= 30
            and int(states.get(p["id"], {}).get("injury_days", 0)) == 0
            and p["id"] not in recently_recommended
        ]
        if not candidates:
            return
        candidates.sort(
            key=lambda p: (
                overall_rating(p),
                _stable_number(save_id, day, p["id"], modulo=1000),
            ),
            reverse=True,
        )
        player = candidates[0]
        salary = max(3000, int(player.get("salary") or 3000))
        offer = int(round(salary * 1.15 / 100) * 100)
        choices = (
            _choice("sign", "FA 계약 제시", f"연봉 {offer:,}만원 조건으로 영입합니다."),
            _choice("short_offer", "단년 저가 제안", "영입 확률은 낮지만 재정 부담을 줄입니다."),
            _choice("pass", "영입 철회", "현재 선수단과 예산을 유지합니다."),
        )
        cls._insert_event(
            connection, save_id, day, "FA", "fa_opportunity",
            f"FA 시장 추천 · {player['name']}",
            (
                f"프런트가 {player['team']} 출신 {player['name']}을 FA 영입 "
                f"후보로 추천했습니다. {player.get('pos') or '-'}·"
                f"{player.get('age')}세, 내부 종합 {overall_rating(player)}, "
                f"예상 연봉은 {offer:,}만원입니다."
            ),
            choices,
            {
                "managed_team": team,
                "old_team": player["team"],
                "player_id": player["id"],
                "player_name": player["name"],
                "offer_salary": offer,
            },
            priority="high",
            required=True,
        )

    def resolve(
        self, save_id, event_id, choice_key, resolution_data=None,
    ):
        """선택 결과를 세이브와 선수 DB에 한 트랜잭션으로 반영한다."""
        connection = sqlite3.connect(self.saves_db_path)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute(
                "ATTACH DATABASE ? AS playerdb", (self.player_db_path,)
            )
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT * FROM manager_events
                WHERE save_id = ? AND id = ?
                """,
                (save_id, event_id),
            ).fetchone()
            if row is None:
                raise ValueError("이벤트를 찾을 수 없습니다.")
            if row["status"] != "open":
                return row["result_text"] or "이미 처리된 이벤트입니다."
            choices = json.loads(row["choices_json"])
            if choice_key not in {choice["key"] for choice in choices}:
                raise ValueError("선택할 수 없는 응답입니다.")
            payload = json.loads(row["payload_json"])
            if resolution_data:
                payload["manager_decision"] = dict(resolution_data)
                connection.execute(
                    "UPDATE manager_events SET payload_json=? WHERE id=?",
                    (json.dumps(payload, ensure_ascii=False), event_id),
                )
            result = self._apply_resolution(
                connection, save_id, row["event_type"], choice_key, payload
            )
            connection.execute(
                """
                UPDATE manager_events
                SET status = 'resolved', resolution_key = ?, result_text = ?,
                    is_read = 1, resolved_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (choice_key, result, event_id),
            )
            connection.execute(
                """
                INSERT OR IGNORE INTO daily_news (
                    save_id, news_date, category, headline, body, created_at
                ) VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """,
                (
                    save_id,
                    row["event_date"],
                    row["category"],
                    f"결정 완료 · {row['headline']}",
                    result,
                ),
            )
            connection.commit()
            return result
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def _apply_resolution(
        connection, save_id, event_type, choice, payload,
    ):
        if event_type == "injury":
            player_id = payload["player_id"]
            if choice == "full_rest":
                connection.execute(
                    """
                    UPDATE player_simulation_states
                    SET fatigue = MAX(0, fatigue - 15),
                        condition = MIN(100, condition + 6),
                        injury_risk = MAX(1, injury_risk - 4),
                        squad_group = '재활조'
                    WHERE save_id = ? AND player_id = ?
                    """,
                    (save_id, player_id),
                )
                return f"{payload['player_name']}에게 완전 휴식을 부여했습니다. 재발 위험이 낮아집니다."
            if choice == "rehab":
                connection.execute(
                    """
                    UPDATE player_simulation_states
                    SET injury_days = MAX(1, injury_days - 2),
                        fatigue = MAX(0, fatigue - 8),
                        squad_group = '재활조'
                    WHERE save_id = ? AND player_id = ?
                    """,
                    (save_id, player_id),
                )
                return f"{payload['player_name']}을 재활조에 편성했습니다. 예상 복귀가 최대 2일 앞당겨집니다."
            connection.execute(
                """
                UPDATE player_simulation_states
                SET injury_days = MAX(1, injury_days - 4),
                    fatigue = MIN(100, fatigue + 15),
                    injury_risk = MIN(100, injury_risk + 15),
                    morale = MIN(100, morale + 2)
                WHERE save_id = ? AND player_id = ?
                """,
                (save_id, player_id),
            )
            return f"{payload['player_name']}을 출전 가능 상태로 관리합니다. 복귀는 빨라지지만 재발 위험이 크게 올랐습니다."

        if event_type == "player_complaint":
            delta = {"promise": 9, "explain": 3, "firm": -7}[choice]
            connection.execute(
                """
                UPDATE player_simulation_states
                SET morale = MAX(0, MIN(100, morale + ?))
                WHERE save_id = ? AND player_id = ?
                """,
                (delta, save_id, payload["player_id"]),
            )
            return {
                "promise": f"{payload['player_name']}에게 향후 기회를 약속했습니다. 선수의 사기가 크게 올랐습니다.",
                "explain": f"{payload['player_name']}이 경쟁 원칙에 대한 설명을 받아들였습니다.",
                "firm": f"{payload['player_name']}에게 팀 결정을 강조했습니다. 선수의 불만이 커졌습니다.",
            }[choice]

        if event_type == "board_review":
            delta = {"accept": 4, "negotiate": 0, "challenge": -6}[choice]
            row = connection.execute(
                "SELECT state_json FROM governance_state WHERE save_id = ?",
                (save_id,),
            ).fetchone()
            state = json.loads(row["state_json"]) if row else {}
            confidence = max(
                0, min(100, int(state.get("board_confidence", 75)) + delta)
            )
            state["board_confidence"] = confidence
            connection.execute(
                """
                INSERT INTO governance_state (
                    save_id, board_confidence, gm_relationship,
                    state_json, updated_at
                ) VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(save_id) DO UPDATE SET
                    board_confidence = excluded.board_confidence,
                    state_json = excluded.state_json,
                    updated_at = excluded.updated_at
                """,
                (
                    save_id,
                    confidence,
                    int(state.get("gm_relationship", 70)),
                    json.dumps(state, ensure_ascii=False),
                ),
            )
            return {
                "accept": f"이사회 요구를 수용했습니다. 이사회 신뢰는 {confidence}입니다.",
                "negotiate": f"선수단 상태를 근거로 목표 조정을 요청했습니다. 이사회 신뢰는 {confidence}입니다.",
                "challenge": f"현장 권한을 강조했습니다. 이사회 신뢰가 {confidence}으로 하락했습니다.",
            }[choice]

        if event_type == "entry_review":
            if choice == "recommended_swap" and payload.get("promote_id"):
                connection.execute(
                    "UPDATE playerdb.players SET status=0,lineup_pos=0,role='' WHERE id=?",
                    (payload["demote_id"],),
                )
                connection.execute(
                    "UPDATE playerdb.players SET status=1,lineup_pos=0,role='' WHERE id=?",
                    (payload["promote_id"],),
                )
                connection.execute(
                    """
                    UPDATE player_simulation_states SET squad_group='2군'
                    WHERE save_id=? AND player_id=?
                    """,
                    (save_id, payload["demote_id"]),
                )
                connection.execute(
                    """
                    UPDATE player_simulation_states SET squad_group='1군'
                    WHERE save_id=? AND player_id=?
                    """,
                    (save_id, payload["promote_id"]),
                )
                return f"{payload['promote_name']}을 1군에 등록하고 {payload['demote_name']}을 말소했습니다."
            return "현재 1군 엔트리를 그대로 제출했습니다."

        if event_type == "trade_offer":
            if choice == "accept":
                connection.execute(
                    """
                    UPDATE playerdb.players
                    SET team=?,status=0,lineup_pos=0,role=''
                    WHERE id=?
                    """,
                    (payload["other_team"], payload["outgoing_id"]),
                )
                connection.execute(
                    """
                    UPDATE playerdb.players
                    SET team=?,status=0,lineup_pos=0,role=''
                    WHERE id=?
                    """,
                    (payload["managed_team"], payload["incoming_id"]),
                )
                connection.execute(
                    """
                    UPDATE player_simulation_states SET team=?,squad_group='2군'
                    WHERE save_id=? AND player_id=?
                    """,
                    (payload["other_team"], save_id, payload["outgoing_id"]),
                )
                connection.execute(
                    """
                    UPDATE player_simulation_states SET team=?,squad_group='2군'
                    WHERE save_id=? AND player_id=?
                    """,
                    (payload["managed_team"], save_id, payload["incoming_id"]),
                )
                terms = dict(payload.get("trade_terms") or {})
                additional_id = terms.get("additional_incoming_id")
                additional_name = str(
                    terms.get("additional_incoming_name") or ""
                )
                if additional_id:
                    connection.execute(
                        """
                        UPDATE playerdb.players
                        SET team=?,status=0,lineup_pos=0,role=''
                        WHERE id=?
                        """,
                        (payload["managed_team"], int(additional_id)),
                    )
                    connection.execute(
                        """
                        UPDATE player_simulation_states
                        SET team=?,squad_group='2군'
                        WHERE save_id=? AND player_id=?
                        """,
                        (
                            payload["managed_team"],
                            save_id,
                            int(additional_id),
                        ),
                    )
                additional_outgoing_id = terms.get(
                    "additional_outgoing_id"
                )
                additional_outgoing_name = str(
                    terms.get("additional_outgoing_name") or ""
                )
                if additional_outgoing_id:
                    connection.execute(
                        """
                        UPDATE playerdb.players
                        SET team=?,status=0,lineup_pos=0,role=''
                        WHERE id=?
                        """,
                        (
                            payload["other_team"],
                            int(additional_outgoing_id),
                        ),
                    )
                    connection.execute(
                        """
                        UPDATE player_simulation_states
                        SET team=?,squad_group='2군'
                        WHERE save_id=? AND player_id=?
                        """,
                        (
                            payload["other_team"],
                            save_id,
                            int(additional_outgoing_id),
                        ),
                    )
                cash_to_user = max(
                    0, int(terms.get("cash_to_user_10k") or 0)
                )
                cash_from_user = max(
                    0, int(terms.get("cash_from_user_10k") or 0)
                )
                cash_amount = cash_to_user - cash_from_user
                future_pool = list(
                    terms.get("future_player_pool") or []
                )
                future_pool_outgoing = list(
                    terms.get("future_player_pool_outgoing") or []
                )
                future_due_date = None
                if future_pool or future_pool_outgoing:
                    connection.execute(FUTURE_PLAYER_OBLIGATION_SQL)
                    try:
                        offer_date = date.fromisoformat(
                            str(payload.get("offer_date"))
                        )
                    except ValueError:
                        offer_date = date(2025, 11, 4)
                    future_due_date = (
                        offer_date
                        + timedelta(
                            days=max(
                                1,
                                int(
                                    terms.get("future_player_due_days")
                                    or 30
                                ),
                            )
                        )
                    ).isoformat()
                    obligations = []
                    if future_pool:
                        obligations.append(
                            (
                                payload["managed_team"],
                                payload["other_team"],
                                future_pool,
                            )
                        )
                    if future_pool_outgoing:
                        obligations.append(
                            (
                                payload["other_team"],
                                payload["managed_team"],
                                future_pool_outgoing,
                            )
                        )
                    connection.executemany(
                        """
                        INSERT INTO trade_future_player_obligations (
                            save_id, managed_team, other_team, due_date,
                            candidate_pool_json
                        ) VALUES (?, ?, ?, ?, ?)
                        """,
                        tuple(
                            (
                                save_id,
                                recipient_team,
                                source_team,
                                future_due_date,
                                json.dumps(pool, ensure_ascii=False),
                            )
                            for recipient_team, source_team, pool in obligations
                        ),
                    )
                if cash_amount != 0:
                    connection.execute(
                        """
                        CREATE TABLE IF NOT EXISTS club_finance_transactions (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            save_id INTEGER NOT NULL,
                            team TEXT NOT NULL,
                            amount_10k INTEGER NOT NULL,
                            category TEXT NOT NULL,
                            details TEXT NOT NULL,
                            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                        )
                        """
                    )
                    details = (
                        f"{payload['other_team']}과의 트레이드 현금 보상 · "
                        f"{payload['incoming_name']} / {payload['outgoing_name']}"
                    )
                    connection.executemany(
                        """
                        INSERT INTO club_finance_transactions (
                            save_id, team, amount_10k, category, details
                        ) VALUES (?, ?, ?, '트레이드', ?)
                        """,
                        (
                            (
                                save_id,
                                payload["managed_team"],
                                cash_amount,
                                details,
                            ),
                            (
                                save_id,
                                payload["other_team"],
                                -cash_amount,
                                details,
                            ),
                        ),
                    )
                result = (
                    f"트레이드가 성사됐습니다. {payload['incoming_name']}이 합류하고 "
                    f"{payload['outgoing_name']}이 {payload['other_team']}으로 이동합니다."
                )
                if additional_name:
                    result += f" 추가 보상 선수 {additional_name}도 함께 합류합니다."
                if additional_outgoing_name:
                    result += (
                        f" 상대 구단의 요구에 따라 {additional_outgoing_name}도 "
                        f"{payload['other_team']}으로 함께 이동합니다."
                    )
                if cash_to_user:
                    result += (
                        f" 현금 보상 {ManagerEventService._format_trade_cash(cash_to_user)}이 "
                        "구단 재정 거래 내역에 반영됐습니다."
                    )
                if cash_from_user:
                    result += (
                        f" 상대 구단에 지급할 현금 "
                        f"{ManagerEventService._format_trade_cash(cash_from_user)}이 "
                        "구단 재정 거래 내역에 반영됐습니다."
                    )
                if future_pool:
                    names = ", ".join(
                        str(player.get("name") or "후보")
                        for player in future_pool
                    )
                    result += (
                        f" 추후 지명 선수 후보는 {names}이며 "
                        f"{payload['other_team']}이 {future_due_date}까지 "
                        "한 명을 확정할 예정입니다."
                    )
                if future_pool_outgoing:
                    names = ", ".join(
                        str(player.get("name") or "후보")
                        for player in future_pool_outgoing
                    )
                    result += (
                        f" 우리 구단 추후 지명 후보는 {names}이며 "
                        f"{payload['other_team']}이 {future_due_date}까지 "
                        "한 명을 확정할 예정입니다."
                    )
                return result
            if choice == "counter":
                return "추가 조건을 요구했습니다. 상대 구단이 이번 제안을 철회했습니다."
            return "트레이드 제안을 거절했습니다. 선수단 변동은 없습니다."

        if event_type == "fa_opportunity":
            if choice in ("sign", "short_offer"):
                salary = int(payload["offer_salary"])
                if choice == "short_offer":
                    salary = int(round(salary * 0.85 / 100) * 100)
                    success = _stable_number(
                        save_id, payload["player_id"], "short_fa", modulo=100
                    ) < 45
                    if not success:
                        return f"{payload['player_name']} 측이 단년 저가 제안을 거절했습니다."
                connection.execute(
                    """
                    UPDATE playerdb.players
                    SET team=?,salary=?,status=0,lineup_pos=0,role='FA 영입'
                    WHERE id=?
                    """,
                    (
                        payload["managed_team"],
                        salary,
                        payload["player_id"],
                    ),
                )
                connection.execute(
                    """
                    UPDATE player_simulation_states
                    SET team=?,squad_group='2군',morale=MIN(100,morale+5)
                    WHERE save_id=? AND player_id=?
                    """,
                    (
                        payload["managed_team"],
                        save_id,
                        payload["player_id"],
                    ),
                )
                return (
                    f"{payload['player_name']}과 연봉 {salary:,}만원에 FA 계약을 "
                    f"체결했습니다. 선수는 {payload['managed_team']} 2군에 합류합니다."
                )
            return f"{payload['player_name']} 영입을 철회했습니다."

        if event_type == "schedule":
            schedule_event = dict(payload.get("schedule_event") or {})
            if schedule_event.get("event_id") == "roster_audit":
                decisions = list(
                    (payload.get("manager_decision") or {}).get("players")
                    or []
                )
                manager_decision = dict(
                    payload.get("manager_decision") or {}
                )
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS roster_audit_decisions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        save_id INTEGER NOT NULL,
                        audit_date TEXT NOT NULL,
                        team TEXT NOT NULL,
                        player_id INTEGER NOT NULL,
                        player_name TEXT NOT NULL,
                        decision TEXT NOT NULL,
                        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(save_id, audit_date, player_id)
                    )
                    """
                )
                audit_date = str(
                    payload.get("event_date")
                    or manager_decision.get("event_date")
                    or "2025-11-03"
                )
                team = str(
                    payload.get("team")
                    or manager_decision.get("team")
                    or "우리 구단"
                )
                for item in decisions:
                    connection.execute(
                        """
                        INSERT INTO roster_audit_decisions (
                            save_id, audit_date, team, player_id,
                            player_name, decision
                        ) VALUES (?, ?, ?, ?, ?, ?)
                        ON CONFLICT(save_id, audit_date, player_id) DO UPDATE SET
                            decision=excluded.decision,
                            player_name=excluded.player_name,
                            updated_at=CURRENT_TIMESTAMP
                        """,
                        (
                            save_id, audit_date, team,
                            int(item.get("player_id") or 0),
                            str(item.get("player_name") or "-"),
                            str(item.get("decision") or "재검토"),
                        ),
                    )
                counts = {}
                for item in decisions:
                    decision = str(item.get("decision") or "재검토")
                    counts[decision] = counts.get(decision, 0) + 1
                summary = " · ".join(
                    f"{label} {counts.get(label, 0)}명"
                    for label in (
                        "보류·재계약", "계약 재검토",
                        "퓨처스 육성", "방출 후보",
                    )
                )
                return (
                    f"{team} 선수단 1차 분류안을 저장했습니다. {summary}. "
                    "이번 결정은 즉시 방출로 처리되지 않으며, 11월 25일 "
                    "보류선수 명단 최종 점검에서 다시 확정합니다."
                )
            return "일정과 담당 업무를 확인했습니다."

        return "결정을 확인했습니다."
