"""구단 비전 협상에서 사용하는 결정·단계 공통 규칙."""


LEVELS = {
    1: {"label": "대폭 완화", "base_trust_delta": -8},
    2: {"label": "일부 완화", "base_trust_delta": -3},
    3: {"label": "원안 합의", "base_trust_delta": 0},
    4: {"label": "도전 합의", "base_trust_delta": 3},
    5: {"label": "최고 목표", "base_trust_delta": 6},
}

PRIORITY_WEIGHTS = {"필수": 2.0, "중요": 1.4, "장기": 1.2, "권장": 0.8}

DECISION_LABELS = {
    "accept": "승인",
    "conditional_accept": "조건부 승인",
    "counter_offer": "역제안",
    "reject": "거절",
}


def trust_delta_for_level(level, priority):
    data = LEVELS[int(level)]
    weight = PRIORITY_WEIGHTS.get(priority, 1.0)
    return round(data["base_trust_delta"] * weight)


def final_level_for_decision(requested_level, decision):
    requested_level = int(requested_level)
    if decision in {"accept", "conditional_accept"}:
        return requested_level
    if decision == "counter_offer":
        if requested_level < 3:
            return requested_level + 1
        if requested_level > 3:
            return requested_level - 1
    return 3


PLAYER_MEETING_POSITIVE_WEIGHTS = {
    "이해": 2,
    "듣": 2,
    "인정": 2,
    "함께": 2,
    "솔직": 1,
    "기회": 3,
    "출전": 2,
    "1군": 2,
    "역할": 2,
    "계획": 2,
    "목표": 2,
    "약속": 2,
    "공정": 3,
    "투명": 2,
    "기준": 2,
    "성장": 2,
    "보완": 1,
}

PLAYER_MEETING_NEGATIVE_WEIGHTS = {
    "감독의 권한": -5,
    "특별 대우": -4,
    "의미가 없다": -5,
    "다른 선택": -5,
    "방출": -8,
    "싫으면": -7,
    "명령": -5,
    "따라야": -4,
    "먼저 증명": -2,
}


def player_meeting_rule_delta(message):
    """감독 발언의 공감·구체성·강압성을 결정론적으로 평가한다."""
    text = str(message or "")
    score = sum(
        weight
        for term, weight in PLAYER_MEETING_POSITIVE_WEIGHTS.items()
        if term in text
    )
    score += sum(
        weight
        for term, weight in PLAYER_MEETING_NEGATIVE_WEIGHTS.items()
        if term in text
    )
    if len(text) >= 35:
        score += 1
    elif len(text) < 10:
        score -= 2
    return max(-10, min(12, score))


