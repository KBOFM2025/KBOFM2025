"""2025 공개 캠프 보도 기반. 세션 배열과 미공개 휴식 주기는 게임 모델이다."""

PROFILES = {
    "KIA": ("체력·기본기와 투수 스트라이크", "체력", "투수 제구", 4,
            "https://www.osen.co.kr/article/G1112701468"),
    "삼성": ("젊은 선수의 기술 약점 반복 보완", "타격 기술", "내야 수비", 3,
            "https://www.xportsnews.com/article/2080280"),
    "LG": ("주전 휴식과 선별 육성 훈련", "회복", "타격 기술", 3,
           "https://www.sportsseoul.com/news/read/1560643"),
    "두산": ("투수 스트라이크와 연습경기 점검", "투수 제구", "라이브 BP", 3,
            "https://www.osen.co.kr/article/G1112694590"),
    "KT": ("개인 맞춤 기술·전술과 실전 점검", "자율 훈련", "팀 전술", 3,
           "https://www.yna.co.kr/view/AKR20251015140500007"),
    "SSG": ("타격 로테이션과 타구 질 점검", "타격 기술", "장타 훈련", 4,
            "https://www.sportschosun.com/baseball/2025-12-09/202512090100055860008567"),
    "롯데": ("수비 기본기 집중 보완", "내야 수비", "외야 수비", 3,
            "https://www.kookje.co.kr/news2011/asp/newsbody.asp?code=0600&key=20251125.22015007831"),
    "한화": ("포지션별 캠프 편성과 연습경기 점검", "팀 전술", "라이브 BP", 3,
            "https://www.mt.co.kr/sports/2025/11/05/2025110513244795041"),
    "NC": ("투타 분리·반복 기술과 투수 루틴", "투수 제구", "타격 기술", 3,
           "https://www4.osen.co.kr/article/G1112684843"),
    "키움": ("기본기·개인 기술과 부상 예방", "타격 기술", "회복", 3,
            "https://m.heroesbaseball.co.kr/story/heroesNews/view.do?num=22365"),
}


def club_profile(team):
    key = next((key for key in PROFILES if team.upper().startswith(key)), "KIA")
    theme, first, second, cycle, source = PROFILES[key]
    return dict(club=key, theme=theme, first=first, second=second,
                cycle=cycle, source=source,
                note="세션·강도는 게임용 재구성. KIA·SSG 외 3일 훈련/1일 휴식은 설계 가정입니다.")
