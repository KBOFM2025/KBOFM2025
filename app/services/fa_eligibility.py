"""2025시즌 종료 기준 KBO FA 자격 판정 데이터와 표시용 보고서."""

import csv
import re
from functools import lru_cache

from database.contract_data import MULTI_YEAR_CONTRACT_ENDS, MULTI_YEAR_OPTION_TERMS
from database.paths import DATA_DIR


FA_RULE_SOURCE = (
    "https://6ptotvmi5753.edge.naverncp.com/KBO_FILE/ebook/pdf/"
    "2025_%EC%95%BC%EA%B5%AC%EA%B7%9C%EC%95%BD.pdf"
)
FA_2026_SOURCE = "https://www.koreabaseball.com/MediaNews/Notice/View.aspx?bdSe=11753"
FA_SNAPSHOT = "2025-11-05"
FA_BASE_SEASON = 2025
REGISTRATION_DATA_SNAPSHOT = "2026-08-03"
CAREER_HISTORY_PATH = DATA_DIR / "source" / "kbo_player_career_history.csv"
REGISTRATION_DAYS_PATH = DATA_DIR / "source" / "kbo_player_registration_days.csv"


def _entry(kind, seasons, grade, note="", birth_date=""):
    return {
        "kind": kind, "recognized_seasons": seasons,
        "grade": grade, "note": note, "birth_date": birth_date,
    }


# KBO 공식 '2026년 FA 자격 선수 명단'. 동명이인은 구단과 함께 식별한다.
FA_2026_ELIGIBLE = {
    ("LG 트윈스", "심창민"): _entry("자격유지", 8, "C"),
    ("LG 트윈스", "김현수"): _entry("재자격", 4, "C", "3번째 FA"),
    ("LG 트윈스", "박해민"): _entry("재자격", 4, "B", "2번째 FA"),
    ("한화 이글스", "김범수"): _entry("신규", 8, "B"),
    ("한화 이글스", "이재원"): _entry("자격유지(재자격)", 6, "B", "2번째 FA"),
    ("한화 이글스", "손아섭"): _entry("재자격", 4, "C", "3번째 FA"),
    ("SSG 랜더스", "서진용"): _entry("자격유지", 8, "A"),
    ("삼성 라이온즈", "김태훈"): _entry("신규", 8, "A", birth_date="1992-03-02"),
    ("삼성 라이온즈", "이승현"): _entry("신규", 8, "B", birth_date="1991-11-20"),
    ("삼성 라이온즈", "강민호"): _entry("재자격", 4, "C", "4번째 FA"),
    ("삼성 라이온즈", "박병호"): _entry("재자격", 4, "C", "2번째 FA · 첫 FA C등급"),
    ("NC 다이노스", "최원준"): _entry("신규", 8, "A", birth_date="1997-03-23"),
    ("KT 위즈", "강백호"): _entry("신규", 8, "A"),
    ("KT 위즈", "장성우"): _entry("재자격", 4, "B", "2번째 FA"),
    ("KT 위즈", "오재일"): _entry("자격유지(재자격)", 4, "B", "2번째 FA"),
    ("KT 위즈", "황재균"): _entry("재자격", 4, "C", "3번째 FA"),
    ("롯데 자이언츠", "김상수"): _entry("재자격", 4, "B", "2번째 FA"),
    ("롯데 자이언츠", "진해수"): _entry("자격유지(재자격)", 4, "B", "2번째 FA"),
    ("롯데 자이언츠", "박승욱"): _entry("신규", 8, "B"),
    ("KIA 타이거즈", "양현종"): _entry("재자격", 4, "C", "3번째 FA"),
    ("KIA 타이거즈", "이준영"): _entry("신규", 7, "B", "4년제 대학 선수"),
    ("KIA 타이거즈", "조상우"): _entry("신규", 8, "A"),
    ("KIA 타이거즈", "한승택"): _entry("신규", 8, "C"),
    ("KIA 타이거즈", "박찬호"): _entry("신규", 8, "A"),
    ("KIA 타이거즈", "최형우"): _entry("재자격", 5, "C", "3번째 FA"),
    ("두산 베어스", "이영하"): _entry("신규", 8, "B"),
    ("두산 베어스", "최원준"): _entry(
        "신규", 7, "A", "4년제 대학 선수", birth_date="1994-12-21"
    ),
    ("두산 베어스", "김재환"): _entry("재자격", 4, "B", "2번째 FA"),
    ("두산 베어스", "조수행"): _entry("신규", 7, "B", "4년제 대학 선수"),
    ("키움 히어로즈", "이용규"): _entry("자격유지(재자격)", 4, "C", "3번째 FA"),
}


