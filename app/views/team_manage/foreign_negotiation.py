"""선수 상세 페이지의 통합 외국인 선수 계약 협상 화면."""

from app.views.contract_negotiation import AgentContractNegotiationWidget


class ForeignNegotiationPanel(AgentContractNegotiationWidget):
    """국내 FA와 동일한 에이전트 협의·계약·서명 흐름을 사용한다."""
    pass
