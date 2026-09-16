"""KBO 저장 자료 기반의 게임용 잠재 평가. 현재 능력과 실측 기록은 변경하지 않는다."""
import json
import math
from datetime import date

VERSION = "kbo-potential-career-v3.1"
HITTER = ("contact", "power", "plate_discipline", "bat_control", "timing", "bunt", "speed",
          "baserunning_judgment", "fielding_range", "catching", "throwing_power", "throwing_accuracy",
          "fielding_judgment", "composure", "leadership", "aggressiveness")
PITCHER = ("pitcher_velocity", "pitcher_stuff", "pitcher_command", "pitcher_movement", "pitcher_stamina",
           "pitcher_pitchability", "pitcher_strikeout", "pitcher_walk_control", "pitcher_composure")
PITCHES = ("pitch_four_seam", "pitch_sinker", "pitch_cutter", "pitch_changeup", "pitch_slider", "pitch_curve",
           "pitch_splitter", "pitch_sweeper", "pitch_knuckleball")
PHYSICAL = {"speed", "throwing_power", "fielding_range", "pitcher_velocity", "pitcher_stamina"}
LEARNED = {"plate_discipline", "baserunning_judgment", "throwing_accuracy", "fielding_judgment",
           "composure", "leadership", "pitcher_command", "pitcher_walk_control", "pitcher_pitchability", "pitcher_composure"}


def number(value, default=0):
    try:
        result = float(value)
        return result if math.isfinite(result) else default
    except (TypeError, ValueError):
        return default


def estimate_potential(player, as_of=None):
    from app.services.player_development import age_on
    from app.services.potential_evidence import evidence_for
    day = date.fromisoformat(as_of) if isinstance(as_of, str) else as_of or date(2025, 11, 1)
    age = age_on(player, day)
    pitcher = (player.get("position_group") or player.get("pos")) == "P"
    keys = PITCHER + PITCHES if pitcher else HITTER
    values = {key: int(number(player.get(key))) for key in keys if 1 <= number(player.get(key)) <= 20}
    core = PITCHER if pitcher else ("contact", "power", "plate_discipline", "bat_control", "timing")
    core_values = [values[k] for k in core if k in values]
    evidence = {}
    if not pitcher:
        try:
            evidence = json.loads(player.get("hitter_rating_detail_json") or "{}")
            if not isinstance(evidence, dict):
                evidence = {}
        except (ValueError, TypeError):
            pass
    sample = max(0, number(player.get("pitcher_sample_tbf"))) if pitcher else max(0, number(evidence.get("PA")))
    reliability = min(1., sample / (500 if pitcher else 400))
    confidence = "높음" if reliability >= .75 else "보통" if reliability >= .3 else "낮음"
    history = evidence_for(player, day)
    from app.services.potential_lifecycle import lifecycle_for
    lifecycle = lifecycle_for(player, day, history)
    if history["records"]:
        sample = history["first_team_sample"]
        confidence = history["confidence"]
        reliability = min(1., sample / 650)
    if age <= 23 and confidence == "높음":
        confidence = "보통"
    # Small samples shrink the evidence towards neutral, never grant a talent bonus.
    proven_skill = ((sum(core_values) / len(core_values) if core_values else 10) - 10) / 10
    performance_support = max(-.2, min(.35, proven_skill * reliability))
    pick = number(player.get("draft_pick"))
    prospect = .65 if 0 < pick <= 10 else .4 if pick <= 30 and pick > 0 else .15 if 0 < pick <= 60 else 0
    if age > 24:
        prospect = 0
    base = 3.8 if age <= 19 else 3.1 if age <= 22 else 2.3 if age <= 24 else 1.5 if age <= 27 else .8 if age <= 30 else .3
    caps = {}
    for key, current in values.items():
        if key in PHYSICAL:
            teachability = 1. if age <= 22 else .65 if age <= 26 else .3 if age <= 29 else 0
        elif key in LEARNED:
            teachability = 1.15 if age <= 29 else 1.7 if age <= 33 else 1.
        elif key == "aggressiveness":
            teachability = 0  # Trait direction is not a monotonic improvement.
        else:
            teachability = 1. if age <= 27 else .65 if age <= 31 else .2
        # Positional demand changes the room for technical development, not current skill.
        position = player.get("pos") or player.get("position_group")
        positional = 1.15 if (position == "C" and key == "catching") or (position in ("SS", "2B") and key in ("fielding_range", "fielding_judgment")) else 1.
        # Unknown weaknesses do not get more headroom merely because their rating is low.
        mastery = max(.3, min(1., (22 - current) / 10))
        skill_signal = history["signals"].get(key)
        support = skill_signal * 1.5 if skill_signal is not None else performance_support * .3
        gain = max(0, round((base + prospect + support) * teachability * positional * mastery))
        caps[key] = min(20, current + min(6, gain))
        if history['records'] and skill_signal is not None:
            # Retain evidence of demonstrated skill through absence, not just age + present prior.
            caps[key] = max(caps[key], min(20, round(10 + max(0., skill_signal) * 8)))
    # Role weights exclude personality/bunting and do not reward owning more pitch types.
    if pitcher:
        weights = dict(pitcher_velocity=.12, pitcher_stuff=.20, pitcher_command=.18,
                       pitcher_movement=.12, pitcher_stamina=.10, pitcher_pitchability=.10,
                       pitcher_strikeout=.08, pitcher_walk_control=.08, pitcher_composure=.02)
        appearances = [r for r in history["records"] if r["level"] == "first_team" and r["season"] == lifecycle["evaluated_through"]]
        games = sum(r["games"] for r in appearances)
        if games >= 10 and sum(r["sample"] for r in appearances) / games < 12:
            weights.update(pitcher_stamina=.04, pitcher_stuff=.23, pitcher_velocity=.15)
    else:
        weights = dict(contact=.22, power=.22, plate_discipline=.18, bat_control=.05, timing=.05,
                       speed=.08, baserunning_judgment=.02, fielding_range=.07, catching=.04,
                       throwing_power=.01, throwing_accuracy=.03, fielding_judgment=.03)
        if player.get("pos") == "C" or player.get("position_group") == "C":
            weights.update(power=.18, speed=.02, catching=.14)
        elif player.get("pos") in ("SS", "2B"):
            weights.update(power=.18, fielding_range=.11)
    weights = {key: value for key, value in weights.items() if key in values}
    total = sum(weights.values())
    current_rating = round(sum(values[k] * weights[k] for k in weights) / total * 10) if total else None
    rating = round(sum(caps[k] * weights[k] for k in weights) / total * 10) if total else None
    uncertainty = (5 if confidence == "높음" else 10 if confidence == "보통" else 20) + (5 if age <= 23 else 0)
    needs_review = (not history["records"] and not pick) or age > 45 or any(r["level"] == "historical" for r in history["records"])
    return dict(version=VERSION, reference_date=day.isoformat(), age=age, lifecycle=lifecycle,
                role="투수" if pitcher else "타자", current_rating=current_rating, rating=rating,
                rating_range=[max(current_rating, rating - uncertainty), min(200, rating + uncertainty)] if rating else None,
                confidence=confidence, sample=sample, sample_unit="상대 타자" if pitcher else "타석",
                draft_pick=int(pick) if pick > 0 else None, caps=caps, evidence=history,
                review_required=needs_review,
                assessment="추가 검토 필요" if needs_review else "잠정 평가" if confidence == "낮음" else "기록 기반 추정",
                weights=weights,
                note="공식 잠재력 아님 · 프로 4년차까지 누적 성적 재평가 / 이후 전 경력 확인 후 고정.")


