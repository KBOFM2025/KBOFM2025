"""2025 선수계약 메타데이터와 외국인 선수 공식 발표 계약액."""

REGULAR_CONTRACT_SOURCE = (
    "https://6ptotvmi5753.edge.naverncp.com/KBO_FILE/ebook/pdf/"
    "2025_%EC%95%BC%EA%B5%AC%EA%B7%9C%EC%95%BD.pdf"
)
OPENING_FOREIGN_SOURCE = "https://www.yna.co.kr/view/AKR20241226074100007"
USD_KRW_REFERENCE_RATE = 1380


def _foreign(total, salary=None, bonus=0, option=0, transfer=0, source=OPENING_FOREIGN_SOURCE):
    return {
        "total": total, "salary": salary or 0, "bonus": bonus, "option": option,
        "transfer": transfer, "source": source, "breakdown_known": salary is not None,
    }


FOREIGN_CONTRACTS_2025 = {
    ("KIA 타이거즈", "올러"): _foreign(1_000_000, 600_000, 200_000, 200_000),
    ("KIA 타이거즈", "네일"): _foreign(1_800_000, 1_200_000, 400_000, 200_000),
    ("KIA 타이거즈", "위즈덤"): _foreign(1_000_000, 800_000, 200_000),
    ("삼성 라이온즈", "후라도"): _foreign(1_000_000, 700_000, 300_000),
    ("삼성 라이온즈", "디아즈"): _foreign(800_000, 500_000, 100_000, 200_000),
    ("삼성 라이온즈", "가라비토"): _foreign(
        556_666, 356_666, transfer=200_000,
        source="https://www.newspim.com/news/view/20250619000390",
    ),
    ("LG 트윈스", "치리노스"): _foreign(1_000_000, 800_000, 200_000),
    ("LG 트윈스", "오스틴"): _foreign(1_700_000, 1_200_000, 300_000, 200_000),
    ("LG 트윈스", "톨허스트"): _foreign(
        370_000, 270_000, transfer=100_000,
        source="https://www.starnewskorea.com/sports/2025/08/13/2025081308072796555",
    ),
    ("두산 베어스", "잭로그"): _foreign(800_000, 700_000, 100_000),
    ("두산 베어스", "콜어빈"): _foreign(1_000_000, 800_000, 200_000),
    ("두산 베어스", "케이브"): _foreign(1_000_000, 800_000, 200_000),
    ("KT 위즈", "헤이수스"): _foreign(1_000_000, 800_000, 200_000),
    ("KT 위즈", "패트릭"): _foreign(
        277_000,
        source="https://yagongso.com/2025-kbo%EB%A6%AC%EA%B7%B8-%EC%99%B8%EA%B5%AD%EC%9D%B8-%EC%84%A0%EC%88%98-%EC%8A%A4%EC%B9%B4%EC%9A%B0%ED%8C%85-%EB%A6%AC%ED%8F%AC%ED%8A%B8-kt-%EC%9C%84%EC%A6%88-%ED%8C%A8%ED%8A%B8%EB%A6%AD/",
    ),
    ("KT 위즈", "스티븐슨"): _foreign(
        200_000, source="https://yagongso.com/?p=24450",
    ),
    ("SSG 랜더스", "화이트"): _foreign(1_000_000, 1_000_000),
    ("SSG 랜더스", "앤더슨"): _foreign(1_200_000, 1_150_000, option=50_000),
    ("SSG 랜더스", "에레디아"): _foreign(1_800_000, 1_600_000, option=200_000),
    ("롯데 자이언츠", "레이예스"): _foreign(1_250_000, 1_000_000, option=250_000),
    ("롯데 자이언츠", "감보아"): _foreign(
        400_000, 250_000, bonus=50_000, transfer=100_000,
        source="https://www.koreabaseball.com/Record/Player/PitcherDetail/Total.aspx?playerId=55532",
    ),
    ("롯데 자이언츠", "벨라스케즈"): _foreign(
        330_000,
        source="https://www.newspim.com/news/view/20250807000381",
    ),
    ("한화 이글스", "폰세"): _foreign(1_000_000, 800_000, 200_000),
    ("한화 이글스", "와이스"): _foreign(950_000, 600_000, 150_000, 200_000),
    ("한화 이글스", "리베라토"): _foreign(
        205_000,
        source="https://www.yna.co.kr/view/AKR20250719053100007",
    ),
    ("NC 다이노스", "로건"): _foreign(1_000_000, 560_000, 140_000, 300_000),
    ("NC 다이노스", "라일리"): _foreign(900_000, 520_000, 130_000, 250_000),
    ("NC 다이노스", "데이비슨"): _foreign(1_500_000, 1_200_000, option=300_000),
    ("키움 히어로즈", "카디네스"): _foreign(600_000, 450_000, option=150_000),
    ("키움 히어로즈", "알칸타라"): _foreign(
        400_000, 250_000, option=150_000,
        source="https://www.sportsworldi.com/newsView/20250519509233",
    ),
    ("키움 히어로즈", "메르세데스"): _foreign(
        280_000,
        source="https://sports.news.nate.com/view/20250730n15812",
    ),
}