FA_2026_DEFERRED = {
    ("한화 이글스", "최재훈"): "1989-08-27",
    ("SSG 랜더스", "김광현"): "1988-07-22",
    ("SSG 랜더스", "문승원"): "1989-11-28",
    ("SSG 랜더스", "박종훈"): "1991-08-13",
    ("SSG 랜더스", "김성현"): "1987-03-09",
    ("SSG 랜더스", "한유섬"): "1989-08-09",
    ("삼성 라이온즈", "구자욱"): "1993-02-12",
    ("NC 다이노스", "박건우"): "1990-09-08",
    ("KT 위즈", "고영표"): "1991-09-16",
    ("롯데 자이언츠", "박세웅"): "1995-11-30",
    ("KIA 타이거즈", "김태군"): "1989-12-30",
    ("KIA 타이거즈", "나성범"): "1989-10-03",
    ("두산 베어스", "정수빈"): "1990-10-07",
    ("키움 히어로즈", "최주환"): "1988-02-28",
}


def _college_player(career):
    career = str(career or "")
    return bool(re.search(r"대학교|\(대\)|[가-힣]{2,}대(?:-|$)", career))


def _eligible_entry(player):
    """현재 팀 우선, 생년월일 보조로 트레이드와 동명이인을 모두 처리한다."""
    team = str(player.get("team") or "")
    name = str(player.get("name") or "")
    birth_date = str(player.get("birth_date") or "")
    exact = FA_2026_ELIGIBLE.get((team, name))
    if exact and (not exact.get("birth_date") or exact["birth_date"] == birth_date):
        return exact
    candidates = [
        data for (_original_team, original_name), data in FA_2026_ELIGIBLE.items()
        if original_name == name
        and (not data.get("birth_date") or data["birth_date"] == birth_date)
    ]
    return candidates[0] if len(candidates) == 1 else None


def _is_deferred(player):
    team = str(player.get("team") or "")
    name = str(player.get("name") or "")
    birth_date = str(player.get("birth_date") or "")
    if FA_2026_DEFERRED.get((team, name)) == birth_date:
        return True
    return any(
        deferred_name == name and deferred_birth == birth_date
        for (_team, deferred_name), deferred_birth in FA_2026_DEFERRED.items()
    )


