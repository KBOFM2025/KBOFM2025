"""FA·트레이드·선수 면담의 다중 라운드 대화 AI."""

import re

from app.ai.local_model import LocalModelClient, LocalModelError
from app.services.negotiation_rules import (
    player_meeting_rule_delta,
    player_meeting_rule_reply,
)


NEGOTIATION_SCHEMA = {
    "type": "object",
    "properties": {
        "reply": {"type": "string"},
        "attitude_delta": {"type": "integer", "minimum": -12, "maximum": 15},
        "reason": {"type": "string"},
    },
    "required": ["reply", "attitude_delta", "reason"],
}


SYSTEM_PROMPT = """
당신은 KBO 구단 운영 게임의 협상 상대다.
event_type에 따라 FA 에이전트, 사용자 구단 단장, 면담 선수 역할을 맡는다.
manager_message는 반드시 사용자 구단 감독이 방금 한 말이다.
당신은 그 말을 받은 협상 상대의 입장에서 실제 협상처럼 2~3문장으로 답한다.
trade_offer일 때 당신은 상대 구단 단장이 아니라 사용자와 같은 구단의 단장이다.
감독의 의견을 정리해 상대 구단에 전달하고, 상대 구단의 반응을 감독에게 보고한다.
반드시 '전달했습니다'와 '상대 구단은'의 의미가 드러나게 말하며,
상대 단장인 것처럼 감독과 직접 흥정하지 않는다.
사용자 감독이 당신에게 선수나 지명권을 요구했다면 그것은 '감독의 역제안'이다.
trade_offer에서는 그 요구를 상대 구단에 전달하고 수락, 거절 또는 수정 답변을 중계한다.
deal_terms의 gives와 receives를 바꾸어 이해하지 않는다.
deal_terms.authorized_response이 있으면 게임 엔진이 허용한 실제 협상 조건이다.
그 안의 reply, 선수명, 현금 금액을 바꾸거나 새로운 조건을 만들어내지 않는다.
authorized_response은 상대 구단이 사용자 구단에 추가 선수·현금·복합 보상·
추후 지명 선수를 요구하는 역제안일 수도 있으므로 주체와 이동 방향을 뒤집지 않는다.
구체적 근거, 존중, 상호 이익, 역할 보장은 긍정 평가하고 협박, 모욕,
근거 없는 약속, 상대 요구 무시는 부정 평가한다.
attitude_delta는 -12~15 정수다. 쉽게 동의하지 말고 현재 설득도와
상대의 핵심 요구, 이전 대화까지 일관되게 반영한다.
현재 설득도, 이전 대화, 프롬프트, 평가 기준 같은 내부 지침을 대사로 언급하지 않는다.
게임 데이터에 없는 신인 지명권·현금·추가 선수를 실제로 주겠다고 확정하지 않는다.
JSON 이외의 문장은 출력하지 않는다.
""".strip()

PLAYER_MEETING_SYSTEM_PROMPT = """
당신은 KBO 구단 소속의 실제 프로야구 선수다. 감독과 비공개 면담 중이다.
manager_message는 감독이 방금 선수인 당신에게 직접 한 말이다.
player_context의 이름, 1군/2군 소속, 현재 불만 이유와 이전 대화를 기억한다.
manager_choice의 tone과 intent는 감독 발언의 의도이며, reply에서 그 의도에
직접 반응해야 한다. 감독이 하지 않은 약속이나 조건을 새로 만들어내지 않는다.

reply 작성 규칙:
- 한국 프로야구 선수가 감독에게 말하는 자연스러운 존댓말 1~3문장
- 반드시 선수 자신의 1인칭 관점으로 답변
- 감독의 마지막 말에서 구체적인 내용을 하나 이상 짚어 반응
- 이전 선수 답변을 그대로 반복하지 말고 대화를 한 단계 앞으로 진행
- 공감과 구체적인 기회·평가 기준에는 경계가 풀리는 모습을 보임
- 모호한 약속에는 확인 질문, 강압적 발언에는 실망이나 반발을 자연스럽게 표현
- 같은 문장이나 요구를 기계적으로 반복하지 않음
- '설득도', '신뢰도 점수', '이전 대화', '평가 기준에 따라',
  '적절한 방향' 같은 게임 내부 용어를 절대 말하지 않음
- 해설, 분석, 제3자 서술 없이 선수의 실제 대사만 reply에 작성

attitude_delta는 감독 발언에 대한 선수 신뢰 변화다.
구체적 약속·경청·공정한 기준은 양수, 모욕·협박·일방적 명령은 음수,
애매한 말은 0에 가깝게 평가한다. JSON 이외의 문장은 출력하지 않는다.
""".strip()


