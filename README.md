# KBO Manager 2025

2025년 KBO 리그를 배경으로 한 데스크톱 야구 구단 운영 시뮬레이션입니다. 감독을 생성하고 10개 구단 중 하나를 선택해 선수단과 라인업을 관리하는 게임을 목표로 개발하고 있습니다.

> 현재 개발 중인 프로젝트입니다. 실제 경기 시뮬레이션과 시즌 진행 기능은 아직 완성되지 않았습니다.

## 빠른 실행

### 1. 저장소 받기

```powershell
git clone https://github.com/KBOFM2025/KBOFM2025.git
cd KBOFM2025
```

ZIP으로 받은 경우 압축을 푼 뒤 PowerShell에서 해당 폴더로 이동하면 됩니다.

### 2. 가상환경과 패키지 설치

```powershell
python -m venv venv
venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install PySide6
```

PowerShell 실행 정책 때문에 가상환경 활성화가 차단되면 현재 창에서 다음 명령을 먼저 실행합니다.

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
venv\Scripts\Activate.ps1
```

### 3. 게임 실행

```powershell
python main.py
```

최초 실행 시 `data/players.db`가 자동으로 확인·갱신됩니다. 게임 저장 파일은 `data/kbo_fm_saves.db`에 생성됩니다.

## 핵심 기능

### 감독과 구단 생성

- 새 감독 프로필과 사용자 구단명 생성
- 염경엽·김경문·김성근 감독 스타일 프리셋
- 11개 감독 능력치와 20점 척도 포인트 배분
- 6개 감독 능력 영역 레이더 차트
- CAMP1·CAMP2 기준 게임 시작 시점 선택
- 10개 KBO 구단별 색상·마스코트·구단 정보 적용

### 선수단 관리

- 2025년 10월 31일 기준 10개 구단 선수 636명 수록
- KBO 선수 ID, 생년월일, 투타, 신장·체중, 경력 저장
- 1군·C팀 명단과 라인업 관리
- 승격·강등과 타순 변경 내용 SQLite DB 반영
- 구단 선택 단계에서 전체 선수단 미리보기

### 전체화면 선수 상세 페이지

선수 이름을 클릭하면 팝업이 아닌 전체 페이지형 선수 보고서가 열립니다.

- 좌측: 선수 카드, 신체정보, 연봉, 계약·가치·잠재력 틀
- 중앙: 타자/투수 능력치, 2025 실제 기록, 코칭스태프 보고서
- 우측: 종합평가, 데이터 신뢰도, 야구장 포지션 맵과 숙련도
- 구단별 고유 색상 팔레트 적용
- 미수집 항목은 삭제하지 않고 `미평가` 또는 `-`로 표시
- 선수 유형에 따라 타자·투수 화면 자동 전환

### 게임 화면과 저장

- SQLite 기반 새 게임 저장·불러오기·삭제
- 게임 날짜 표시와 하루 진행
- 전체 뉴스 센터와 날짜별 소식
- 미확인 뉴스 개수와 확인 상태 저장
- 감독 부임 직후 구단 공식 발표 뉴스
- 정규리그 순위와 선수 랭킹 화면

### 로컬 구단 운영 AI

이사회·단장 협상과 상대 구단의 주요 일정 판단에는 로컬 Qwen 모델을 사용할 수 있습니다.
하루 진행에 필요한 선수 상태·훈련·부상·1군/2군 편성은 빠른 시뮬레이션 엔진이 처리하고,
응답 생성 시간이 필요한 구단 AI 판단은 백그라운드에서 실행됩니다.

- 권장 모델: `Qwen3-1.7B-Q4_K_M.gguf`
- 로컬 서버: `llama.cpp`의 OpenAI 호환 서버
- 기본 주소: `http://127.0.0.1:8080/v1`
- 응답 검증: 잘못된 JSON과 허용되지 않은 결정 차단
- 폴백: 모델 서버가 꺼져 있어도 날짜 진행과 구단 시뮬레이션은 계속 수행
- 종료 처리: 제공 스크립트로 시작한 모델 서버는 게임 종료 시 함께 종료

