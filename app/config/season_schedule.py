"""2025-26 KBO 오프시즌 달력과 게임 진행용 주요 일정."""

from datetime import date

CALENDAR_START = date(2025, 11, 1)
CALENDAR_END = date(2026, 2, 28)

# 2026년부터 비활동기간 종료일이 1월 31일에서 1월 24일로 변경됐다.
SEASON_PHASES = (
    (date(2025, 11, 1), date(2025, 11, 18), "FA·전력 분석", "FA 공시와 2차 드래프트 준비"),
    (date(2025, 11, 19), date(2025, 11, 30), "선수단 정리", "2차 드래프트·보류선수 명단"),
    (date(2025, 12, 1), date(2025, 12, 31), "계약과 편성", "외국인 선수·연봉·시즌 일정"),
    (date(2026, 1, 1), date(2026, 1, 24), "비활동기간·캠프 준비", "메디컬·훈련 계획·캠프 명단"),
    (date(2026, 1, 25), date(2026, 2, 21), "1차 캠프", "체력·기술 훈련과 선수 평가"),
    (date(2026, 2, 22), date(2026, 2, 28), "2차 캠프", "실전 점검과 연습경기"),
)

OFFICIAL_SOURCES = {
    "fa": "https://www.koreabaseball.com/MediaNews/Notice/View.aspx?bdSe=11762",
    "second_draft": "https://www.koreabaseball.com/MediaNews/Notice/View.aspx?bdSe=11771",
    "awards": "https://www.koreabaseball.com/MediaNews/Notice/View.aspx?bdSe=11766",
    "golden_glove": "https://www.koreabaseball.com/MediaNews/Notice/View.aspx?bdSe=11782",
    "regular_schedule": "https://www.koreabaseball.com/MediaNews/Notice/View.aspx?bdSe=11794",
    "exhibition": "https://www.koreabaseball.com/MediaNews/Notice/View.aspx?bdSe=11823",
    "national_team": "https://www.koreabaseball.com/MediaNews/Notice/View.aspx?bdSe=11721",
    "national_team_callup": "https://www.koreabaseball.com/MediaNews/Notice/View.aspx?bdSe=11747",
}


def _event(event_id, category, title, detail, task, importance="normal", *,
           event_type="club_task", inbox=True, requires_action=False,
           source_key=None, workflow="notice", choices=()):
    return {
        "event_id": event_id, "category": category, "title": title,
        "detail": detail, "task": task, "importance": importance,
        "event_type": event_type, "inbox": inbox,
        "requires_action": requires_action,
        "source_url": OFFICIAL_SOURCES.get(str(source_key)) if source_key else None,
        "workflow": workflow,
        "choices": tuple(choices),
    }


