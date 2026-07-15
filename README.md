# KBO FM 2025

KBO 구단의 감독이 되어 구단을 운영하는 데스크톱 야구 매니지먼트 게임입니다.  
현재는 감독 생성, 구단 선택, 저장·불러오기와 기본 대시보드까지 구현되어 있습니다.

> 구단, 감독, 대표 선수와 관중 관련 정보는 **2026년 7월 15일 확인 기준**입니다.  
> 관중 수와 유튜브 구독자 수처럼 계속 변하는 값은 게임용 참고치로 표시됩니다.

## 현재 구현된 기능

- 새 게임 생성, 저장된 게임 불러오기와 삭제
- 10개 KBO 구단 선택 및 사용자 구단명 설정
- 염경엽·김경문·김성근 감독 스타일 프리셋
- 사용자 정의 감독 스타일 생성
- 11개 감독 능력치와 20점 척도 슬라이더
- 감독 능력을 6개 영역으로 묶은 레이더 차트
- 구단별 연고지, 구장, 창단 연도와 우승 기록
- 대표 선수, 구단 목표, 단장·팬·미디어 성향
- 구단별 마스코트 이미지와 이름
- SQLite 기반 선수 및 세이브 데이터 관리
- 정규리그 순위와 1군·2군·라인업 관리 화면
- 대시보드에서 시작 화면으로 돌아가기

## 실행 환경 준비

Python 3.10 이상을 권장합니다.

```powershell
python -m venv venv
venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install PySide6 pyinstaller
```

현재 저장소의 기존 `venv`는 로컬에 존재하지 않는 Python 3.9 경로를 가리킬 수 있습니다. 실행되지 않으면 해당 가상환경을 제거한 뒤 위 명령으로 다시 생성하세요.

## 실행

프로젝트 루트에서 다음 명령을 실행합니다.

```powershell
python main.py
```

최초 실행 시 `data/players.db`가 준비되며, 새 게임 저장 정보는 `data/kbo_fm_saves.db`에 기록됩니다.

## 실행 파일 빌드

PyInstaller 설정에는 `image` 폴더가 리소스로 포함되어 있습니다.

```powershell
pyinstaller main.spec
```

빌드 결과는 `dist` 폴더에서 확인할 수 있습니다.

## 프로젝트 구조

```text
KBO-FM-2025/
├─ main.py                    # 프로그램 실행 파일
├─ main.spec                  # PyInstaller 빌드 설정
├─ app/
│  ├─ application.py         # 외부에서 사용하는 공개 진입점
│  ├─ windows.py             # 새 게임, 시작 화면, 메인 창
│  ├─ manager_widgets.py     # 감독 카드, 능력 슬라이더, 레이더 차트
│  ├─ styles.py              # 공통 Qt 스타일
│  ├─ constants.py           # 애플리케이션 전역 상수
│  ├─ utils.py               # 리소스 경로와 데이터 변환 함수
│  ├─ config/
│  │  ├─ managers.py         # 감독 스타일과 능력치 설정
│  │  └─ teams.py            # 10개 구단 메타데이터
│  └─ views/
│     ├─ load_game.py        # 저장 불러오기와 삭제
│     ├─ league_rank.py      # 정규리그 순위
│     ├─ team_manager.py     # 선수단 관리 탭
│     └─ team_manage/        # 1군, 2군, 라인업과 선수 프로필
├─ database/
│  ├─ paths.py               # 데이터베이스 경로
│  ├─ player_database.py     # 선수 DB 생성과 초기화
│  ├─ roster_data.py         # 기본 선수단 데이터
│  └─ save_database.py       # 게임 저장 CRUD
├─ data/                     # SQLite 데이터베이스
└─ image/
   ├─ Yeom.png, Moon.png, SK.png
   └─ Mascort/               # 10개 구단 마스코트 원본 이미지
```

## 데이터 수정 위치

- 구단 정보: `app/config/teams.py`
- 감독 스타일과 능력치: `app/config/managers.py`
- 기본 선수단: `database/roster_data.py`
- 마스코트 이미지: `image/Mascort/`

구단 정보에는 실제 기록과 게임용 해석 데이터가 함께 들어 있습니다. 단장·팬 성향과 구단 목표는 게임 플레이를 위한 해석값이므로 실제 구단의 공식 평가와는 다를 수 있습니다.

## 다음 개발 목표

1. 타석 단위 경기 시뮬레이션 엔진
2. 타자·투수 능력치와 체력, 컨디션, 좌우 상성
3. 라인업, 대타, 도루와 투수 교체를 판단하는 감독 AI
4. 경기 기록 누적과 시즌 일정 진행
5. 중계 문장, 뉴스와 인터뷰 생성 기능

경기 결과는 재현과 밸런스 조정이 가능한 확률 기반 엔진으로 계산하고, 생성형 AI는 중계·뉴스·대화처럼 선택적인 콘텐츠에 사용하는 방향을 권장합니다.

## 개발 시 참고

- `main.py`는 계속 `app.application.run`만 호출합니다.
- 외부 코드에서는 가능하면 `app.windows`를 직접 참조하지 말고 `app.application`을 사용하세요.
- 화면 코드가 다시 커지면 `NewGameWizard`, `StartWindow`, `MainWindow`를 각각 별도 모듈로 분리하세요.
- DB 스키마를 변경할 때는 기존 세이브 파일과의 호환성을 먼저 확인하세요.

## 실행 화면 (감독 스타일 추천)
<img width="1191" height="761" alt="image" src="https://github.com/user-attachments/assets/59633bc0-be87-40d7-bbb3-d120c3f8a494" />

## 실행 화면 (감독 능력치 선택)
<img width="1170" height="736" alt="image" src="https://github.com/user-attachments/assets/cd4fa125-54cc-4f19-960f-0eac272aba51" />

## 실행 화면 (구단 선택)
<img width="1888" height="968" alt="image" src="https://github.com/user-attachments/assets/f0934777-3295-41a3-bb6f-b1aefacd8c38" />

