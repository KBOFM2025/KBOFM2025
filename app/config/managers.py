MANAGER_ABILITIES = {
    "batting": "타격 지도",
    "pitching": "투수 지도",
    "defense": "수비 지도",
    "baserunning": "주루 지도",
    "game_management": "경기 운영",
    "pitching_change": "투수 교체",
    "pinch_hitting": "대타 기용",
    "data_analysis": "데이터 분석",
    "development": "유망주 육성",
    "fitness": "훈련·체력 관리",
    "leadership": "리더십",
}

MANAGER_ABILITY_DESCRIPTIONS = {
    "batting": (
        "게임 반영: 타자 훈련의 컨택·장타 성장률, 타격 슬럼프 회복 속도에 적용됩니다. "
        "경기에서는 타자의 타석 결과 보정과 상대 투수 유형에 맞는 타격 지시 성공률에 영향을 줍니다."
    ),
    "pitching": (
        "게임 반영: 투수 훈련의 구위·제구·변화구 성장률과 부진 회복에 적용됩니다. "
        "경기에서는 볼넷·피홈런 억제와 투수의 보유 능력을 안정적으로 발휘할 확률에 영향을 줍니다."
    ),
    "defense": (
        "게임 반영: 수비 훈련, 포지션 적응과 실책 감소 속도에 적용됩니다. "
        "경기에서는 타구 처리, 병살 연결, 송구 정확도와 수비 범위 판정에 영향을 줍니다."
    ),
    "baserunning": (
        "게임 반영: 도루 시도 판단과 성공률, 타구에 따른 추가 진루 확률에 적용됩니다. "
        "수치가 높을수록 무리한 주루사와 견제사를 줄이고 득점권 진입 기회를 늘립니다."
    ),
    "game_management": (
        "게임 반영: 번트·히트앤드런·고의사구·수비 시프트 등 작전 선택에 적용됩니다. "
        "접전과 경기 후반에 감독 AI가 점수·이닝·상대 전력을 판단하는 정확도에 영향을 줍니다."
    ),
    "pitching_change": (
        "게임 반영: 투수의 체력 저하와 위기 신호를 감지하는 시점에 적용됩니다. "
        "상대 타자 좌우 유형, 불펜 컨디션과 연투 상황을 고려한 교체 성공률에 영향을 줍니다."
    ),
    "pinch_hitting": (
        "게임 반영: 대타 투입 시점과 벤치 타자 선택 정확도에 적용됩니다. "
        "상대 투수와의 좌우·능력치 매치업을 활용해 대타 타석의 기대 결과를 높입니다."
    ),
    "data_analysis": (
        "게임 반영: 상대 약점 분석, 추천 라인업과 선수 평가 보고서의 정확도에 적용됩니다. "
        "수치가 높을수록 숨겨진 컨디션·성장 가능성 정보가 정확해지고 잘못된 스카우팅 판단이 줄어듭니다."
    ),
    "development": (
        "게임 반영: 젊은 선수의 능력치 성장 속도와 잠재력 발현 이벤트에 적용됩니다. "
        "유망주의 약점을 보완하고 2군 선수가 1군 전력으로 성장할 가능성을 높입니다."
    ),
    "fitness": (
        "게임 반영: 경기 후 체력 회복, 훈련 피로 누적과 부상 발생 위험에 적용됩니다. "
        "수치가 높을수록 장기 시즌에서 주전의 컨디션을 유지하고 부상 복귀 기간을 단축합니다."
    ),
    "leadership": (
        "게임 반영: 팀 분위기, 선수 불만, 출전 시간 갈등과 연패 시 사기 변화에 적용됩니다. "
        "라커룸 결속력을 높이고 중요한 경기에서 선수들이 능력을 안정적으로 발휘하도록 돕습니다."
    ),
}

MANAGER_RADAR_GROUPS = {
    "공격": ("batting", "pinch_hitting"),
    "투수": ("pitching", "pitching_change"),
    "수비·주루": ("defense", "baserunning"),
    "경기 운영": ("game_management", "data_analysis"),
    "육성": ("development", "fitness"),
    "리더십": ("leadership",),
}

MANAGER_ABILITY_MAX = 20
MANAGER_POINT_BUDGET = 120

MANAGER_STYLES = {
    "염경엽": {
        "image": "Yeom_card.png",
        "focus_x": 0.34,
        "tagline": "데이터 기반 작전 야구",
        "description": "데이터 분석과 적극적인 주루, 대타 기용으로 승부하는 경기 운영형 감독",
        "abilities": {
            "batting": 10, "pitching": 8, "defense": 8, "baserunning": 16,
            "game_management": 16, "pitching_change": 10, "pinch_hitting": 14,
            "data_analysis": 16, "development": 6, "fitness": 8, "leadership": 8,
        },
    },
    "김경문": {
        "image": "Moon.png",
        "focus_x": 0.64,
        "tagline": "신뢰 중심 육성 야구",
        "description": "수비 안정과 유망주 성장, 선수단 신뢰를 중시하는 장기 육성형 감독",
        "abilities": {
            "batting": 10, "pitching": 10, "defense": 14, "baserunning": 12,
            "game_management": 12, "pitching_change": 10, "pinch_hitting": 10,
            "data_analysis": 6, "development": 16, "fitness": 8, "leadership": 12,
        },
    },
    "김성근": {
        "image": "SK.png",
        "focus_x": 0.50,
        "tagline": "강한 훈련과 투수 운용",
        "description": "세밀한 투수 교체와 강도 높은 훈련으로 전력을 끌어내는 관리형 감독",
        "abilities": {
            "batting": 8, "pitching": 18, "defense": 12, "baserunning": 8,
            "game_management": 14, "pitching_change": 16, "pinch_hitting": 8,
            "data_analysis": 10, "development": 8, "fitness": 12, "leadership": 6,
        },
    },
}
