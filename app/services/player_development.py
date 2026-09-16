"""능력별 누적 성장·잠재 한계·에이징. 수치는 게임 설계이며 실측 예측 모델이 아니다."""
import calendar
import hashlib
from datetime import date

PHYSICAL = {"speed", "fielding_range", "throwing_power", "power", "pitcher_velocity", "pitcher_stamina"}


def roll(*parts):
    return int.from_bytes(hashlib.sha256(":".join(map(str, parts)).encode()).digest()[:8], "big") / 2**64


def age_on(player, day):
    if isinstance(day, str):
        day = date.fromisoformat(day)
    try:
        born = date.fromisoformat(str(player.get("birth_date")))
        return max(16, day.year - born.year - ((day.month, day.day) < (born.month, born.day)))
    except (ValueError, TypeError):
        return int(player.get("age") or 27)


def growth_multiplier(player, state, day, attribute):
    age = age_on(player, day)
    age_factor = 1.25 if age <= 22 else 1.0 if age <= 26 else .65 if age <= 29 else .35 if age <= 33 else .16
    if attribute in PHYSICAL and age >= 30:
        age_factor *= .6
    if state.get("injury_days", 0) > 0 or state.get("squad_group") == "국가대표":
        return 0.0
    condition = max(.1, min(1., float(state.get("condition", 85)) / 85))
    fatigue = max(.1, 1 - float(state.get("fatigue", 0)) / 100)
    morale = .6 + float(state.get("morale", 75)) / 200
    # Sharpness is a readiness proxy, not an invented count of match appearances.
    readiness = .75 + float(state.get("match_sharpness", 55)) / 400
    return age_factor * condition * fatigue * morale * readiness


def apply_daily_development(connection, save_id, player, state, day, training):
    from app.services.training import HITTER_ATTRIBUTES, PITCHER_ATTRIBUTES
    day = day if isinstance(day, date) else date.fromisoformat(day)
    day_text = day.isoformat()
    player_id = int(player["id"])
    marker = connection.execute("INSERT OR IGNORE INTO development_processed_days VALUES (?,?,?)",
                                (save_id, player_id, day_text))
    if not marker.rowcount:
        return
    is_pitcher = (player.get("position_group") or player.get("pos")) == "P"
    allowed = {key for keys in (PITCHER_ATTRIBUTES if is_pitcher else HITTER_ATTRIBUTES).values() for key in keys}
    allowed |= {"speed", "throwing_power"} if not is_pitcher else {"pitcher_velocity", "pitcher_stamina"}
    age = age_on(player, day)
    attribute = training.get("attribute")
    if attribute in allowed and player.get(attribute) is not None:
        current = int(player[attribute])
        if 1 <= current <= 20:
            from app.services.player_potential import profile_for
            ceiling = profile_for(player)["caps"].get(attribute, current)
            connection.execute("""INSERT OR IGNORE INTO player_attribute_development
                (save_id,player_id,attribute,ceiling,progress) VALUES (?,?,?,?,0)""",
                (save_id, player_id, attribute, max(current, min(20, ceiling))))
            record = connection.execute("""SELECT * FROM player_attribute_development
                WHERE save_id=? AND player_id=? AND attribute=?""", (save_id, player_id, attribute)).fetchone()
            points = max(0, float(training.get("training_gain", 0)))
            multiplier = growth_multiplier(player, state, day, attribute)
            variation = .75 + .5 * roll(save_id, player_id, day_text, "response")
            progress = float(record["progress"]) + points * multiplier * variation
            threshold = 90 + max(0, current - 12) * 12
            if current >= record["ceiling"]:
                progress = 0
            elif progress >= threshold:
                connection.execute(f"UPDATE playerdb.players SET {attribute}=? WHERE id=?", (current + 1, player_id))
                connection.execute("INSERT INTO player_development_events VALUES (?,?,?,?,?,?,?)",
                    (save_id, player_id, day_text, attribute, current, current + 1,
                     f"목표 훈련 누적 · {age}세 · 회복/사기/경기감각 반영"))
                progress -= threshold
            connection.execute("""UPDATE player_attribute_development SET progress=?
                WHERE save_id=? AND player_id=? AND attribute=?""", (progress, save_id, player_id, attribute))
    # One bounded monthly decline opportunity, not a daily penalty to every skill.
    if day.day == calendar.monthrange(day.year, day.month)[1] and age >= 32:
        probability = min(.25, (age - 31) * .018 + max(0, state.get("fatigue", 0) - 50) / 1000)
        if roll(save_id, player_id, day_text, "decline") < probability:
            choices = sorted(k for k in allowed & PHYSICAL if player.get(k) is not None and 1 < int(player[k]) <= 20)
            if choices:
                key = choices[min(len(choices) - 1, int(roll(save_id, player_id, day_text, "decline-skill") * len(choices)))]
                current = connection.execute(f"SELECT {key} FROM playerdb.players WHERE id=?", (player_id,)).fetchone()[0]
                connection.execute(f"UPDATE playerdb.players SET {key}=? WHERE id=?", (current - 1, player_id))
                connection.execute("INSERT INTO player_development_events VALUES (?,?,?,?,?,?,?)",
                    (save_id, player_id, day_text, key, current, current - 1, f"{age}세 · 신체 능력 에이징"))