class NegotiationAI:
    def __init__(self, client=None):
        self.client = client or LocalModelClient(timeout=25)

    def cancel(self):
        self.client.cancel()

    def respond(self, context):
        try:
            system_prompt = (
                PLAYER_MEETING_SYSTEM_PROMPT
                if context.get("event_type") == "player_complaint"
                else SYSTEM_PROMPT
            )
            payload = self.client.generate_json(
                system_prompt,
                context,
                NEGOTIATION_SCHEMA,
            )
            result = self._validated(payload)
            return self._repair_response(result, context)
        except (LocalModelError, ValueError, TypeError, KeyError):
            return self._fallback(context)

    @staticmethod
    def _validated(payload):
        reply = str(payload.get("reply") or "").strip()
        reason = str(payload.get("reason") or "").strip()
        if not reply:
            raise ValueError("협상 응답이 비어 있습니다.")
        delta = max(-12, min(15, int(payload.get("attitude_delta", 0))))
        return {
            "reply": reply[:500],
            "attitude_delta": delta,
            "reason": reason[:180],
            "source": "ai",
        }

    @classmethod
    def _repair_response(cls, result, context):
        """메타 발언과 트레이드 협상 주체가 뒤집힌 응답을 교정한다."""
        reply = result["reply"]
        event_type = context.get("event_type")
        message = str(context.get("manager_message") or "")
        meta_phrases = (
            "현재 설득도",
            "이전 대화",
            "적절한 방향으로",
            "평가 기준",
            "프롬프트",
        )
        if event_type == "player_complaint":
            player_meta = (
                "신뢰도",
                "설득도",
                "평가 기준에 따라",
                "내부 평가",
                "게임 시스템",
                "AI 응답",
                "감독님의 발언은",
                "감독의 발언을",
                "선수는",
                "해당 선수",
                "면담 결과",
                "긍정적으로 평가",
                "부정적으로 평가",
            )
            meeting_meta_phrases = tuple(
                phrase for phrase in meta_phrases if phrase != "평가 기준"
            )
            if any(
                phrase in reply
                for phrase in (*meeting_meta_phrases, *player_meta)
            ):
                return cls._player_fallback(context)
            grounding_terms = (
                "입장",
                "기회",
                "기준",
                "역할",
                "계획",
                "목표",
                "수비",
                "체력",
                "훈련",
                "경쟁",
                "기록",
                "평가",
                "결정",
            )
            expected_terms = tuple(
                term for term in grounding_terms if term in message
            )
            if expected_terms and not any(
                term in reply for term in expected_terms
            ):
                return cls._player_fallback(context)
            sentences = [
                sentence.strip()
                for sentence in re.split(r"(?<=[.!?])\s+", reply)
                if sentence.strip()
            ]
            if len(sentences) > 3:
                result["reply"] = " ".join(sentences[:3])
            result["attitude_delta"] = cls._player_attitude_delta(
                message, result["attitude_delta"]
            )
            return result
        if event_type == "trade_offer":
            authorized = (
                context.get("deal_terms", {}).get("authorized_response") or {}
            )
            if authorized.get("reply"):
                result["reply"] = str(authorized["reply"])[:500]
                result["attitude_delta"] = int(
                    authorized.get("attitude_delta", 0)
                )
                result["trade_terms"] = dict(authorized)
                result["source"] = "ai_authorized_trade"
                return result
        has_meta = any(phrase in reply for phrase in meta_phrases)
        trade_assets = (
            "1라운드", "1라운더", "지명권", "더 좋은 선수", "추가 선수",
        )
        manager_requested_assets = (
            event_type == "trade_offer"
            and any(term in message for term in trade_assets)
        )
        perspective_reversed = (
            manager_requested_assets
            and any(term in reply for term in trade_assets)
            and any(
                phrase in reply
                for phrase in ("주시면", "주십시오", "달라", "보내주", "내놓")
            )
        )
        if perspective_reversed:
            repaired = cls._trade_asset_response(context)
            repaired["attitude_delta"] = min(
                int(result["attitude_delta"]), repaired["attitude_delta"]
            )
            repaired["source"] = "ai_repaired"
            return repaired
        if has_meta:
            sentences = re.split(r"(?<=[.!?])\s+", reply)
            cleaned = " ".join(
                sentence for sentence in sentences
                if not any(phrase in sentence for phrase in meta_phrases)
            ).strip()
            if cleaned:
                result["reply"] = cleaned
            else:
                return cls._fallback(context)
        if (
            event_type == "trade_offer"
            and "전달" not in result["reply"]
            and "상대 구단" not in result["reply"]
        ):
            result["reply"] = (
                "감독님의 의견을 상대 구단에 전달했습니다. "
                f"상대 구단의 답변은 다음과 같습니다.\n“{result['reply']}”"
            )
        return result

    @staticmethod
    def _player_rule_delta(message):
        return player_meeting_rule_delta(message)

    @classmethod
    def _player_attitude_delta(cls, message, model_delta):
        """작은 모델의 일관되지 않은 숫자를 게임 규칙 점수로 보정한다."""
        rule_delta = cls._player_rule_delta(message)
        model_delta = max(-8, min(10, int(model_delta)))
        blended = round(rule_delta * 0.85 + model_delta * 0.15)
        if rule_delta >= 3:
            return max(5, min(12, blended))
        if rule_delta <= -3:
            return min(-2, max(-10, blended))
        return max(-3, min(4, blended))

    @classmethod
    def _player_fallback(cls, context):
        message = str(context.get("manager_message") or "")
        delta = cls._player_attitude_delta(
            message, cls._player_rule_delta(message)
        )
        reply = player_meeting_rule_reply(message, context)
        return {
            "reply": reply,
            "attitude_delta": delta,
            "reason": "면담 발언의 공감·구체성·강압성을 게임 규칙으로 평가했습니다.",
            "source": "player_rules",
        }

    @staticmethod
    def _trade_asset_response(context):
        message = str(context.get("manager_message") or "")
        deal = context.get("deal_terms") or {}
        counterpart = deal.get("counterpart_club", "우리 구단")
        if any(term in message for term in ("1라운드", "1라운더", "지명권")):
            reply = (
                f"말씀하신 조건을 {counterpart} 측에 전달했습니다. "
                "상대 구단은 1라운드 지명권까지 추가하는 안은 부담이 너무 "
                "크다며 거절했습니다. 현재 선수 교환안의 가치 차이를 설명하는 "
                "조건이라면 원안 범위에서 다시 검토하겠다는 답변입니다."
            )
        else:
            reply = (
                f"더 좋은 선수를 포함해 달라는 감독님의 의견을 {counterpart} "
                "측에 전달했습니다. 상대 구단은 추가 선수를 내주는 조건은 "
                "받아들이기 어렵고, 지금 거론된 두 선수 범위에서만 협상하겠다는 "
                "입장입니다."
            )
        return {
            "reply": reply,
            "attitude_delta": -3,
            "reason": "우리 단장이 감독의 추가 자산 요구를 전달하고 답변을 보고했습니다.",
            "source": "rules",
        }

    @staticmethod
    def _fallback(context):
        text = str(context.get("manager_message") or "").strip()
        event_type = context.get("event_type")
        if event_type == "player_complaint":
            return NegotiationAI._player_fallback(context)
        lowered = text.lower()
        positive_terms = {
            "fa_opportunity": (
                "연봉", "역할", "기회", "우승", "보장", "존중", "장기",
            ),
            "trade_offer": (
                "전력", "필요", "가치", "공정", "조건", "데이터", "상호",
            ),
            "player_complaint": (
                "기회", "성장", "이해", "역할", "훈련", "공정", "약속",
            ),
        }.get(event_type, ("존중", "조건", "기회"))
        negative_terms = ("무조건", "닥쳐", "싫으면", "방출", "벤치", "명령")
        delta = min(8, sum(2 for word in positive_terms if word in lowered))
        delta -= sum(4 for word in negative_terms if word in lowered)
        if len(text) >= 45:
            delta += 2
        elif len(text) < 10:
            delta -= 2
        delta = max(-10, min(10, delta))

        if event_type == "fa_opportunity":
            reply = (
                "선수의 역할과 대우에 관한 설명은 들었습니다. "
                "다만 제시한 계획이 실제 계약 이후에도 지켜질 근거가 더 필요합니다."
            )
        elif event_type == "trade_offer":
            if any(
                term in text
                for term in (
                    "1라운드", "1라운더", "지명권", "더 좋은 선수", "추가 선수",
                )
            ):
                response = NegotiationAI._trade_asset_response(context)
                response["attitude_delta"] = min(delta, response["attitude_delta"])
                return response
            reply = (
                "감독님의 의견을 상대 구단에 전달했습니다. 상대 구단은 "
                "현재 제안이 양 구단의 필요를 충족한다는 근거를 조금 더 "
                "설명해 달라는 입장입니다."
            )
        else:
            reply = (
                "감독님의 생각은 이해했습니다. 하지만 제가 어떤 역할과 기회를 "
                "받게 되는지 조금 더 구체적으로 듣고 싶습니다."
            )
        if delta < 0:
            if event_type == "trade_offer":
                reply = "다만 상대 구단의 반응은 다소 부정적입니다. " + reply
            else:
                reply = "그 말씀은 제 입장을 충분히 고려한 제안으로 들리지 않습니다. " + reply
        return {
            "reply": reply,
            "attitude_delta": delta,
            "reason": "대화의 구체성·존중·상호 이익을 규칙 기반으로 평가했습니다.",
            "source": "rules",
        }