# 2025-10-31 시점에 공개적으로 계약 기간이 남은 주요 FA·비FA 다년계약.
# 명시되지 않은 선수는 KBO 통일계약서에 따라 해당 연도 11월 30일 만료다.
MULTI_YEAR_CONTRACT_ENDS = {
    ("KIA 타이거즈", "김태군"): ("2026-11-30", "비FA 다년계약"),
    ("KIA 타이거즈", "김선빈"): ("2026-11-30", "FA 다년계약"),
    ("KIA 타이거즈", "나성범"): ("2027-11-30", "FA 다년계약"),
    ("삼성 라이온즈", "구자욱"): ("2026-11-30", "비FA 다년계약"),
    ("삼성 라이온즈", "김재윤"): ("2027-11-30", "FA 다년계약"),
    # 비FA 다년계약 합의 후 2023시즌 종료 뒤 FA 승인·계약으로 전환됐다.
    ("LG 트윈스", "오지환"): ("2029-11-30", "FA 다년계약"),
    ("LG 트윈스", "박동원"): ("2026-11-30", "FA 다년계약"),
    ("LG 트윈스", "임찬규"): ("2027-11-30", "FA 다년계약"),
    ("LG 트윈스", "함덕주"): ("2027-11-30", "FA 다년계약"),
    ("두산 베어스", "정수빈"): ("2026-11-30", "FA 다년계약"),
    ("두산 베어스", "양의지"): ("2028-11-30", "FA 4+2년 계약"),
    ("두산 베어스", "양석환"): ("2029-11-30", "FA 4+2년 계약"),
    ("KT 위즈", "고영표"): ("2028-11-30", "비FA 다년계약"),
    ("KT 위즈", "허경민"): ("2028-11-30", "FA 다년계약"),
    ("KT 위즈", "김상수"): ("2026-11-30", "FA 다년계약"),
    # 2025시즌 중 FA 취득 전에 체결한 2026~2027년 연장 계약.
    ("SSG 랜더스", "김광현"): ("2027-11-30", "비FA 2년 계약"),
    ("SSG 랜더스", "김성현"): ("2026-11-30", "비FA 다년계약"),
    ("SSG 랜더스", "문승원"): ("2026-11-30", "비FA 다년계약"),
    ("SSG 랜더스", "박종훈"): ("2026-11-30", "비FA 다년계약"),
    ("SSG 랜더스", "한유섬"): ("2026-11-30", "비FA 다년계약"),
    ("SSG 랜더스", "최정"): ("2028-11-30", "FA 다년계약"),
    ("SSG 랜더스", "노경은"): ("2027-11-30", "FA 2+1년 계약"),
    ("롯데 자이언츠", "박세웅"): ("2027-11-30", "비FA 다년계약"),
    ("롯데 자이언츠", "전준우"): ("2027-11-30", "FA 다년계약"),
    ("롯데 자이언츠", "유강남"): ("2026-11-30", "FA 다년계약"),
    ("롯데 자이언츠", "노진혁"): ("2026-11-30", "FA 다년계약"),
    ("롯데 자이언츠", "김원중"): ("2028-11-30", "FA 다년계약"),
    ("롯데 자이언츠", "구승민"): ("2028-11-30", "FA 2+2년 계약"),
    ("한화 이글스", "류현진"): ("2031-11-30", "비FA 다년계약"),
    ("한화 이글스", "최재훈"): ("2026-11-30", "FA 5년 계약"),
    ("한화 이글스", "채은성"): ("2028-11-30", "FA 다년계약"),
    ("한화 이글스", "안치홍"): ("2029-11-30", "FA 4+2년 계약"),
    ("한화 이글스", "엄상백"): ("2028-11-30", "FA 다년계약"),
    ("한화 이글스", "심우준"): ("2028-11-30", "FA 다년계약"),
    ("NC 다이노스", "박건우"): ("2027-11-30", "FA 다년계약"),
    ("NC 다이노스", "박민우"): ("2030-11-30", "FA 5+3년 계약"),
    ("NC 다이노스", "구창모"): ("2029-11-30", "비FA 6+1년 계약"),
    ("NC 다이노스", "임정호"): ("2027-11-30", "FA 다년계약"),
    ("NC 다이노스", "김성욱"): ("2026-11-30", "FA 다년계약"),
    ("키움 히어로즈", "최주환"): ("2028-11-30", "비FA 2+1+1년 계약"),
    ("키움 히어로즈", "송성문"): ("2031-11-30", "비FA 다년계약"),
    ("키움 히어로즈", "이형종"): ("2026-11-30", "FA 다년계약"),
    ("키움 히어로즈", "원종현"): ("2026-11-30", "FA 다년계약"),
}