프로필 기준값은 `data/config/club_governance_profiles.json`에 있으며 선수 DB와 분리되어 있습니다.

## AI 모델 다운로드

GGUF 모델 가중치는 용량과 배포 정책 때문에 GitHub 저장소에 포함하지 않습니다. 저장소를 받은 뒤
[ggml-org의 Qwen3-1.7B GGUF 페이지](https://huggingface.co/ggml-org/Qwen3-1.7B-GGUF)에서
`Qwen3-1.7B-Q4_K_M.gguf`를 내려받아 `models` 폴더에 넣어야 합니다.

### 방법 1: Hugging Face CLI 사용 권장

프로젝트 루트의 PowerShell에서 실행합니다.

```powershell
python -m pip install --upgrade huggingface_hub
New-Item -ItemType Directory -Force models | Out-Null
hf download ggml-org/Qwen3-1.7B-GGUF Qwen3-1.7B-Q4_K_M.gguf --local-dir models
```

### 방법 2: PowerShell로 직접 다운로드

```powershell
New-Item -ItemType Directory -Force models | Out-Null
Invoke-WebRequest `
  -Uri "https://huggingface.co/ggml-org/Qwen3-1.7B-GGUF/resolve/main/Qwen3-1.7B-Q4_K_M.gguf?download=true" `
  -OutFile "models/Qwen3-1.7B-Q4_K_M.gguf"
```

다운로드 결과를 확인합니다.

```powershell
Get-Item models/Qwen3-1.7B-Q4_K_M.gguf | Select-Object Name, Length
```

파일 크기는 약 1.28GB입니다. 다음 경로와 파일명이 정확해야 제공 스크립트가 인식합니다.

```text
KBOFM2025/
└─ models/
   └─ Qwen3-1.7B-Q4_K_M.gguf
```

## llama.cpp 설치 및 AI 실행

Windows에서는 `llama.cpp`를 설치합니다.

```powershell
winget install llama.cpp
```

설치와 모델 다운로드가 끝나면 첫 번째 PowerShell에서 서버를 실행합니다.

```powershell
powershell -ExecutionPolicy Bypass -File scripts/start_local_ai.ps1
```

두 번째 PowerShell에서 게임을 실행합니다.

```powershell
$env:KBOFM_AI_ENABLED="1"
python main.py
```

서버는 `127.0.0.1:8080`에서 `kbofm-local`이라는 별칭으로 실행되며 로그는
`data/ai_logs`에 기록됩니다.

Ollama의 OpenAI 호환 주소를 사용하는 경우 실행 전에 환경변수를 지정합니다.

```powershell
$env:KBOFM_AI_BASE_URL="http://127.0.0.1:11434/v1"
$env:KBOFM_AI_MODEL="qwen3:4b"
python main.py
```

로컬 AI를 사용하지 않으려면 다음과 같이 명시적으로 비활성화할 수 있습니다.

```powershell
$env:KBOFM_AI_ENABLED="0"
python main.py
```

## 데이터 기준

| 구분 | 기준 |
|---|---|
| 선수 소속 | 2025년 10월 31일 |
| 타격·투수·주루 기록 | 2025 KBO 시즌 |
| 선수 프로필 | KBO 공식 프로필 기반 |
| 구단·감독 메타데이터 | 2026년 7월 15일 확인 기준 |

선수단은 2025 등록 선수 명단을 시작점으로 2025년 2월 11일부터 10월 31일까지 발표된 소속선수 추가 등록, 자유계약선수, 웨이버, 임의해지·복귀, 군보류, 트레이드와 개명을 순서대로 반영했습니다.

주요 원본과 감사 자료는 다음 파일에 있습니다.

- `data/source/kbo_2025_final_roster.csv`
- `data/source/kbo_2025_membership_movements.csv`
- `data/source/kbo_2025_player_profiles.csv`
- `scripts/build_kbo_roster_snapshot.ps1`
- `scripts/fetch_kbo_player_profiles.ps1`

## 타자 능력치

현재 타자 317명에 대해 다음 능력치를 1~20으로 계산해 DB에 저장합니다.

| 영역 | 능력치 |
|---|---|
| 타격 | 컨택, 파워, 선구안, 배트 컨트롤, 타이밍, 번트 |
| 주루 | 주력, 주루 판단 |
| 수비 | 수비범위, 포구, 송구력, 송구 정확도, 수비판단 |
| 멘탈 | 침착성, 리더십, 적극성 |

수비와 멘탈 능력치는 스키마와 화면 틀만 준비되어 있으며 현재 값은 `NULL`입니다.

능력치 계산에는 타율, ISO, 홈런율, 볼넷율, 삼진율, 희생번트, 도루 시도와 성공률, 주루사·견제사, 투수 유형별 기록을 사용합니다. 작은 표본은 실제 타석·타수·주루 기회를 기준으로 리그 평균 쪽으로 보정합니다.

- 평균적인 능력: 약 10
- 상위 10%: 14 이상
- 상위 1%: 18 이상
- 19~20: 극히 예외적인 기록에만 부여
- 1군 기록이 없는 선수: 퓨처스 기록과 레벨 보정 사용
- 1군·퓨처스 기록이 모두 없는 선수: 중립값 사용

전체 타자 능력치는 다음 명령으로 다시 계산할 수 있습니다.

```powershell
powershell -ExecutionPolicy Bypass -File scripts/calculate_kbo_2025_hitter_abilities.ps1
```

결과 파일은 `data/source/kbo_2025_hitter_abilities.csv`이며, 공식 계산 버전은 `kbo-hitter-abilities-v2-compressed`입니다.

## 2025 시즌 기록

### 타자

`data/source/kbo_2025_first_team_hitting.csv`에 타율, 경기, 타석, 안타, 2루타, 3루타, 홈런, 타점, 도루, 볼넷, 삼진, 출루율, 장타율, OPS, 희생번트와 파생지표가 저장됩니다.

### 투수

`data/source/kbo_2025_first_team_pitching.csv`에 ERA, 경기, 승패, 세이브, 홀드, 이닝, 피안타, 피홈런, 볼넷, 탈삼진과 WHIP가 저장됩니다.

### 주루와 상황별 기록

- `data/source/kbo_2025_running.csv`: 도루 시도, 도루, 도루실패, 성공률, 주루사, 견제사
- `data/source/kbo_2025_hitter_situation_splits.csv`: 주자, 볼카운트, 이닝, 타순, 투수 유형, 아웃카운트별 기록
- `data/source/kbo_2025_futures_hitting.csv`: 퓨처스 타자 성적

## 실행 환경

- Windows 10/11
- Python 3.10 이상 권장
- PySide6
- SQLite

PowerShell에서 가상환경과 의존성을 준비합니다.

```powershell
python -m venv venv
venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install PySide6 pyinstaller
```

기존 `venv`가 다른 PC의 Python 경로를 가리키면 삭제한 뒤 다시 생성해야 합니다.

## 실행 방법

프로젝트 루트에서 실행합니다.

```powershell
python main.py
```

최초 실행 시 `data/players.db` 스키마와 선수 데이터가 확인됩니다. 게임 저장 파일은 `data/kbo_fm_saves.db`에 생성되며 Git에는 포함되지 않습니다.

## 실행 파일 빌드

```powershell
pyinstaller main.spec
```

빌드 결과는 `dist` 폴더에 생성됩니다. `main.spec`에는 이미지, 최종 선수단, 타자 능력치, 2025 타격·투수 기록이 포함되어 있습니다.

## 프로젝트 구조

```text
KBO-Manager-2025/
├─ main.py
├─ main.spec
├─ app/
│  ├─ application.py
│  ├─ windows.py
│  ├─ config/
│  │  ├─ managers.py
│  │  └─ teams.py
│  └─ views/
│     ├─ team_roster_preview.py
│     ├─ team_manager.py
│     └─ team_manage/
│        ├─ first_team.py
│        ├─ second_team.py
│        ├─ set_lineup.py
│        └─ player_profile.py
├─ database/
│  ├─ paths.py
│  ├─ player_database.py
│  ├─ roster_data.py
│  └─ save_database.py
├─ data/
│  ├─ players.db
│  └─ source/
├─ scripts/
└─ image/
   └─ Mascort/
```

## 주요 스크립트

| 스크립트 | 용도 |
|---|---|
| `build_kbo_roster_snapshot.ps1` | 선수 이동을 반영한 최종 선수단 생성 |
| `fetch_kbo_player_profiles.ps1` | 선수 공식 프로필 수집 |
| `fetch_kbo_2025_stats.ps1` | 2025 1군 타격·투수 및 퓨처스 기록 수집 |
| `fetch_kbo_2025_hitter_detail.ps1` | 타자 세부·상황별 기록 수집 |
| `fetch_kbo_2025_running.ps1` | 공식 주루 기록 수집 |
| `calculate_kbo_2025_hitter_abilities.ps1` | 타자 능력치 1~20 계산 |
| `import_kbo_2025_hitter_abilities.mjs` | 계산된 타자 능력치를 SQLite DB에 반영 |

## 현재 제한사항

- 투수 전용 세부 능력치는 아직 기존 임시 능력치를 사용합니다.
- 수비·멘탈·잠재력·계약기간과 시장가치는 아직 일부 항목이 평가되지 않았습니다.
- 선수 사진은 DB와 연결되지 않아 이름 카드가 표시됩니다.
- 정규시즌 경기 결과를 만드는 타석 단위 경기 시뮬레이션은 개발 예정입니다.
- 일부 구단·팬·미디어 성향은 게임 플레이용 해석값입니다.

## 개발 로드맵

1. 투수 능력치 모델과 구종 데이터 구축
2. 수비·멘탈·포지션 숙련도 평가
3. 타석 단위 경기 시뮬레이션 엔진
4. 체력·컨디션·부상과 성장 시스템
5. 감독 AI의 라인업·대타·도루·투수 교체 판단
6. 경기 기록 누적과 정규시즌 일정
7. 중계 문장, 뉴스와 인터뷰 콘텐츠

## 데이터베이스 호환성

선수 DB는 기존 `con`, `pow`, `eye`, `def` 필드를 보존하면서 타자 전용 능력치를 별도 컬럼으로 추가합니다. 기존 화면과 투수 임시 능력치가 깨지지 않도록 레거시 필드는 자동으로 덮어쓰지 않습니다.

수비와 멘탈은 다음 SQLite 뷰로 분리해 조회할 수 있습니다.

- `player_defense_abilities`
- `player_mental_abilities`

## 고지

이 프로젝트는 KBO 및 각 구단과 공식적으로 관련이 없는 비공식 개인 개발 프로젝트입니다. 구단명, 선수명, 기록과 이미지의 권리는 각 권리자에게 있으며, 공개·배포 시 원자료의 이용 조건을 별도로 확인해야 합니다.




## 실행 사진

<img width="1191" height="761" alt="image" src="https://github.com/user-attachments/assets/557e04cd-adc6-4934-84f5-926f049f46db" />

<img width="1170" height="736" alt="image" src="https://github.com/user-attachments/assets/9f924e3b-2e35-41c7-94e6-4660219411fb" />

<img width="1280" height="656" alt="image" src="https://github.com/user-attachments/assets/2cd10660-516c-487f-9b1d-bc574c9b2d19" />

<img width="1280" height="820" alt="image" src="https://github.com/user-attachments/assets/ca411cf4-1ab5-4603-b76e-4d08c98d8ecf" />

<img width="1280" height="809" alt="image" src="https://github.com/user-attachments/assets/20d8d1f0-54ff-42cf-ba62-97030e4cd5e4" />

<img width="1280" height="807" alt="image" src="https://github.com/user-attachments/assets/0e48b551-9f0e-464f-94fe-c53c7871151b" />