def profile_for(player, as_of=None):
    previous = None
    try:
        profile = json.loads(player.get("potential_profile_json") or "{}")
        if isinstance(profile.get("caps"), dict):
            if (profile.get("lifecycle", {}).get("state") == "fixed"
                    and profile['lifecycle'].get('history_complete')
                    and (profile["lifecycle"].get("career_year") or 0) >= 5):
                return profile
        if profile.get("version") == VERSION and isinstance(profile.get("caps"), dict):
            previous = profile
            if as_of is None:
                as_of = profile.get("reference_date")
    except (ValueError, TypeError, AttributeError):
        pass
    candidate = estimate_potential(player, as_of)
    if previous and previous.get("lifecycle", {}).get("evidence_fingerprint") == candidate["lifecycle"]["evidence_fingerprint"]:
        return dict(previous, lifecycle=candidate["lifecycle"])
    return candidate


def populate_potentials(connection, as_of=None):
    """고정 선수 보존. 4년차 이하는 새 성적이 있을 때 재평가한다."""
    columns = {row[1] for row in connection.execute("PRAGMA table_info(players)")}
    if "potential_profile_json" not in columns:
        connection.execute("ALTER TABLE players ADD COLUMN potential_profile_json TEXT DEFAULT ''")
    cursor = connection.execute("SELECT * FROM players")
    names = [item[0] for item in cursor.description]
    changed = 0
    for row in cursor.fetchall():
        player = dict(zip(names, row))
        profile = profile_for(player, as_of)
        try:
            existing = json.loads(player.get("potential_profile_json") or "{}")
        except (ValueError, TypeError):
            existing = {}
        if existing == profile:
            continue
        connection.execute("UPDATE players SET potential_profile_json=? WHERE id=?",
                           (json.dumps(profile, ensure_ascii=False), player["id"]))
        changed += 1
    return changed


def ensure_saved_potential(connection, save_id, player, as_of=None):
    profile = profile_for(player, as_of)
    lifecycle = profile["lifecycle"]
    signature = VERSION + ":" + lifecycle["evidence_fingerprint"] + ":" + lifecycle["state"]
    existing = connection.execute("SELECT version FROM player_potential_versions WHERE save_id=? AND player_id=?",
                                  (save_id, player["id"])).fetchone()
    if existing and existing[0] == signature:
        return
    for attribute, cap in profile["caps"].items():
        ceiling = max(int(number(player.get(attribute))), int(cap))
        connection.execute("""INSERT INTO player_attribute_development VALUES (?,?,?,?,0)
            ON CONFLICT(save_id,player_id,attribute) DO UPDATE SET ceiling=excluded.ceiling""",
            (save_id, player["id"], attribute, min(20, ceiling)))
    connection.execute("""INSERT INTO player_potential_versions VALUES (?,?,?)
        ON CONFLICT(save_id,player_id) DO UPDATE SET version=excluded.version""", (save_id, player["id"], signature))
    # Persist the lifecycle in the save's player DB, not only in the global source DB.
    attached = {r[1] for r in connection.execute("PRAGMA database_list")}
    if "playerdb" in attached:
        columns = {r[1] for r in connection.execute("PRAGMA playerdb.table_info(players)")}
        if "potential_profile_json" not in columns:
            connection.execute("ALTER TABLE playerdb.players ADD COLUMN potential_profile_json TEXT DEFAULT ''")
        connection.execute("UPDATE playerdb.players SET potential_profile_json=? WHERE id=?",
                           (json.dumps(profile, ensure_ascii=False), player["id"]))
