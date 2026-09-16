"""KBO 경쟁균형세(샐러리캡) 계산 규칙."""

from __future__ import annotations


CAP_BY_YEAR_10K = {
    2025: 1_371_165,  # 137억 1,165만원
    2026: 1_439_723,  # 143억 9,723만원
    2027: 1_511_709,
    2028: 1_587_294,
}


def cap_limit(year):
    year = int(year or 2026)
    if year in CAP_BY_YEAR_10K:
        return CAP_BY_YEAR_10K[year]
    latest = max(CAP_BY_YEAR_10K)
    return int(round(CAP_BY_YEAR_10K[latest] * (1.05 ** (year - latest))))


def salary_cap_summary(connection, team, year=2026, proposed_salary=0, schema="main"):
    """외국인·신인을 제외한 연봉 상위 40명의 경쟁균형세 총액을 반환한다."""
    table = "playerdb.players" if schema == "playerdb" else "players"
    rows = connection.execute(
        f"""
        SELECT id, name, salary, contract_bonus, contract_years, contract_currency
        FROM {table}
        WHERE team=? AND COALESCE(is_foreign, 0)=0 AND COALESCE(is_rookie, 0)=0
        ORDER BY COALESCE(salary, 0) DESC
        LIMIT 40
        """,
        (team,),
    ).fetchall()
    salaries = []
    for row in rows:
        charge = max(0, int(row["salary"] or 0))
        if str(row["contract_currency"] or "KRW") != "USD":
            charge += int(round(
                int(row["contract_bonus"] or 0)
                / 10_000 / max(1, int(row["contract_years"] or 1))
            ))
        salaries.append(charge)
    current = sum(salaries)
    proposed = max(0, int(proposed_salary or 0))
    projected_salaries = sorted(salaries + ([proposed] if proposed else []), reverse=True)[:40]
    projected = sum(projected_salaries)
    limit = cap_limit(year)
    excess = max(0, projected - limit)
    return {
        "year": int(year),
        "limit": limit,
        "current": current,
        "room": limit - current,
        "proposed_salary": proposed,
        "projected": projected,
        "projected_room": limit - projected,
        "excess": excess,
        "first_excess_levy": int(round(excess * 0.30)),
        "counted_players": min(40, len(projected_salaries)),
    }


def salary_cap_from_players(players, team, year=2026, proposed_salary=0):
    eligible = [
        player for player in players
        if player.get("team") == team
        and not int(player.get("is_foreign") or 0)
        and not int(player.get("is_rookie") or 0)
    ]
    salaries = []
    for player in eligible:
        charge = max(0, int(player.get("salary") or 0))
        if str(player.get("contract_currency") or "KRW") != "USD":
            charge += int(round(
                int(player.get("contract_bonus") or 0)
                / 10_000 / max(1, int(player.get("contract_years") or 1))
            ))
        salaries.append(charge)
    salaries = sorted(salaries, reverse=True)[:40]
    current = sum(salaries)
    proposed = max(0, int(proposed_salary or 0))
    projected = sum(sorted(salaries + ([proposed] if proposed else []), reverse=True)[:40])
    limit = cap_limit(year)
    excess = max(0, projected - limit)
    return {
        "year": int(year), "limit": limit, "current": current,
        "room": limit - current, "proposed_salary": proposed,
        "projected": projected, "projected_room": limit - projected,
        "excess": excess, "first_excess_levy": int(round(excess * 0.30)),
        "counted_players": min(40, len(salaries) + (1 if proposed else 0)),
    }


def money_krw_10k(value):
    value = int(value or 0)
    return f"{value // 10_000}억 {value % 10_000:,}만원" if value >= 10_000 else f"{value:,}만원"
