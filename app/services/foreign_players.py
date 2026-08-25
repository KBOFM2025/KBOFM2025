"""외국인 선수 재계약·방출 및 신규 FA 시장 서비스."""

import hashlib
import json
import random
import sqlite3
from datetime import datetime

from app.player_ratings import overall_rating
from database.contract_data import USD_KRW_REFERENCE_RATE
from database.league_simulation_repository import SIMULATION_SCHEMA


FOREIGN_LIMIT = 3
FOREIGN_PITCHER_LIMIT = 2
NEW_FOREIGN_CAP_USD = 1_000_000
TEAM_FOREIGN_CAP_USD = 4_000_000
NEW_FOREIGN_CAP = NEW_FOREIGN_CAP_USD  # 이전 import 호환
MARKET_POOL_SIZE = 24
FOREIGN_CAP_SOURCE = "https://www.koreabaseball.com/MediaNews/Notice/View.aspx?bdSe=7651"

NAME_POOLS = {
    "미국": (
        ("제이크", "앤더슨"), ("로건", "카터"), ("마커스", "리드"),
        ("콜", "해리슨"), ("에릭", "밀러"), ("브랜든", "워커"),
        ("트레버", "홀"), ("타일러", "브룩스"), ("코너", "베넷"),
    ),
    "도미니카": (
        ("루이스", "오르테가"), ("미겔", "산토스"), ("라몬", "크루스"),
        ("호세", "페랄타"), ("에밀리오", "로하스"), ("디에고", "카스티요"),
    ),
    "베네수엘라": (
        ("안드레스", "모라"), ("호세", "바르가스"), ("카를로스", "멘데스"),
        ("마누엘", "수아레스"), ("헤수스", "마르티네스"), ("엔리케", "살라자르"),
    ),
    "쿠바": (
        ("야스마니", "디아스"), ("루이스", "에레라"), ("아리엘", "가르시아"),
        ("다얀", "로드리게스"), ("오스카", "페레스"),
    ),
    "멕시코": (
        ("알레한드로", "로페스"), ("세사르", "라미레스"), ("훌리오", "베가"),
        ("마르코", "토레스"), ("에드가", "나바로"),
    ),
    "푸에르토리코": (
        ("하비에르", "리베라"), ("앙헬", "플로레스"), ("펠릭스", "콜론"),
        ("로베르토", "델가도"), ("이반", "소토"),
    ),
}
NATIONALITY_WEIGHTS = {
    "미국": 38, "도미니카": 20, "베네수엘라": 17,
    "쿠바": 10, "멕시코": 8, "푸에르토리코": 7,
}

# 실제 구단 관계자에 대한 평가가 아니라 게임 밸런스를 위한 초기 능력치다.
# 추후 스카우터 고용 시스템이 구현되면 이 기본값 대신 직원 능력치 합산값을 사용한다.
TEAM_SCOUTING_DEPARTMENTS = {
    "KIA 타이거즈": {"discovery": 15, "accuracy": 14, "network": 15},
    "삼성 라이온즈": {"discovery": 16, "accuracy": 15, "network": 15},
    "LG 트윈스": {"discovery": 17, "accuracy": 16, "network": 16},
    "두산 베어스": {"discovery": 14, "accuracy": 16, "network": 13},
    "KT 위즈": {"discovery": 14, "accuracy": 15, "network": 14},
    "SSG 랜더스": {"discovery": 17, "accuracy": 15, "network": 16},
    "롯데 자이언츠": {"discovery": 16, "accuracy": 14, "network": 15},
    "한화 이글스": {"discovery": 16, "accuracy": 15, "network": 15},
    "NC 다이노스": {"discovery": 18, "accuracy": 17, "network": 16},
    "키움 히어로즈": {"discovery": 15, "accuracy": 18, "network": 13},
}
DEFAULT_SCOUTING_DEPARTMENT = {"discovery": 14, "accuracy": 14, "network": 14}