def player_meeting_rule_reply(message, context=None):
    """감독의 실제 발언을 짚어 답하는 선수 1인칭 폴백 대사를 만든다."""
    text = str(message or "")
    context = context or {}
    player_context = context.get("player_context") or {}
    squad = str(player_context.get("squad") or "")
    round_number = max(1, int(context.get("round") or 1))
    delta = player_meeting_rule_delta(message)
    if delta <= -3:
        if any(term in text for term in ("다른 선택", "방출", "싫으면")):
            return (
                "제 의견을 말씀드리러 왔는데 다른 선택까지 이야기하시면 "
                "저도 많이 실망스럽습니다. 이 상태로는 제 역할에 대해 "
                "납득하기 어렵습니다."
            )
        if "특별 대우" in text or "같은 기준" in text:
            return (
                "특별 대우를 바라는 게 아니라, 제가 무엇을 더 해야 기회를 "
                "받는지 알고 싶은 겁니다. 제 질문에 대한 답은 듣지 못한 것 같습니다."
            )
        return (
            "결정을 따르라는 말씀만으로는 제가 왜 지금 역할에 머물러야 하는지 "
            "납득하기 어렵습니다. 제 이야기도 조금은 들어주셨으면 합니다."
        )
    if "듣" in text and ("이해" in text or "입장" in text):
        if round_number > 1:
            return (
                "계속 제 입장을 들어주시려는 건 감사합니다. 제가 바라는 건 "
                "무조건적인 출전이 아니라, 준비한 만큼 경쟁할 수 있는 기회입니다."
            )
        return (
            "먼저 제 이야기를 들어주시겠다고 하니 감사합니다. "
            f"지금 {squad or '선수단'}에서 무엇을 더 준비해야 실제 기회를 "
            "받을 수 있는지 솔직하게 말씀해 주셨으면 합니다."
        )
    if "원하는 역할" in text and "구체적으로" in text:
        desired_role = (
            "1군에서 경쟁할 수 있는 기회"
            if squad == "2군"
            else "지금보다 분명한 출전 역할"
        )
        return (
            f"제가 원하는 건 {desired_role}입니다. 당장 자리를 보장해 달라는 "
            "뜻은 아니지만, 가능하려면 무엇을 더 보여드려야 하는지 알고 싶습니다."
        )
    if "기회" in text and any(term in text for term in ("기준", "투명", "공정")):
        opportunity = "1군 경쟁 기회" if squad == "2군" else "출전 기회"
        return (
            f"{opportunity}를 주는 기준을 공개해 주신다면 저도 납득하고 "
            "준비할 수 있습니다. 어떤 항목을 언제까지 증명해야 하는지 "
            "코치님들과도 공유해 주십시오."
        )
    if "노력을 인정" in text and "다시 검토" in text:
        return (
            "지금까지 준비한 부분을 인정해 주셔서 감사합니다. "
            "코치진과 다시 검토한 뒤 제가 맡을 역할과 부족한 점을 "
            "구체적으로 설명해 주셨으면 합니다."
        )
    if "평가 시점" in text or ("직접" in text and "결과" in text):
        return (
            "평가할 시점과 결과를 직접 설명해 주신다는 약속이라면 믿어보겠습니다. "
            "그때까지 제가 준비해야 할 과제도 명확하게 정해주셨으면 합니다."
        )
    if "수비" in text and "체력" in text:
        return (
            "수비와 체력을 먼저 끌어올리라는 뜻은 알겠습니다. "
            "요구하신 수치를 채웠을 때 대수비에서 끝나는 게 아니라 "
            "선발 경쟁까지 이어지는 건지 확인하고 싶습니다."
        )
    if "역할" in text and any(term in text for term in ("계획", "보완", "솔직")):
        return (
            "제 역할과 부족한 부분을 솔직하게 설명해 주신다면 받아들이겠습니다. "
            "다만 보완했을 때 어떤 기회로 이어지는지도 함께 정해주셨으면 합니다."
        )
    if "팀이 필요로 하는 역할" in text:
        return (
            "팀이 요구하는 역할을 먼저 해내야 한다는 말씀은 이해합니다. "
            "그 역할에서 결과를 냈을 때 출전 비중도 실제로 늘어나는지 "
            "분명히 약속해 주셨으면 합니다."
        )
    if "기록" in text and "판단" in text:
        return (
            "기록으로 판단하겠다는 원칙은 받아들이겠습니다. "
            "다만 제 보직에서 어떤 기록을 중점적으로 보는지 분명히 알려주셔야 "
            "저도 그 목표에 맞춰 준비할 수 있습니다."
        )
    if any(term in text for term in ("목표", "성장", "계획")):
        return (
            "단계별 목표를 정해주신다면 막연히 기다리는 것보다는 훨씬 낫습니다. "
            "과제를 달성한 뒤 다시 면담해서 제 역할을 확실히 이야기하고 싶습니다."
        )
    if "경쟁" in text and "증명" in text:
        return (
            "경쟁을 피하려는 건 아닙니다. 훈련에서 무엇을 증명해야 하는지와 "
            "그 결과가 실제 기용으로 이어지는 시점을 분명히 말씀해 주십시오."
        )
    if delta >= 6:
        return (
            "구체적으로 말씀해 주시니 제가 무엇을 준비해야 할지는 알겠습니다. "
            "말씀하신 조건을 해냈을 때 약속한 기회를 꼭 지켜주셨으면 합니다."
        )
    if delta >= 2:
        return (
            "말씀하신 취지는 이해했습니다. 그 기준이 실제 선수 기용에도 "
            "같이 적용된다면 저도 결과로 보여드리겠습니다."
        )
    return (
        "말씀은 이해하지만 제가 언제, 어떤 기준으로 기회를 받을 수 있는지 "
        "조금 더 구체적으로 듣고 싶습니다."
    )