SEASON_EVENTS = {
    date(2025, 11, 1): (_event(
        "offseason_open", "구단", "스토브리그 업무 시작",
        "선수단과 프런트의 2026시즌 준비가 시작됩니다.",
        "전력·계약·부상 현황을 먼저 점검하세요.", "high",
        requires_action=True, workflow="offseason_strategy",
        choices=(
            ("win_now", "즉시 전력 우선", "FA와 검증된 주전 영입에 자원을 집중합니다."),
            ("balanced", "균형 보강", "주전 보강과 유망주 보호를 함께 추진합니다."),
            ("development", "육성 중심", "샐러리캡 여유와 유망주 기회를 우선합니다."),
        ),
    ), _event(
        "national_team_roster", "국가대표", "K-BASEBALL SERIES 최종 소집 명단",
        "부상 교체를 반영한 대한민국 대표팀 최종 소집 인원은 34명입니다.",
        "우리 구단 차출 선수와 합류일, 부상 교체 명단을 확인하세요.", "high",
        event_type="league_notice", source_key="national_team_callup",
        workflow="national_team_roster",
    )),
    date(2025, 11, 2): (_event(
        "coaching_staff_review", "스태프", "2026 코칭스태프 업무 배정",
        "현재 코칭스태프의 전문 분야와 업무량을 검토합니다.",
        "타격·투수·수비 훈련을 담당할 코치를 각각 배정하세요.", "high",
        requires_action=True, workflow="training_center_staff",
        choices=((
            "complete_staff_review", "코치 업무 배정 완료",
            "훈련 센터에서 타격·투수·수비 담당 코치를 확정합니다.",
        ),),
    ), _event(
        "national_team_callup", "국가대표", "대표팀 소집·훈련 시작",
        "대표팀이 고양 국가대표야구훈련장에서 첫 훈련을 시작합니다.",
        "차출 선수는 구단 훈련에서 분리되며 대표팀 일정으로 관리됩니다.",
        event_type="national_team", source_key="national_team_callup",
        workflow="national_team_callup",
    )),
    date(2025, 11, 3): (_event("roster_audit", "선수단", "보류선수·계약 현황 1차 검토", "FA 자격과 계약 만료, 보류 여부를 함께 검토합니다.", "방출 후보와 우선 협상 선수를 분류하세요.", "high", requires_action=True, workflow="roster_audit"),),
    date(2025, 11, 4): (_event(
        "offseason_training_plan", "훈련", "11월 팀·개인 훈련 계획 확정",
        "오프시즌 훈련 중점과 휴식 정책, 선수별 성장 과제를 설정합니다.",
        "팀 훈련 계획을 저장하고 핵심 선수 최소 3명의 개인 훈련을 배정하세요.",
        "high", requires_action=True, workflow="training_center_plan",
        choices=((
            "complete_training_plan", "훈련 계획 제출",
            "팀 훈련과 최소 3명의 개인 훈련 계획을 확정합니다.",
        ),),
    ), _event(
        "national_team_late_join", "국가대표", "LG·한화 대표 선수 합류",
        "한국시리즈를 마친 LG와 한화 소속 대표 선수들이 고척 훈련부터 합류합니다.",
        "우리 구단 차출 선수의 회복 상태와 대표팀 훈련 부하를 확인하세요.",
        event_type="national_team", source_key="national_team_callup",
        workflow="national_team_callup",
    )),
    date(2025, 11, 5): (_event(
        "fa_eligible", "KBO", "2026 FA 자격 선수 명단 확인",
        "FA 자격 대상자가 공시되고 승인 신청 절차가 진행됩니다.",
        "내부 FA의 잔류 우선순위와 보상 위험을 검토하세요.", "high",
        event_type="league_notice", requires_action=True,
        workflow="fa_eligibility", choices=(
            ("retain_core", "핵심 내부 FA 우선", "주전급 내부 FA의 잔류 협상을 가장 먼저 준비합니다."),
            ("retain_all", "내부 FA 전원 잔류 검토", "내부 FA 모두에게 잔류 조건을 검토하되 예산을 엄격히 관리합니다."),
            ("market_test", "시장 가치 우선", "선수별 시장 가격과 보상 부담을 확인한 뒤 선별 대응합니다."),
        ),
    ),),
    date(2025, 11, 8): (
        _event(
            "fa_approved", "KBO", "2026 FA 승인 선수 21명 공시",
            "KBO가 FA 권리를 행사한 21명을 승인 선수로 공시했습니다.",
            "외부 영입 한도 3명과 보상 조건을 반영해 후보군을 확정하세요.",
            "high", event_type="official", requires_action=True,
            source_key="fa", workflow="fa_approved", choices=(
                ("star_targets", "핵심 전력 후보군", "능력과 포지션 수요가 높은 주전급 FA를 우선 추적합니다."),
                ("value_targets", "효율형 후보군", "연봉·보상선수·샐러리캡 부담이 낮은 후보를 우선 추적합니다."),
                ("internal_targets", "내부 FA 집중", "외부 접촉보다 원소속 FA 잔류 협상에 집중합니다."),
            ),
        ),
        _event("korea_czech_one", "국가대표", "K-BASEBALL SERIES · 대한민국 vs 체코 1차전", "경기 종료 · 대한민국이 체코에 3-0으로 승리했습니다. 대표팀 마운드는 17탈삼진·3피안타 완봉을 합작했습니다.", "대표 선수의 기용과 컨디션을 확인하세요.", event_type="game", inbox=False, source_key="national_team", workflow="national_game"),
    ),
    date(2025, 11, 9): (
        _event("fa_market_open", "FA", "2026 FA 협상 시장 개장", "모든 구단이 승인 FA 선수와 협상할 수 있습니다.", "예산과 보상선수 위험을 확인한 뒤 영입 기조를 결정하세요.", "high", event_type="market", requires_action=True, source_key="fa", workflow="fa_market", choices=(
            ("aggressive", "핵심 FA 적극 영입", "A·B등급 주전급 선수부터 접촉합니다."),
            ("value", "가성비 중심 탐색", "보상 부담과 샐러리캡 효율을 우선합니다."),
            ("internal_first", "내부 FA 우선", "원소속 FA 잔류 협상을 먼저 진행합니다."),
        )),
        _event("korea_czech_two", "국가대표", "K-BASEBALL SERIES · 대한민국 vs 체코 2차전", "경기 종료 · 대한민국이 장단 17안타로 체코에 11-1 승리를 거두며 2연전을 모두 이겼습니다.", "소속 대표 선수의 피로와 경기 내용을 점검하세요.", event_type="game", inbox=False, source_key="national_team", workflow="national_game"),
    ),
    date(2025, 11, 12): (
        _event("second_draft_protect", "구단", "2차 드래프트 보호선수 35인 확정", "육성선수와 자격 제외 선수를 검토해 보호 명단을 완성합니다.", "즉시전력과 유망주의 유출 위험을 비교하세요.", "high", requires_action=True, workflow="second_draft_protection"),
        _event(
            "national_team_departure", "국가대표", "대표팀 일본 원정 출국",
            "체코전을 마친 대표팀이 일본과의 2연전을 위해 도쿄로 이동합니다.",
            "원정 이동에 따른 차출 선수의 피로와 회복 계획을 확인하세요.",
            event_type="national_team", source_key="national_team_callup",
            workflow="national_team_travel",
        ),
    ),
    date(2025, 11, 15): (_event("korea_japan_one", "국가대표", "K-BASEBALL SERIES · 대한민국 vs 일본 1차전", "경기 종료 · 대한민국이 일본에 4-11로 역전패했습니다. 안현민과 송성문이 연속 타자 홈런을 기록했습니다.", "대표 선수의 경기력과 부상 위험을 확인하세요.", "high", event_type="game", inbox=False, source_key="national_team", workflow="national_game"),),
    date(2025, 11, 16): (_event("korea_japan_two", "국가대표", "K-BASEBALL SERIES · 대한민국 vs 일본 2차전", "경기 종료 · 대한민국과 일본이 7-7로 비겼습니다. 김주원이 9회 2사에서 동점 홈런을 기록했습니다.", "복귀 예정 선수의 피로 회복 계획을 준비하세요.", "high", event_type="game", inbox=False, source_key="national_team", workflow="national_game"),),
    date(2025, 11, 17): (_event(
        "national_team_return", "국가대표", "대표팀 일정 종료·소속팀 복귀",
        "일본 원정을 마친 대표 선수들이 소속 구단으로 복귀합니다.",
        "복귀 선수의 누적 피로와 컨디션을 확인해 회복 훈련을 배정하세요.",
        "high", event_type="national_team", source_key="national_team_callup",
        workflow="national_team_return",
    ),),
    date(2025, 11, 19): (_event("second_draft", "KBO", "2025 KBO 2차 드래프트", "10개 구단이 보호선수 외 전력을 대상으로 지명을 진행합니다.", "포지션 수요와 양도금 4억·3억·2억원을 함께 판단하세요.", "high", event_type="official", requires_action=True, source_key="second_draft", workflow="second_draft_results"),),
    date(2025, 11, 21): (_event(
        "draft_integration", "선수단", "2차 드래프트 합류·이탈 후속 정리",
        "지명 결과를 선수단 깊이와 연봉 계획에 반영합니다.",
        "신입 선수 역할과 대체 보강 지점을 정하세요.", "high",
        requires_action=True, workflow="draft_integration", choices=(
            ("first_team_competition", "1군 경쟁 우선", "합류 선수를 즉시 1군 경쟁에 포함하고 이탈 포지션을 보강합니다."),
            ("depth_first", "선수층 보강", "합류 선수는 백업 전력으로 시작하고 부족 포지션의 깊이를 우선합니다."),
            ("development_first", "퓨처스 적응", "합류 선수를 퓨처스 육성조에 배치해 장기 적응을 우선합니다."),
        ),
    ),),
    date(2025, 11, 24): (_event("kbo_awards", "KBO", "2025 KBO 시상식", "한화 코디 폰세가 정규시즌 MVP, KT 안현민이 신인상을 수상했습니다. 개인 부문 1위와 KBO 수비상 수상자도 함께 시상했습니다.", "수상 선수의 위상과 다음 시즌 경쟁 구도를 확인하세요.", event_type="official", source_key="awards", workflow="awards"),),
    date(2025, 11, 25): (_event("reserve_submit", "구단", "보류선수 명단 제출 점검", "다음 시즌 계약 권리를 유지할 선수 명단을 최종 검토합니다.", "방출·육성 전환·재계약 대상을 확정하세요.", "high", requires_action=True, workflow="reserve_submission"),),
    date(2025, 11, 27): (_event(
        "november_review", "구단", "11월 전력 정비 결산",
        "FA와 2차 드래프트 결과를 전력표에 반영합니다.",
        "남은 보강 지점을 이사회에 보고하세요.", "high",
        requires_action=True, workflow="november_review", choices=(
            ("pitching_need", "투수진 보강", "12월 시장에서 선발·불펜 뎁스를 우선 보강합니다."),
            ("batting_need", "야수진 보강", "12월 시장에서 타선과 포지션 뎁스를 우선 보강합니다."),
            ("budget_hold", "예산 유지", "현재 전력을 유지하고 외국인·연봉 협상용 예산을 남깁니다."),
        ),
    ),),
    date(2025, 11, 30): (_event("reserve_publication", "KBO", "보류선수 명단 공시", "보류 명단을 기준으로 계약 가능 선수와 자유계약선수를 구분합니다.", "시장 선수와 내부 계약 대상을 다시 확인하세요.", "high", event_type="league_notice", workflow="reserve_publication"),),
    date(2025, 12, 1): (_event("foreign_market", "외국인", "외국인 선수 시장 집중 조사", "재계약 대상과 신규 후보의 기량·부상·적응 위험을 비교합니다.", "스카우트 보고서로 투타 우선순위를 정하세요.", "high", requires_action=True),),
    date(2025, 12, 5): (_event("payroll_review", "재정", "선수단 총연봉·계약 예산 점검", "FA와 외국인 협상 이후 남은 예산을 재산정합니다.", "연봉 상한과 추가 보강 여력을 확정하세요."),),
    date(2025, 12, 9): (_event("golden_glove", "KBO", "2025 KBO 골든글러브 시상식", "포지션별 최고 활약 선수의 수상자가 발표됩니다.", "수상 결과와 포지션별 경쟁력을 확인하세요.", event_type="official", source_key="golden_glove"),),
    date(2025, 12, 15): (_event("contract_checkpoint", "계약", "연봉·외국인 계약 중간 점검", "미계약 선수와 외국인 선수 협상 현황을 정리합니다.", "계약 상한과 결렬 시 대체 후보를 확정하세요.", "high", requires_action=True),),
    date(2025, 12, 19): (_event("regular_schedule", "KBO", "2026 정규시즌 일정 발표", "팀당 144경기, 총 720경기 일정이 발표됩니다. 개막일은 3월 28일입니다.", "개막 시리즈와 장거리 원정 구간을 분석하세요.", "high", event_type="official", source_key="regular_schedule"),),
    date(2025, 12, 22): (_event("season_plan", "전술", "2026 시즌 운용 계획 회의", "일정에 맞춰 선발 로테이션과 휴식 구간을 설계합니다.", "개막 후 첫 달의 투수 운용 초안을 작성하세요."),),
    date(2025, 12, 29): (_event("year_end_review", "구단", "연말 선수단 평가", "오프시즌 전력 정비 결과와 잔여 과제를 결산합니다.", "1월 캠프 준비 과제를 전달하세요."),),
    date(2026, 1, 2): (_event("rookie_orientation", "선수단", "신인·신규 합류 선수 오리엔테이션", "신인과 이적 선수에게 구단 운영 원칙을 전달합니다.", "적응 지원과 육성 담당자를 배정하세요."),),
    date(2026, 1, 5): (_event("conditioning_plan", "훈련", "개인 컨디셔닝 계획 제출", "개인 훈련 결과와 캠프 목표를 수집합니다.", "부상 이력에 맞춰 캠프 훈련량을 조정하세요."),),
    date(2026, 1, 12): (_event("medical_check", "의료", "캠프 전 메디컬 점검", "투수 어깨·팔꿈치와 야수 주요 부위 상태를 확인합니다.", "제한 훈련 대상과 재활조를 분류하세요.", "high", requires_action=True),),
    date(2026, 1, 16): (_event("salary_checkpoint", "계약", "연봉 협상 최종 점검", "캠프 출발 전 미계약 국내선수의 협상 진행도를 확인합니다.", "이견이 큰 선수의 후속 대응을 결정하세요."),),
    date(2026, 1, 19): (_event("camp_roster", "캠프", "스프링캠프 참가 명단 확정", "1차 캠프 참가 선수와 코칭스태프를 확정합니다.", "유망주 초청과 포지션 경쟁 구도를 결정하세요.", "high", requires_action=True),),
    date(2026, 1, 22): (_event("camp_advance", "캠프", "캠프 선발대·장비 출발", "운영진과 장비가 먼저 이동해 현지 준비를 시작합니다.", "시설·숙소·의료 장비 상태를 확인하세요."),),
    date(2026, 1, 24): (_event("inactive_period_end", "KBO", "비활동기간 종료", "선수단 단체훈련 재개를 앞둔 마지막 준비일입니다.", "훈련조와 이동 명단을 최종 확인하세요.", "high", event_type="league_notice"),),
    date(2026, 1, 25): (_event("camp_one_open", "캠프", "10개 구단 1차 스프링캠프 시작", "체력과 기본기 중심의 1차 캠프가 시작됩니다.", "선수별 훈련 강도와 평가 항목을 설정하세요.", "high", requires_action=True),),
    date(2026, 1, 31): (_event("camp_week_one", "캠프", "1차 캠프 첫 주 평가", "선수들의 컨디션과 훈련 적응도를 점검합니다.", "과부하 선수와 페이스가 느린 선수를 조정하세요."),),
    date(2026, 2, 4): (_event("exhibition_schedule", "KBO", "2026 시범경기 일정 발표", "3월 12일부터 24일까지 팀당 12경기, 총 60경기로 편성됩니다.", "이동 일정과 투수 운용안을 준비하세요.", "high", event_type="official", source_key="exhibition"),),
    date(2026, 2, 7): (_event("bullpen_defense_review", "캠프", "불펜·수비 1차 평가", "투수 피칭과 야수 팀 수비 완성도를 점검합니다.", "실전조 승격 후보를 정하세요."),),
    date(2026, 2, 14): (_event("intrasquad_game", "경기", "청백전·내부 평가전", "첫 내부 실전으로 경기 감각을 확인합니다.", "타순과 수비 경쟁 결과를 기록하세요.", "high"),),
    date(2026, 2, 19): (_event("camp_two_roster", "캠프", "2차 캠프 이동 명단 확정", "실전 중심 2차 캠프 참가 선수단을 결정합니다.", "1군 경쟁 명단과 잔류조를 확정하세요.", "high", requires_action=True),),
    date(2026, 2, 21): (_event("camp_one_close", "캠프", "1차 캠프 종료 평가", "체력·기술 훈련 성과를 종합 평가합니다.", "선수별 보고서와 다음 목표를 확정하세요."),),
    date(2026, 2, 22): (_event("camp_move", "캠프", "2차 캠프 이동", "선수단이 실전 훈련지로 이동합니다.", "회복 훈련과 첫 연습경기를 준비하세요."),),
    date(2026, 2, 23): (_event("camp_two_open", "캠프", "2차 스프링캠프 시작", "연습경기와 실전 전술 중심 캠프가 시작됩니다.", "개막 엔트리 경쟁 기준을 전달하세요.", "high"),),
    date(2026, 2, 24): (_event("practice_game_window", "경기", "대외 연습경기 구간 진입", "타 구단·현지 팀과 연습경기로 실전 감각을 끌어올립니다.", "선발 후보를 짧은 이닝부터 투입하세요."),),
    date(2026, 2, 28): (_event("february_review", "캠프", "2월 실전 평가", "2차 캠프 첫 주의 투타 실전을 결산합니다.", "시범경기 전 마지막 보완 대상을 정하세요.", "high", requires_action=True),),
}


def phase_for(day):
    for start, end, name, description in SEASON_PHASES:
        if start <= day <= end:
            return name, description
    return "시즌 준비", "구단 운영 일정"


def events_for(day, *, inbox_only=False):
    events = SEASON_EVENTS.get(day, ())
    return tuple(e for e in events if e.get("inbox", True)) if inbox_only else events


def next_event_after(day):
    event_day = min((d for d in SEASON_EVENTS if d > day), default=None)
    return (event_day, SEASON_EVENTS[event_day]) if event_day else (None, ())