PITCHER_ARCHETYPES = (
    ("파워 선발", {"pitcher_velocity": 3, "pitcher_stuff": 3, "pitcher_command": -1},
     "강한 포심과 결정구로 타자를 압도하는 파워형 선발"),
    ("제구형 선발", {"pitcher_command": 3, "pitcher_pitchability": 3, "pitcher_velocity": -1},
     "볼넷을 억제하고 코너워크로 승부하는 경기 운영형 선발"),
    ("땅볼 유도형", {"pitcher_movement": 3, "pitcher_stamina": 2, "pitcher_stuff": -1},
     "움직임이 큰 구종으로 장타를 억제하는 땅볼 유도형 투수"),
    ("완성형 선발", {"pitcher_command": 2, "pitcher_movement": 2, "pitcher_pitchability": 2},
     "뚜렷한 약점 없이 긴 이닝을 책임질 수 있는 완성형 선발"),
)

HITTER_ARCHETYPES = (
    ("거포", {"power": 4, "contact": -1, "speed": -2},
     "중심 타선에서 장타 생산을 기대할 수 있는 거포"),
    ("정교한 타자", {"contact": 3, "plate_discipline": 3, "power": -1},
     "정교한 타격과 선구안으로 출루를 만드는 타자"),
    ("호타준족", {"contact": 2, "speed": 4, "fielding_range": 2},
     "빠른 발과 넓은 수비 범위를 겸비한 호타준족"),
    ("공수겸장", {"power": 2, "fielding_range": 3, "throwing_power": 2},
     "공격과 수비에서 모두 기여할 수 있는 공수겸장 야수"),
)


def _clamp_rating(value):
    return max(5, min(20, int(value)))


def _generated_market_pool(save_id, size=MARKET_POOL_SIZE):
    """세이브마다 재현 가능한 신규 외국인 선수 시장을 생성한다."""
    rng = random.Random(f"kbo-fm-foreign-market:{save_id}")
    used_names = set()
    players = []
    for index in range(size):
        is_pitcher = index < size // 2
        available_nationalities = [
            country for country, names in NAME_POOLS.items()
            if any(name not in used_names for name in names)
        ]
        nationality = rng.choices(
            available_nationalities,
            weights=[NATIONALITY_WEIGHTS[country] for country in available_nationalities],
            k=1,
        )[0]
        available_names = [
            name for name in NAME_POOLS[nationality] if name not in used_names
        ]
        first_name, last_name = rng.choice(available_names)
        used_names.add((first_name, last_name))

        age = rng.randint(25, 34)
        base = rng.randint(11, 16)
        if is_pitcher:
            position_group = "P"
            primary_position = rng.choices(("SP", "RP"), weights=(88, 12), k=1)[0]
        else:
            primary_position = rng.choice(("1B", "2B", "3B", "SS", "LF", "CF", "RF"))
            position_group = "IF" if primary_position in {"1B", "2B", "3B", "SS"} else "OF"
        player = {
            "id": f"GEN2-{save_id}-{'P' if is_pitcher else 'H'}-{index + 1:03d}",
            "name": f"{first_name} {last_name}",
            "nationality": nationality,
            "pos": "P" if is_pitcher else position_group,
            "position_group": position_group,
            "primary_position": primary_position,
            "age": age,
            "generated": True,
        }
        if is_pitcher:
            style, modifiers, summary = rng.choice(PITCHER_ARCHETYPES)
            ratings = {
                "pitcher_velocity": base + rng.randint(-2, 2),
                "pitcher_stuff": base + rng.randint(-2, 2),
                "pitcher_command": base + rng.randint(-2, 2),
                "pitcher_movement": base + rng.randint(-2, 2),
                "pitcher_stamina": base + rng.randint(-2, 2),
                "pitcher_pitchability": base + rng.randint(-2, 2),
            }
            handedness = rng.choices(("우투우타", "좌투좌타"), weights=(72, 28), k=1)[0]
        else:
            style, modifiers, summary = rng.choice(HITTER_ARCHETYPES)
            ratings = {
                "contact": base + rng.randint(-2, 2),
                "power": base + rng.randint(-2, 2),
                "plate_discipline": base + rng.randint(-2, 2),
                "fielding_range": base + rng.randint(-3, 2),
                "throwing_power": base + rng.randint(-3, 2),
                "speed": base + rng.randint(-4, 3),
            }
            handedness = rng.choices(
                ("우투우타", "우투좌타", "우투양타"), weights=(48, 42, 10), k=1
            )[0]
        for rating, modifier in modifiers.items():
            ratings[rating] = ratings.get(rating, base) + modifier
        player.update({key: _clamp_rating(value) for key, value in ratings.items()})
        player["bats_throws"] = handedness
        player["archetype"] = style
        player["summary"] = summary

        core = (
            [player[key] for key in (
                "pitcher_stuff", "pitcher_command", "pitcher_movement",
                "pitcher_stamina", "pitcher_pitchability",
            )]
            if is_pitcher else
            [player[key] for key in ("contact", "power", "plate_discipline")]
        )
        ability = sum(core) / len(core)
        age_adjustment = max(-60_000, (30 - age) * 15_000)
        salary = 180_000 + (ability - 8) * 105_000 + age_adjustment + rng.randint(-50_000, 50_000)
        player["asking_salary"] = max(
            250_000, min(NEW_FOREIGN_CAP_USD, int(round(salary / 10_000) * 10_000))
        )
        player["currency"] = "USD"
        player["contract_end_date"] = "2026-11-30"
        players.append(player)
    return players