# '+N년'은 자동 보장 기간이 아니라 상호 합의·조건 충족 등에 따른 연장 구간이다.
# FA 가능 시점을 최대 계약 종료일 하나로 단정하지 않도록 보장 종료일을 별도로 둔다.
MULTI_YEAR_OPTION_TERMS = {
    ("두산 베어스", "양의지"): ("2026-11-30", "2028-11-30"),
    ("두산 베어스", "양석환"): ("2027-11-30", "2029-11-30"),
    ("SSG 랜더스", "노경은"): ("2026-11-30", "2027-11-30"),
    ("롯데 자이언츠", "구승민"): ("2026-11-30", "2028-11-30"),
    ("한화 이글스", "안치홍"): ("2027-11-30", "2029-11-30"),
    ("NC 다이노스", "박민우"): ("2027-11-30", "2030-11-30"),
    ("NC 다이노스", "구창모"): ("2028-11-30", "2029-11-30"),
    ("키움 히어로즈", "최주환"): ("2026-11-30", "2028-11-30"),
}


CONTRACT_COLUMNS = {
    "contract_start_date": "TEXT DEFAULT ''",
    "contract_end_date": "TEXT DEFAULT ''",
    "contract_type": "TEXT DEFAULT ''",
    "contract_years": "INTEGER DEFAULT 1",
    "contract_total": "INTEGER DEFAULT 0",
    "contract_currency": "TEXT DEFAULT 'KRW'",
    "contract_salary": "INTEGER DEFAULT 0",
    "contract_bonus": "INTEGER DEFAULT 0",
    "contract_option": "INTEGER DEFAULT 0",
    "contract_transfer_fee": "INTEGER DEFAULT 0",
    "contract_source_url": "TEXT DEFAULT ''",
    "contract_note": "TEXT DEFAULT ''",
}


def apply_contract_metadata(connection):
    """모든 선수에 계약 만료를 부여하고 공개 다년·외국인 계약을 덮어쓴다."""
    columns = {row[1] for row in connection.execute("PRAGMA table_info(players)")}
    for name, declaration in CONTRACT_COLUMNS.items():
        if name not in columns:
            connection.execute(f"ALTER TABLE players ADD COLUMN {name} {declaration}")
    connection.execute(
        """UPDATE players SET
        contract_start_date=CASE WHEN contract_start_date='' THEN '2025-02-01' ELSE contract_start_date END,
        contract_end_date=CASE WHEN contract_end_date='' THEN '2025-11-30' ELSE contract_end_date END,
        contract_type=CASE WHEN contract_type='' THEN '연 단위 선수계약' ELSE contract_type END,
        contract_years=CASE WHEN contract_years<1 THEN 1 ELSE contract_years END,
        contract_currency=CASE WHEN contract_currency='' THEN 'KRW' ELSE contract_currency END,
        contract_salary=CASE WHEN contract_salary=0 THEN salary*10000 ELSE contract_salary END,
        contract_total=CASE WHEN contract_total=0 THEN salary*10000 ELSE contract_total END,
        contract_source_url=CASE WHEN contract_source_url='' THEN ? ELSE contract_source_url END,
        contract_note=CASE WHEN contract_note='' THEN 'KBO 통일계약서 기준 시즌 단위 계약' ELSE contract_note END
        """,
        (REGULAR_CONTRACT_SOURCE,),
    )
    for (team, name), (end_date, contract_type) in MULTI_YEAR_CONTRACT_ENDS.items():
        connection.execute(
            "UPDATE players SET contract_end_date=?,contract_type=?,contract_note=? WHERE team=? AND name=?",
            (end_date, contract_type, "공개 발표된 FA·비FA 다년계약 기간 반영", team, name),
        )
    for (team, name), data in FOREIGN_CONTRACTS_2025.items():
        published_pay = data["salary"] + data["bonus"]
        salary_10k = round((published_pay or data["total"]) * USD_KRW_REFERENCE_RATE / 10000)
        note = (
            "2025 구단 발표 계약액 · 금액 단위 USD"
            if data["breakdown_known"]
            else "2025 구단 발표 계약 총액 · 세부 내역 비공개 · 금액 단위 USD"
        )
        connection.execute(
            """UPDATE players SET salary=?,contract_start_date='2025-02-01',
            contract_end_date='2025-11-30',contract_type='외국인 선수 단년계약',
            contract_years=1,contract_total=?,contract_currency='USD',contract_salary=?,
            contract_bonus=?,contract_option=?,contract_transfer_fee=?,contract_source_url=?,
            contract_note=? WHERE team=? AND name=?""",
            (salary_10k, data["total"], data["salary"], data["bonus"], data["option"],
             data["transfer"], data["source"], note, team, name),
        )