@lru_cache(maxsize=1)
def _career_seasons():
    """KBO 기록이 확인되는 시즌을 읽는다. FA 인정 등록일수와는 구분한다."""
    seasons = {}
    if not CAREER_HISTORY_PATH.exists():
        return seasons
    with CAREER_HISTORY_PATH.open("r", encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            player_id = str(row.get("kbo_player_id") or "").strip()
            season = str(row.get("season") or "").strip()
            if player_id and season.isdigit() and int(season) <= 2025:
                seasons.setdefault(player_id, set()).add(int(season))
    return {player_id: tuple(sorted(values)) for player_id, values in seasons.items()}


def _record_seasons(player):
    return list(_career_seasons().get(str(player.get("kbo_player_id") or "").strip(), ()))


@lru_cache(maxsize=1)
def _registration_days():
    histories = {}
    if not REGISTRATION_DAYS_PATH.exists():
        return histories
    with REGISTRATION_DAYS_PATH.open("r", encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            player_id = str(row.get("kbo_player_id") or "").strip()
            if not player_id:
                continue
            registration = int(row.get("registration_days") or 0)
            national = int(row.get("national_team_days") or 0)
            histories.setdefault(player_id, []).append({
                "team": str(row.get("team") or ""),
                "season": int(row.get("season") or 0),
                "registration_days": registration,
                "national_team": str(row.get("national_team") or ""),
                "national_team_days": national,
                "effective_days": registration + national,
                "source_url": str(row.get("source_url") or ""),
            })
    return {
        player_id: tuple(sorted(rows, key=lambda item: item["season"]))
        for player_id, rows in histories.items()
    }


def _service_day_details(player, required):
    player_id = str(player.get("kbo_player_id") or "").strip()
    rows = [dict(row) for row in _registration_days().get(player_id, ())]
    full_seasons = 0
    partial_pool = 0
    for row in rows:
        if row["effective_days"] >= 145:
            row["credit_status"] = "1시즌 인정"
            full_seasons += 1
        else:
            row["credit_status"] = "미달일수 합산"
            partial_pool += row["effective_days"]
    combined_seasons, partial_remainder = divmod(partial_pool, 145)
    credited_seasons = full_seasons + combined_seasons
    credited_days = credited_seasons * 145 + partial_remainder
    target_days = required * 145 if required else None
    remaining_days = max(0, target_days - credited_days) if target_days is not None else None
    return {
        "registration_rows": rows,
        "raw_registration_days": sum(row["registration_days"] for row in rows),
        "national_team_days": sum(row["national_team_days"] for row in rows),
        "effective_history_days": sum(row["effective_days"] for row in rows),
        "full_service_seasons": full_seasons,
        "combined_service_seasons": combined_seasons,
        "credited_seasons_calculated": credited_seasons,
        "partial_remainder_days": partial_remainder,
        "credited_days": credited_days,
        "target_days": target_days,
        "remaining_days": remaining_days,
    }


def _common_details(player, required, recognized=None, shortage=None):
    seasons = _record_seasons(player)
    details = {
        "required_seasons": required,
        "recognized_seasons": recognized,
        "shortage_seasons": shortage,
        "record_seasons": seasons,
        "record_season_count": len(seasons),
        "season_rule": "현역선수 등록일수 145일 이상이 원칙적으로 1시즌 인정",
        "registration_data_snapshot": REGISTRATION_DATA_SNAPSHOT,
    }
    details.update(_service_day_details(player, required))
    return details


def _contract_state(player, qualification_met=False, projected_season=None):
    """FA 등록일수와 별도로 현재 계약이 권리 행사를 막는지 계산한다."""
    player_key = (str(player.get("team") or ""), str(player.get("name") or ""))
    published_contract = MULTI_YEAR_CONTRACT_ENDS.get(player_key)
    option_term = MULTI_YEAR_OPTION_TERMS.get(player_key)
    contract_type = str(player.get("contract_type") or "연 단위 선수계약")
    contract_start = str(player.get("contract_start_date") or "")
    contract_end = str(player.get("contract_end_date") or "2025-11-30")
    if published_contract:
        contract_end, contract_type = published_contract
    start_year_text = contract_start[:4]
    end_year_text = contract_end[:4]
    start_year = int(start_year_text) if start_year_text.isdigit() else FA_BASE_SEASON
    end_year = int(end_year_text) if end_year_text.isdigit() else FA_BASE_SEASON
    guaranteed_end = option_term[0] if option_term else contract_end
    guaranteed_year_text = guaranteed_end[:4]
    guaranteed_end_year = (
        int(guaranteed_year_text) if guaranteed_year_text.isdigit() else end_year
    )
    recorded_years = int(player.get("contract_years") or 0)
    inferred_years = max(1, end_year - start_year + 1)
    contract_years = max(recorded_years, inferred_years)
    is_multi_year = (
        end_year > FA_BASE_SEASON
        and (
            contract_years > 1 or "다년" in contract_type or "+" in contract_type
            or bool(re.search(r"\d+(?:\+\d+)*년", contract_type))
        )
    )
    is_non_fa_multi_year = is_multi_year and contract_type.startswith("비FA")
    official_deferred = _is_deferred(player)
    blocks_application = bool(is_multi_year and (qualification_met or official_deferred))
    remaining_contract_seasons = max(0, guaranteed_end_year - FA_BASE_SEASON)
    option_seasons = max(0, end_year - guaranteed_end_year)

    qualification_season = projected_season
    if qualification_met:
        qualification_season = FA_BASE_SEASON
    earliest_market_year = None
    option_market_year = None
    if qualification_season is not None:
        gate_season = max(
            int(qualification_season), guaranteed_end_year if is_multi_year else FA_BASE_SEASON
        )
        earliest_market_year = gate_season + 1
        if option_term:
            option_market_year = max(int(qualification_season), end_year) + 1

    if official_deferred:
        contract_status = "FA 계약 유보선수"
        if option_term:
            contract_detail = (
                f"FA 자격은 충족했지만 보장 계약이 {guaranteed_end}까지 유효합니다. "
                f"연장 옵션이 발동되면 최대 {contract_end}까지 권리 행사가 유보됩니다."
            )
        else:
            contract_detail = (
                f"FA 자격은 충족했지만 {contract_type}이 {contract_end}까지 유효합니다. "
                f"{end_year}시즌 종료 후 FA 승인 신청이 가능합니다."
            )
    elif is_non_fa_multi_year:
        contract_status = "비FA 다년계약 중"
        if option_term:
            contract_detail = (
                f"등록일수는 계속 인정됩니다. 보장 계약은 {guaranteed_end}까지이며 "
                f"연장 옵션 발동 시 최대 {contract_end}까지 FA 권리 행사가 유보됩니다."
            )
        else:
            contract_detail = (
                f"등록일수는 계약 중에도 계속 인정됩니다. 다만 자격을 먼저 채우더라도 "
                f"계약이 끝나는 {end_year}시즌까지 FA 권리 행사는 유보됩니다."
            )
    elif is_multi_year:
        contract_status = "FA 다년계약 중"
        contract_detail = (
            f"재취득 등록일수는 계약 중에도 누적됩니다. "
            + (
                f"보장 계약은 {guaranteed_end}까지이고 옵션 발동 시 최대 {contract_end}까지 연장됩니다."
                if option_term else f"현재 계약은 {contract_end}까지 유효합니다."
            )
        )
    else:
        contract_status = "시즌 단위 계약"
        contract_detail = "다년계약에 따른 별도 FA 승인 제한이 없습니다."

    return {
        "contract_type": contract_type,
        "contract_start_date": contract_start or "미등록",
        "contract_end_date": contract_end,
        "contract_start_year": start_year,
        "contract_end_year": end_year,
        "guaranteed_contract_end_date": guaranteed_end,
        "guaranteed_contract_end_year": guaranteed_end_year,
        "contract_years": contract_years,
        "is_multi_year_contract": is_multi_year,
        "is_non_fa_multi_year": is_non_fa_multi_year,
        "official_contract_deferred": official_deferred,
        "contract_blocks_fa_application": blocks_application,
        "remaining_contract_seasons": remaining_contract_seasons,
        "option_contract_seasons": option_seasons,
        "has_contract_option_years": bool(option_term),
        "contract_status": contract_status,
        "contract_detail": contract_detail,
        "projected_qualification_season": qualification_season,
        "earliest_fa_market_year": earliest_market_year,
        "option_fa_market_year": option_market_year,
    }


def _finish_report(player, report, qualification_met=False, projected_season=None):
    report.update(_contract_state(player, qualification_met, projected_season))
    report["qualification_met"] = bool(qualification_met)
    if report["official_contract_deferred"]:
        report["can_apply_now"] = False
        if report["has_contract_option_years"]:
            report["availability_label"] = (
                f"빠르면 {report['earliest_fa_market_year']} FA · "
                f"옵션 발동 시 {report['option_fa_market_year']} FA"
            )
        else:
            report["availability_label"] = (
                f"{report['contract_end_year']}시즌 종료 후 · {report['earliest_fa_market_year']} FA 시장"
            )
    elif qualification_met:
        report["can_apply_now"] = not report["contract_blocks_fa_application"]
        if report["option_fa_market_year"]:
            report["availability_label"] = (
                f"빠르면 {report['earliest_fa_market_year']} FA · "
                f"옵션 발동 시 {report['option_fa_market_year']} FA"
            )
        else:
            report["availability_label"] = (
                f"{report['earliest_fa_market_year']} FA 시장"
                if report["earliest_fa_market_year"] else "FA 승인 신청 가능"
            )
    elif report["earliest_fa_market_year"]:
        prefix = "계약·등록일수 기준 빠르면" if report["is_multi_year_contract"] else "등록일수 기준 빠르면"
        report["can_apply_now"] = False
        report["availability_label"] = f"{prefix} {report['earliest_fa_market_year']} FA 시장"
        if report["option_fa_market_year"]:
            report["availability_label"] += f" · 옵션 발동 시 {report['option_fa_market_year']} FA"
    else:
        report["can_apply_now"] = False
        report["availability_label"] = "현재 산정 불가"
    return report


def fa_eligibility_report(player):
    """선수 상세 화면에서 사용할 현재 FA 자격 판정을 반환한다."""
    team = str(player.get("team") or "")
    name = str(player.get("name") or "")
    source_tooltip = (
        f"기준일 {FA_SNAPSHOT}\n"
        "KBO 규약 제162~165조 및 2026년 FA 자격 선수 공시 기준"
    )

    if player.get("is_foreign") or team == "외국인 FA":
        return _finish_report(player, {
            "status": "적용 제외", "progress": "외국인 선수 별도 계약 제도",
            "grade": "-", "note": "KBO 국내 선수 FA 자격 산정 대상이 아닙니다.",
            "tone": "muted", "source": FA_RULE_SOURCE, "tooltip": source_tooltip,
            "shortage_title": "국내 선수 FA 규정 적용 대상 아님",
            "shortage_detail": "외국인 선수는 보류권과 외국인선수 계약 규정을 적용합니다.",
            "qualification_type": "외국인 선수",
            **_common_details(player, None),
        })

    data = _eligible_entry(player)
    if data:
        required = 4 if "재자격" in data["kind"] else data["recognized_seasons"]
        report = {
            "status": f"자격 충족 · {data['kind']}",
            "progress": f"인정 {data['recognized_seasons']}시즌 / 기준 {required}시즌",
            "grade": f"{data['grade']}등급",
            "note": data["note"] or "2026년 FA 자격 선수 공식 공시",
            "tone": "positive", "source": FA_2026_SOURCE, "tooltip": source_tooltip,
            "shortage_title": "부족 요건 없음",
            "shortage_detail": "KBO가 2026년 FA 자격 선수로 공식 공시했습니다.",
            "qualification_type": data["kind"],
        }
        report.update(_common_details(player, required, data["recognized_seasons"], 0))
        report["remaining_days"] = 0
        report["calculation_note"] = "공식 FA 자격 공시가 등록일수 환산 계산보다 우선합니다."
        return _finish_report(player, report, qualification_met=True, projected_season=FA_BASE_SEASON)

    if _is_deferred(player):
        contract_end = player.get("contract_end_date") or "계약 종료 시점"
        report = {
            "status": "자격 충족 · 계약 유보", "progress": f"다년계약 종료 {contract_end}",
            "grade": "유보",
            "note": "요건은 충족했지만 계약 종료 연도까지 FA 승인 신청이 불가능합니다.",
            "tone": "warning", "source": FA_2026_SOURCE, "tooltip": source_tooltip,
            "shortage_title": "인정 시즌은 충족 · 계약 기간만 남음",
            "shortage_detail": f"현재 다년계약이 {contract_end}까지 유효해 그 전에는 FA 승인 신청을 할 수 없습니다.",
            "qualification_type": "계약 유보선수",
        }
        report.update(_common_details(player, None, None, 0))
        report["remaining_days"] = 0
        report["calculation_note"] = "시즌 요건은 공식 충족했으며 계약 종료만 기다립니다."
        return _finish_report(player, report, qualification_met=True, projected_season=FA_BASE_SEASON)

    contract_type = str(player.get("contract_type") or "")
    reacquisition = contract_type.startswith("FA")
    college = _college_player(player.get("career"))
    required = 4 if reacquisition else 7 if college else 8
    rule_name = "FA 재취득" if reacquisition else "4년제 대학 선수" if college else "일반 선수"
    seasons = _record_seasons(player)
    day_details = _service_day_details(player, required)
    reference_gap = max(0, required - len(seasons))
    remaining_days = day_details["remaining_days"]
    shortage_title = f"FA 환산 기준까지 {remaining_days:,}일 부족"
    shortage_detail = (
        f"KBO 공개 등록일수와 대표팀 포인트를 반영하면 인정 환산 {day_details['credited_days']:,}일입니다. "
        f"{required}시즌 환산 기준 {day_details['target_days']:,}일까지 {remaining_days:,}일이 남았습니다."
    )
    calculation_note = "KBO 공개 시즌별 등록일수 기준 계산"
    if reacquisition:
        remaining_days = None
        shortage_title = "재취득 기산점 확인 필요"
        shortage_detail = (
            f"통산 등록일은 {day_details['raw_registration_days']:,}일로 확인되지만, FA 재취득은 직전 FA 행사 후부터 "
            "4개 인정 시즌을 다시 계산합니다. 현재 계약 데이터에 그 기산점이 없어 통산 일수를 재취득 잔여일로 사용하지 않습니다."
        )
        calculation_note = "통산 등록일수만 표시 · 재취득 잔여일은 기산점 미확인"
    elif day_details["credited_seasons_calculated"] >= required:
        remaining_days = None
        shortage_title = "통산 기록은 기준 이상 · 과거 FA 이력 확인 필요"
        shortage_detail = (
            f"공개 기록상 통산 등록 {day_details['raw_registration_days']:,}일이지만 2026년 신규 FA 공시 대상은 아닙니다. "
            "과거 FA 행사 또는 별도 인정 이력이 있을 수 있어 현재 재취득 잔여일을 임의 확정하지 않습니다."
        )
        calculation_note = "통산 등록일수는 정확 · 현재 FA 기산점은 미확인"
    report = {
        "status": "재취득 진행 중" if reacquisition else "현재 자격 미충족",
        "progress": f"{rule_name} 기준 {required}시즌", "grade": "미산정",
        "note": (
            "2026년 FA 자격자·계약 유보선수 공식 명단에 포함되지 않았습니다. "
            "등록일수는 KBO 공개 기록으로 계산하며 최종 자격 판정은 KBO 공시를 우선합니다."
        ),
        "tone": "muted", "source": FA_2026_SOURCE,
        "tooltip": source_tooltip + "\n1시즌은 원칙적으로 현역선수 등록일수 145일 이상",
        "shortage_title": shortage_title,
        "shortage_detail": shortage_detail,
        "qualification_type": rule_name,
        "calculation_note": calculation_note,
    }
    report.update(_common_details(player, required, None, None))
    report["remaining_days"] = remaining_days
    report["reference_gap"] = reference_gap
    projected_season = None
    if remaining_days is not None:
        seasons_left = max(0, (int(remaining_days) + 144) // 145)
        projected_season = FA_BASE_SEASON + seasons_left
    return _finish_report(player, report, projected_season=projected_season)