class ForeignPlayerService:
    def __init__(self, saves_db_path, player_db_path, save_id, team):
        self.saves_db_path = str(saves_db_path)
        self.player_db_path = str(player_db_path)
        self.save_id = int(save_id)
        self.team = team
        self._ensure_market()

    def _save_connect(self):
        connection = sqlite3.connect(self.saves_db_path)
        connection.row_factory = sqlite3.Row
        for statement in SIMULATION_SCHEMA:
            connection.execute(statement)
        return connection

    def scouting_profile(self):
        ratings = dict(TEAM_SCOUTING_DEPARTMENTS.get(
            self.team, DEFAULT_SCOUTING_DEPARTMENT
        ))
        ratings["overall"] = round(
            (ratings["discovery"] + ratings["accuracy"] + ratings["network"]) / 3,
            1,
        )
        ratings["team"] = self.team
        return ratings

    def _ensure_market(self):
        now = datetime.now().isoformat(timespec="seconds")
        with self._save_connect() as connection:
            # 초기 고정 샘플 풀은 계약되지 않은 선수만 제거해 기존 세이브도
            # 생성 선수 시장으로 자연스럽게 마이그레이션한다.
            connection.execute(
                "DELETE FROM foreign_fa_market "
                "WHERE save_id=? AND (candidate_id LIKE 'IFA-%' OR candidate_id LIKE 'GEN-%') "
                "AND status='available'",
                (self.save_id,),
            )
            for player in _generated_market_pool(self.save_id):
                connection.execute(
                    """INSERT OR IGNORE INTO foreign_fa_market
                    (save_id,candidate_id,player_json,asking_salary,status,signed_team,updated_at)
                    VALUES (?,?,?,?, 'available','',?)""",
                    (self.save_id, player["id"], json.dumps(player, ensure_ascii=False),
                     player["asking_salary"], now),
                )

    def current_players(self):
        with sqlite3.connect(self.player_db_path) as player_db:
            player_db.row_factory = sqlite3.Row
            players = [dict(row) for row in player_db.execute(
                "SELECT * FROM players WHERE team=? AND is_foreign=1 ORDER BY position_group,name",
                (self.team,),
            ).fetchall()]
        with self._save_connect() as connection:
            decisions = {row["player_id"]: dict(row) for row in connection.execute(
                "SELECT * FROM foreign_contract_decisions WHERE save_id=? AND team=?",
                (self.save_id, self.team),
            ).fetchall()}
        for player in players:
            player["contract_decision"] = decisions.get(player["id"], {}).get("decision", "undecided")
            player["overall"] = round(float(overall_rating(player)), 1)
            if player.get("contract_currency") == "USD":
                current = int(player.get("contract_total") or player.get("contract_salary") or 0)
            else:
                current = round(int(player.get("salary") or 0) * 10000 / USD_KRW_REFERENCE_RATE)
            player["current_contract_usd"] = current
            player["asking_salary"] = max(100_000, int(round(current * 1.06 / 10_000) * 10_000))
        return players

    def _all_market_players(self):
        with self._save_connect() as connection:
            rows = connection.execute(
                "SELECT * FROM foreign_fa_market WHERE save_id=? ORDER BY status,asking_salary DESC",
                (self.save_id,),
            ).fetchall()
        result = []
        for row in rows:
            player = json.loads(row["player_json"])
            player.update({"status": row["status"], "signed_team": row["signed_team"]})
            player["overall"] = round(float(overall_rating(player)), 1)
            result.append(player)
        return result

    @staticmethod
    def _confidence_label(accuracy):
        if accuracy >= 18:
            return "매우 높음"
        if accuracy >= 15:
            return "높음"
        if accuracy >= 12:
            return "보통"
        return "낮음"

    def _scouting_order(self, candidate):
        digest = hashlib.sha256(
            f"{self.save_id}:{self.team}:{candidate['id']}:discover".encode()
        ).digest()
        return int.from_bytes(digest[:8], "big")

    def _scouted_overall(self, candidate, accuracy):
        actual = float(candidate["overall"])
        max_error = max(0, round((20 - accuracy) / 3))
        if not max_error:
            return actual, f"{actual:.1f}"
        digest = hashlib.sha256(
            f"{self.save_id}:{self.team}:{candidate['id']}:evaluate".encode()
        ).digest()
        offset = (int.from_bytes(digest[:2], "big") % (max_error * 2 + 1)) - max_error
        estimate = max(1.0, min(20.0, actual + offset))
        low = max(1.0, estimate - max_error)
        high = min(20.0, estimate + max_error)
        return estimate, f"{low:.1f}~{high:.1f}"

    def market_players(self):
        """현재 구단이 발견하고 평가한 범위의 선수만 반환한다."""
        profile = self.scouting_profile()
        players = self._all_market_players()
        signed = [player for player in players if player["status"] != "available"]
        available = [player for player in players if player["status"] == "available"]
        visible_count = min(
            len(available),
            5 + round(profile["discovery"] * 0.65 + profile["network"] * 0.20),
        )
        discovered = sorted(available, key=self._scouting_order)[:visible_count]
        result = []
        for actual in discovered + signed:
            player = dict(actual)
            player["is_foreign"] = True
            player["team"] = "외국인 FA"
            player["profile_complete"] = True
            player["source_note"] = player.get("summary", "게임 생성 외국인 후보")
            player["actual_overall"] = actual["overall"]
            estimate, display = self._scouted_overall(actual, profile["accuracy"])
            player["overall"] = round(estimate, 1)
            player["overall_display"] = display
            player["scout_confidence"] = self._confidence_label(profile["accuracy"])
            result.append(player)
        return sorted(
            result,
            key=lambda player: (
                player["status"] != "available",
                -float(player["overall"]),
                player["name"],
            ),
        )

    @staticmethod
    def _contract_cost(player):
        if player.get("contract_currency") == "USD":
            return int(player.get("contract_total") or player.get("contract_salary") or 0)
        return round(int(player.get("salary") or 0) * 10000 / USD_KRW_REFERENCE_RATE)

    def league_budget_rows(self):
        """공개 계약액과 KBO 팀당 400만 달러 한도로 구단별 가용액을 계산한다."""
        with sqlite3.connect(self.player_db_path) as connection:
            connection.row_factory = sqlite3.Row
            players = [dict(row) for row in connection.execute(
                "SELECT * FROM players WHERE is_foreign=1 AND team!='외국인 FA'"
            ).fetchall()]
        grouped = {team: [] for team in TEAM_SCOUTING_DEPARTMENTS}
        for player in players:
            if player.get("team") in grouped:
                grouped[player["team"]].append(player)
        result = []
        for team, roster in grouped.items():
            spent = sum(self._contract_cost(player) for player in roster)
            result.append({
                "team": team,
                "cap_usd": TEAM_FOREIGN_CAP_USD,
                "spent_usd": spent,
                "available_usd": max(0, TEAM_FOREIGN_CAP_USD - spent),
                "player_count": len(roster),
                "contracts": " · ".join(
                    f"{player['name']} ${self._contract_cost(player):,}" for player in roster
                ) or "등록 외국인 없음",
                "source": FOREIGN_CAP_SOURCE,
            })
        return sorted(result, key=lambda row: row["team"])

    def budget_summary(self):
        return next(
            row for row in self.league_budget_rows() if row["team"] == self.team
        )

    def negotiation_context(self, candidate_id):
        candidate_id = str(candidate_id)
        current = next(
            (player for player in self.current_players() if str(player["id"]) == candidate_id),
            None,
        )
        market = next(
            (player for player in self._all_market_players() if str(player["id"]) == candidate_id),
            None,
        )
        player = current or market
        if not player:
            return {"can_negotiate": False, "reason": "협상 대상을 찾을 수 없습니다."}
        budget = self.budget_summary()
        kind = "renew" if current else "sign"
        current_cost = self._contract_cost(current) if current else 0
        budget_room = budget["available_usd"] + current_cost
        individual_cap = TEAM_FOREIGN_CAP_USD if current else NEW_FOREIGN_CAP_USD
        max_total = max(0, min(individual_cap, budget_room))
        total, pitchers = self.slot_state()
        is_pitcher = player.get("position_group", player.get("pos")) == "P"
        reason = ""
        if current and current.get("contract_decision") == "renewed":
            reason = "이미 다음 시즌 재계약이 완료된 선수입니다."
        elif market and player.get("status") != "available":
            reason = f"이미 {player.get('signed_team') or '다른 구단'}과 계약했습니다."
        elif market and total >= FOREIGN_LIMIT:
            reason = "외국인 선수 3명 슬롯이 모두 차 있습니다. 먼저 방출 결정을 내려야 합니다."
        elif market and is_pitcher and pitchers >= FOREIGN_PITCHER_LIMIT:
            reason = "외국인 투수 2명 제한에 걸려 현재 협상할 수 없습니다."
        elif max_total < 100_000:
            reason = "외국인 선수 한도에서 사용할 수 있는 금액이 부족합니다."
        asking = int(player.get("asking_salary") or player.get("current_contract_usd") or 0)
        return {
            "can_negotiate": not reason,
            "reason": reason or "협상 가능",
            "kind": kind,
            "player": player,
            "asking_salary": asking,
            "max_total": max_total,
            "individual_cap": individual_cap,
            "team_cap": TEAM_FOREIGN_CAP_USD,
            "spent_usd": budget["spent_usd"],
            "available_usd": budget["available_usd"],
            "current_cost": current_cost,
        }

    def submit_negotiation_offer(self, candidate_id, offer, round_number=1):
        context = self.negotiation_context(candidate_id)
        if not context.get("can_negotiate"):
            return {"accepted": False, "closed": True, "message": context.get("reason", "협상 불가")}
        salary = max(0, int(offer.get("salary") or 0))
        bonus = max(0, int(offer.get("bonus") or 0))
        incentive = max(0, int(offer.get("incentive") or 0))
        transfer_fee = max(0, int(offer.get("transfer_fee") or 0))
        total = salary + bonus + incentive + transfer_fee
        if total > context["max_total"]:
            return {
                "accepted": False, "closed": False,
                "message": f"제안 총액 ${total:,}은 현재 제안 가능액 ${context['max_total']:,}을 초과합니다.",
                "interest": 15,
            }
        asking = context["asking_salary"]
        role = str(offer.get("role") or "")
        usage = str(offer.get("usage") or "")
        role_values = {
            "1선발": 70_000, "2선발": 55_000, "3선발": 42_000,
            "4~5선발": 28_000, "마무리": 55_000, "필승조": 35_000,
            "롱릴리프": 15_000, "중심타선(3~5번)": 55_000,
            "상위타선(1~2번)": 45_000, "하위타선(6~9번)": 25_000,
            "플래툰 기용": 12_000, "대타·수비 보강": 0,
        }
        usage_values = {
            "선발 30경기 이상": 35_000, "선발 25경기 이상": 25_000,
            "선발 20경기 이상": 15_000, "등판 기회 보장 없음": 0,
            "마무리 우선 기용": 30_000, "접전 8회 우선": 20_000,
            "60경기 이상 등판": 20_000, "상황별 기용": 0,
            "선발 출장 130경기 이상": 35_000, "선발 출장 110경기 이상": 25_000,
            "선발 출장 90경기 이상": 15_000, "상대 투수에 따른 기용": 5_000,
            "출장 보장 없음": 0,
        }
        role_value = role_values.get(role, 0)
        usage_value = usage_values.get(usage, 0)
        player_value = salary + bonus + round(incentive * 0.55) + role_value + usage_value
        seed = int.from_bytes(hashlib.sha256(
            f"{self.save_id}:{candidate_id}:negotiation".encode()
        ).digest()[:2], "big") % 9
        required_value = round(asking * (0.92 + seed / 100))
        interest = max(5, min(100, round(player_value / max(1, required_value) * 100)))
        if player_value < required_value:
            counter = min(context["max_total"], max(asking, required_value))
            patience = max(0, 4 - int(round_number))
            concerns = []
            guaranteed = salary + bonus
            if guaranteed < asking * 0.70:
                concerns.append("기본 연봉과 계약금으로 구성된 보장액이 낮습니다")
            if total and incentive > total * 0.35:
                concerns.append("인센티브 비중이 높아 실질 보장 가치가 부족합니다")
            if usage in ("출장 보장 없음", "등판 기회 보장 없음", "상황별 기용"):
                concerns.append("구체적인 출장·등판 기회가 보장되지 않았습니다")
            concern_text = " ".join(concerns[:2]) or "금액 조건을 조금 더 높여야 합니다"
            return {
                "accepted": False, "closed": patience == 0, "interest": interest,
                "counter_total": counter,
                "message": (
                    f"'{role}' · '{usage}' 기용안은 확인했습니다. {concern_text} "
                    f"총액 ${counter:,} 수준이면 협상을 진전시킬 수 있습니다. "
                    f"남은 협상 기회 {patience}회."
                ),
            }
        if context["kind"] == "renew":
            self._complete_renewal(
                context["player"], salary, bonus, incentive, transfer_fee, role, usage
            )
            message = (
                f"{context['player']['name']}과 총액 ${total:,}에 재계약했습니다.\n"
                f"기용 합의: {role} · {usage}"
            )
        else:
            self._complete_signing(
                context["player"], salary, bonus, incentive, transfer_fee, role, usage
            )
            message = (
                f"{context['player']['name']}과 총액 ${total:,}에 계약했습니다.\n"
                f"기용 합의: {role} · {usage}"
            )
        return {"accepted": True, "closed": True, "interest": 100, "message": message}

    def _complete_renewal(
        self, player, salary, bonus, incentive, transfer_fee=0, role="", usage=""
    ):
        total = salary + bonus + incentive + transfer_fee
        usage_note = f"{role} · {usage}".strip(" ·")
        with sqlite3.connect(self.player_db_path) as connection:
            salary_10k = round((salary + bonus) * USD_KRW_REFERENCE_RATE / 10000)
            connection.execute(
                """UPDATE players SET salary=?,role=?,contract_total=?,
                contract_salary=?,contract_bonus=?,contract_option=?,contract_transfer_fee=?,
                contract_currency='USD',contract_start_date='2026-02-01',
                contract_end_date='2026-11-30',contract_type='외국인 선수 단년계약',
                contract_note=?
                WHERE id=?""",
                (
                    salary_10k, usage_note, total, salary, bonus, incentive, transfer_fee,
                    f"게임 내 외국인 계약 · 기용 합의: {usage_note}", player["id"],
                ),
            )
        self._record_decision(player, "renewed", total)

    def _complete_signing(
        self, candidate, salary, bonus, incentive, transfer_fee=0, role="", usage=""
    ):
        total = salary + bonus + incentive + transfer_fee
        usage_note = f"{role} · {usage}".strip(" ·")
        player_id = self._insert_candidate(candidate, total)
        with sqlite3.connect(self.player_db_path) as connection:
            salary_10k = round((salary + bonus) * USD_KRW_REFERENCE_RATE / 10000)
            connection.execute(
                """UPDATE players SET salary=?,role=?,contract_total=?,contract_salary=?,
                contract_bonus=?,contract_option=?,contract_transfer_fee=?,contract_note=?
                WHERE id=?""",
                (
                    salary_10k, usage_note, total, salary, bonus, incentive, transfer_fee,
                    f"게임 내 외국인 계약 · 기용 합의: {usage_note}", player_id,
                ),
            )
        with self._save_connect() as connection:
            connection.execute(
                "UPDATE foreign_fa_market SET status='signed',signed_team=?,updated_at=? "
                "WHERE save_id=? AND candidate_id=?",
                (self.team, datetime.now().isoformat(timespec="seconds"), self.save_id, candidate["id"]),
            )
            connection.execute(
                """INSERT OR IGNORE INTO player_simulation_states
                (save_id,player_id,team,condition,fatigue,training_points,injury_days,
                 match_sharpness,morale,injury_risk,squad_group,injury_type,last_updated)
                VALUES (?,?,?,85,0,0,0,55,78,5,'2군','',?)""",
                (self.save_id, player_id, self.team, datetime.now().isoformat(timespec="seconds")),
            )

    def slot_state(self):
        active = [p for p in self.current_players() if p["contract_decision"] != "released"]
        return len(active), sum((p.get("position_group") or p.get("pos")) == "P" for p in active)

    def renew(self, player_id, offer_salary):
        offer_salary = int(offer_salary)
        player = next((p for p in self.current_players() if p["id"] == player_id), None)
        if not player:
            return False, "선수를 찾을 수 없습니다."
        demand = int(player["asking_salary"])
        chance = int.from_bytes(hashlib.sha256(
            f"{self.save_id}:{player_id}:renew".encode()
        ).digest()[:2], "big") % 16
        accepted = offer_salary >= int(demand * (0.88 + chance / 100))
        if not accepted:
            return False, f"에이전트가 총액 ${demand:,} 수준의 보장액을 요구했습니다."
        with sqlite3.connect(self.player_db_path) as connection:
            salary_10k = round(offer_salary * USD_KRW_REFERENCE_RATE / 10000)
            connection.execute(
                """UPDATE players SET salary=?,role='재계약',contract_total=?,
                contract_salary=?,contract_currency='USD',contract_start_date='2026-02-01',
                contract_end_date='2026-11-30',contract_type='외국인 선수 단년계약'
                WHERE id=?""",
                (salary_10k, offer_salary, offer_salary, player_id),
            )
        self._record_decision(player, "renewed", offer_salary)
        return True, f"{player['name']}과 2026시즌 총액 ${offer_salary:,}에 재계약했습니다."

    def release(self, player_id):
        player = next((p for p in self.current_players() if p["id"] == player_id), None)
        if not player:
            return False, "선수를 찾을 수 없습니다."
        with sqlite3.connect(self.player_db_path) as connection:
            connection.execute(
                "UPDATE players SET team='외국인 FA',status=0,lineup_pos=0,role='방출' WHERE id=?",
                (player_id,),
            )
        with self._save_connect() as connection:
            connection.execute(
                "UPDATE player_simulation_states SET team='외국인 FA',squad_group='FA' "
                "WHERE save_id=? AND player_id=?",
                (self.save_id, player_id),
            )
        self._record_decision(player, "released", 0)
        return True, f"{player['name']}을 방출해 외국인 선수 슬롯을 비웠습니다."

    def _record_decision(self, player, decision, offer):
        with self._save_connect() as connection:
            connection.execute(
                """INSERT INTO foreign_contract_decisions
                (save_id,player_id,team,decision,previous_salary,offer_salary,decided_at)
                VALUES (?,?,?,?,?,?,?)
                ON CONFLICT(save_id,player_id) DO UPDATE SET
                decision=excluded.decision,offer_salary=excluded.offer_salary,
                decided_at=excluded.decided_at""",
                (self.save_id, player["id"], self.team, decision,
                 int(player.get("current_contract_usd") or player.get("salary") or 0),
                 int(offer),
                 datetime.now().isoformat(timespec="seconds")),
            )

    def sign(self, candidate_id, offer_salary):
        candidate = next(
            (p for p in self._all_market_players() if p["id"] == candidate_id), None
        )
        if not candidate or candidate["status"] != "available":
            return False, "이미 시장에서 계약된 선수입니다."
        total, pitchers = self.slot_state()
        is_pitcher = candidate.get("position_group", candidate["pos"]) == "P"
        if total >= FOREIGN_LIMIT:
            return False, "외국인 선수 3명 슬롯이 모두 차 있습니다."
        if is_pitcher and pitchers >= FOREIGN_PITCHER_LIMIT:
            return False, "외국인 투수는 최대 2명까지 보유할 수 있습니다."
        offer_salary = min(int(offer_salary), NEW_FOREIGN_CAP_USD)
        asking = int(candidate["asking_salary"])
        seed = int.from_bytes(hashlib.sha256(
            f"{self.save_id}:{candidate_id}:sign".encode()
        ).digest()[:2], "big") % 13
        if offer_salary < int(asking * (0.90 + seed / 100)):
            return False, f"선수 측이 요구액 ${asking:,}에 가까운 제안을 원합니다."
        player_id = self._insert_candidate(candidate, offer_salary)
        with self._save_connect() as connection:
            connection.execute(
                "UPDATE foreign_fa_market SET status='signed',signed_team=?,updated_at=? "
                "WHERE save_id=? AND candidate_id=?",
                (self.team, datetime.now().isoformat(timespec="seconds"),
                 self.save_id, candidate_id),
            )
            connection.execute(
                """INSERT OR IGNORE INTO player_simulation_states
                (save_id,player_id,team,condition,fatigue,training_points,injury_days,
                 match_sharpness,morale,injury_risk,squad_group,injury_type,last_updated)
                VALUES (?,?,?,85,0,0,0,55,78,5,'2군','',?)""",
                (self.save_id, player_id, self.team,
                 datetime.now().isoformat(timespec="seconds")),
            )
        return True, f"{candidate['name']}과 2026시즌 총액 ${offer_salary:,}에 계약했습니다."

    def _insert_candidate(self, p, salary):
        is_pitcher = p.get("position_group", p["pos"]) == "P"
        salary_10k = round(salary * USD_KRW_REFERENCE_RATE / 10000)
        with sqlite3.connect(self.player_db_path) as connection:
            cursor = connection.execute(
                """INSERT INTO players
                (player_uid,kbo_player_id,team,name,pos,age,bats_throws,career,
                 con,pow,eye,def,contact,power,plate_discipline,fielding_range,
                 throwing_power,speed,pitcher_velocity,pitcher_stuff,pitcher_command,
                 pitcher_movement,pitcher_stamina,pitcher_pitchability,status,
                 lineup_pos,role,salary,position_group,is_foreign,profile_complete,source_note,
                 contract_start_date,contract_end_date,contract_type,contract_years,
                 contract_total,contract_currency,contract_salary,contract_note)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (p["id"], None, self.team, p["name"], p.get("primary_position", p["pos"]), p["age"],
                 p["bats_throws"], f"{p['nationality']} 외국인 FA",
                 5 if is_pitcher else p.get("contact", 10),
                 5 if is_pitcher else p.get("power", 10),
                 5 if is_pitcher else p.get("plate_discipline", 10),
                 10, p.get("contact"), p.get("power"), p.get("plate_discipline"),
                 p.get("fielding_range"), p.get("throwing_power"), p.get("speed"),
                 p.get("pitcher_velocity"), p.get("pitcher_stuff"),
                 p.get("pitcher_command"), p.get("pitcher_movement"),
                 p.get("pitcher_stamina"), p.get("pitcher_pitchability"),
                 0, 0, "신규 외국인", salary_10k, p.get("position_group", p["pos"]),
                 1, 1, p["summary"], "2026-02-01", p["contract_end_date"],
                 "외국인 선수 단년계약", 1, salary, "USD", salary,
                 "게임 생성 외국인 선수 계약"),
            )
            return cursor.lastrowid
