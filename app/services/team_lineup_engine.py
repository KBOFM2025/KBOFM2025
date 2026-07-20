"""선수 능력과 현재 상태를 이용한 1군·2군 라인업 및 투수 보직 편성."""


DEFENSIVE_SLOTS = (
    ("C", "C"),
    ("IF", "1B"),
    ("IF", "2B"),
    ("IF", "3B"),
    ("IF", "SS"),
    ("OF", "LF"),
    ("OF", "CF"),
    ("OF", "RF"),
)


def _values(player, keys):
    return [float(player[key]) for key in keys if player.get(key) is not None]


def hitter_rating(player):
    values = _values(
        player,
        ("contact", "power", "plate_discipline", "bat_control", "speed", "fielding_judgment"),
    )
    if not values:
        values = _values(player, ("con", "pow", "eye", "def"))
    return sum(values) / len(values) if values else 10.0


def pitcher_rating(player):
    values = _values(player, ("con", "pow", "eye", "def"))
    return sum(values) / len(values) if values else 10.0


def availability_score(player, state, development=3):
    base = pitcher_rating(player) if player.get("position_group") == "P" else hitter_rating(player)
    youth = max(0, 29 - int(player.get("age", 29))) * development * 0.025
    return (
        base * 2.2
        + int(state.get("condition", 80)) * 0.35
        + int(state.get("match_sharpness", 55)) * 0.22
        + int(state.get("morale", 75)) * 0.12
        - int(state.get("fatigue", 0)) * 0.3
        + youth
    )


class TeamLineupEngine:
    def build(self, players, states, squad_level, development=3):
        roster = [
            player for player in players
            if int(bool(player.get("status"))) == int(squad_level)
            and int(states[player["id"]].get("injury_days", 0)) == 0
        ]
        hitters = [player for player in roster if player.get("position_group") != "P"]
        pitchers = [player for player in roster if player.get("position_group") == "P"]
        batting = self._build_batting_lineup(hitters, states, development)
        pitching = self._build_pitching_roles(pitchers, states, development)
        return batting, pitching

    def _build_batting_lineup(self, hitters, states, development):
        selected = []
        used = set()
        for group, defensive_position in DEFENSIVE_SLOTS:
            candidates = [
                player for player in hitters
                if player["id"] not in used and player.get("position_group") == group
            ]
            if not candidates:
                candidates = [player for player in hitters if player["id"] not in used]
            if not candidates:
                break
            player = max(
                candidates,
                key=lambda item: (availability_score(item, states[item["id"]], development), -item["id"]),
            )
            used.add(player["id"])
            selected.append((player, defensive_position))
        remaining = [player for player in hitters if player["id"] not in used]
        if remaining:
            dh = max(
                remaining,
                key=lambda item: (availability_score(item, states[item["id"]], development), -item["id"]),
            )
            selected.append((dh, "DH"))

        def batting_value(entry):
            player, _position = entry
            contact = player.get("contact") if player.get("contact") is not None else player.get("con", 10)
            power = player.get("power") if player.get("power") is not None else player.get("pow", 10)
            eye = player.get("plate_discipline") if player.get("plate_discipline") is not None else player.get("eye", 10)
            speed = player.get("speed") or 10
            return float(contact) * 1.4 + float(eye) + float(power) * 0.9 + float(speed) * 0.35

        selected.sort(key=batting_value, reverse=True)
        if len(selected) >= 4:
            power_order = sorted(
                selected,
                key=lambda entry: float(
                    entry[0].get("power")
                    if entry[0].get("power") is not None
                    else entry[0].get("pow", 10)
                ),
                reverse=True,
            )
            cleanup = power_order[0]
            selected.remove(cleanup)
            selected.insert(3, cleanup)
        return [
            {
                "batting_order": index + 1,
                "player_id": player["id"],
                "player_name": player["name"],
                "defensive_position": position,
                "selection_score": round(availability_score(player, states[player["id"]], development), 2),
            }
            for index, (player, position) in enumerate(selected[:9])
        ]

    def _build_pitching_roles(self, pitchers, states, development):
        ranked = sorted(
            pitchers,
            key=lambda player: (availability_score(player, states[player["id"]], development), -player["id"]),
            reverse=True,
        )
        roles = []
        role_names = ["1선발", "2선발", "3선발", "4선발", "5선발"]
        for role, player in zip(role_names, ranked[:5]):
            roles.append((role, player))
        bullpen = ranked[5:]
        if bullpen:
            closer = max(
                bullpen,
                key=lambda player: float(player.get("pow") or 10) * 1.4 + float(player.get("eye") or 10),
            )
            bullpen.remove(closer)
            roles.append(("마무리", closer))
        for index, player in enumerate(bullpen):
            if index < 2:
                role = f"필승조 {index + 1}"
            elif index < 5:
                role = f"중간계투 {index - 1}"
            else:
                role = "추격·롱릴리프"
            roles.append((role, player))
        return [
            {
                "role_order": index + 1,
                "role": role,
                "player_id": player["id"],
                "player_name": player["name"],
                "selection_score": round(availability_score(player, states[player["id"]], development), 2),
            }
            for index, (role, player) in enumerate(roles)
        ]
