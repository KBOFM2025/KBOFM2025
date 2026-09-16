"""외부 생성 AI 없이 구단 성향·회복 상태에 따라 편성하는 훈련 운영."""
from datetime import date, datetime

from app.config.club_training_profiles import club_profile


def sessions_for_day(team, day, condition=85, fatigue=0):
    if isinstance(day, str):
        day = date.fromisoformat(day)
    profile = club_profile(team)
    if condition < 65 or fatigue >= 65 or day.month in (12, 1):
        return ("휴식", "회복", "휴식")
    if day.month == 11:
        offset = day.day - 1
        if day.day > 24 or offset % (profile["cycle"] + 1) == profile["cycle"]:
            return ("휴식", "회복", "휴식")
        complementary = ("투수 불펜", "포수 수비", "주루", "내야 수비", "변화구", "외야 수비")
        result = [profile["first"], profile["second"], complementary[offset % 6]]
    else:
        result = list((
            ("휴식", "회복", "휴식"), ("체력", "타격 기술", "투수 불펜"),
            ("내야 수비", "외야 수비", "포수 수비"), ("타격 기술", "투수 제구", "주루"),
            ("라이브 BP", "팀 전술", "회복"), ("타격 기술", "변화구", "자율 훈련"),
            ("회복", "자율 훈련", "휴식"),
        )[day.weekday()])
    if condition < 75 or fatigue >= 40:
        result[2] = "회복"
    return tuple(result)


def apply_delegated_training(connection, save_id, players, day):
    """날짜 진행 트랜잭션 안에서 실행하며 수동 계획을 보존한다."""
    from app.services.training import HITTER_ATTRIBUTES, PITCHER_ATTRIBUTES, TRAINING_SLOTS
    day = day.isoformat() if isinstance(day, date) else str(day)
    now = "auto:" + datetime.now().isoformat(timespec="seconds")
    for policy in connection.execute("SELECT * FROM training_management WHERE save_id=?", (save_id,)).fetchall():
        team = policy["team"]
        head = connection.execute("""SELECT 1 FROM coach_assignments a JOIN coaching_staff c
            ON c.save_id=a.save_id AND c.id=a.coach_id WHERE a.save_id=? AND a.team=?
            AND a.assignment_type='responsibility' AND c.team=? AND c.status='hired'""",
            (save_id, team, team)).fetchone()
        if not head or not (policy["delegate_team"] or policy["delegate_individual"]):
            continue
        roster = [p for p in players if p["team"] == team]
        states = {r["player_id"]: dict(r) for r in connection.execute(
            "SELECT * FROM player_simulation_states WHERE save_id=? AND team=?", (save_id, team))}
        available = [p for p in roster if states.get(p["id"], {}).get("squad_group") != "국가대표"
                     and not states.get(p["id"], {}).get("injury_days", 0)]
        condition = sum(states.get(p["id"], {}).get("condition", 85) for p in available) / max(1, len(available))
        fatigue = sum(states.get(p["id"], {}).get("fatigue", 0) for p in available) / max(1, len(available))
        count = 0
        if policy["delegate_team"]:
            for slot, session in zip(TRAINING_SLOTS, sessions_for_day(team, day, condition, fatigue)):
                connection.execute("""INSERT INTO weekly_training_sessions VALUES (?,?,?,?,?,?)
                    ON CONFLICT(save_id,team,session_date,slot) DO UPDATE SET
                    session_type=excluded.session_type,updated_at=excluded.updated_at
                    WHERE weekly_training_sessions.updated_at='' OR weekly_training_sessions.updated_at LIKE 'auto:%'""",
                    (save_id, team, day, slot, session, now))
        if policy["delegate_individual"]:
            for player in roster:
                state = states.get(player["id"], {})
                if state.get("squad_group") == "국가대표":
                    continue
                attributes = PITCHER_ATTRIBUTES if (player.get("position_group") or player.get("pos")) == "P" else HITTER_ATTRIBUTES
                # Compare only present attributes on the game's common 1–20 scale.
                scores = {focus: sum(float(player[k]) for k in keys if player.get(k) is not None) /
                          sum(player.get(k) is not None for k in keys)
                          for focus, keys in attributes.items() if any(player.get(k) is not None for k in keys)}
                focus = min(scores, key=scores.get) if scores else "자동"
                recovering = state.get("injury_days", 0) > 0 or state.get("condition", 85) < 70 or state.get("fatigue", 0) >= 50
                cursor = connection.execute("""INSERT INTO individual_training_plans
                    (save_id,player_id,team,focus,intensity,active,updated_at) VALUES (?,?,?,?,?,1,?)
                    ON CONFLICT(save_id,player_id) DO UPDATE SET focus=excluded.focus,
                    intensity=excluded.intensity,updated_at=excluded.updated_at
                    WHERE individual_training_plans.updated_at='' OR individual_training_plans.updated_at LIKE 'auto:%'""",
                    (save_id, player["id"], team, "회복" if recovering else focus, 1 if recovering else 2, now))
                count += cursor.rowcount
        summary = f"{club_profile(team)['theme']} · 평균 컨디션 {condition:.0f} / 피로 {fatigue:.0f} · 개인 훈련 {count}명 조정 · 직접 저장한 계획 유지"
        connection.execute("""INSERT INTO training_delegation_reports VALUES (?,?,?,?)
            ON CONFLICT(save_id,team,report_date) DO UPDATE SET summary=excluded.summary""", (save_id, team, day, summary))
