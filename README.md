# KBO FM 2025

KBO FM 2025는 2025시즌 종료 시점의 KBO를 배경으로 하는 비공식 데스크톱 야구 구단 운영 시뮬레이션입니다. 감독을 만들고 10개 구단 중 하나를 맡아 이사회 목표, 선수단, 전술, 계약, FA·외국인 시장과 스토브리그 일정을 관리합니다.

> 현재 개발 중인 알파 버전입니다. 11월부터 2월까지의 구단 운영 시스템을 순차적으로 완성하고 있으며, 정규시즌 경기 시뮬레이션은 아직 개발 중입니다.

## 가장 쉬운 실행 방법 (Windows)

### 1. Python 설치

[Python 공식 다운로드 페이지](https://www.python.org/downloads/windows/)에서 Python 3.10 이상을 설치합니다. Python 3.11 또는 3.12를 권장합니다.

설치 화면에서는 반드시 `Add Python to PATH`를 선택합니다.

### 2. 프로젝트 받기

Git을 사용하는 경우 PowerShell에서 다음 명령을 실행합니다.

```powershell
git clone https://github.com/KBOFM2025/KBOFM2025.git
cd KBOFM2025
```

Git을 사용하지 않는 경우 GitHub의 `Code → Download ZIP`을 누르고 압축을 풉니다. 압축을 풀지 않은 ZIP 내부에서는 게임을 실행하지 마세요.

### 3. `run_game.bat` 실행

프로젝트 폴더의 `run_game.bat`을 더블클릭합니다.

처음 실행할 때 스크립트가 자동으로 다음 작업을 수행합니다.

1. `.venv` 가상환경 생성
2. PySide6 설치
3. 로컬 AI 모델 존재 여부 확인
4. `main.py` 실행

처음 한 번은 PySide6 다운로드 때문에 시간이 걸릴 수 있습니다. 이후 실행부터는 바로 게임을 시작합니다.

로컬 AI 모델이 없어도 게임은 실행됩니다. 이 경우 AI가 필요한 선택 기능만 폴백 모드로 동작하며 트레이드·선수 면담 등의 규칙 기반 시스템은 그대로 사용할 수 있습니다.

## 수동 실행 방법

명령어로 직접 실행하려면 프로젝트 루트에서 다음 순서대로 진행합니다.

```powershell
python -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python main.py
```

명령 프롬프트(cmd)를 사용한다면 활성화 명령은 다음과 같습니다.

```bat
.venv\Scripts\activate.bat
python main.py
```

## 권장 실행 환경

| 항목 | 권장 사양 |
|---|---|
| 운영체제 | Windows 10/11 64비트 |
| Python | 3.11 또는 3.12 |
| 화면 | 1600×900 이상, Windows 배율 100~125% |
| 메모리 | 기본 실행 8GB 이상 |
| 로컬 AI 사용 | 16GB RAM 이상, GPU 가속 권장 |
| 필수 패키지 | PySide6 |

기본 게임은 인터넷 연결 없이 실행할 수 있습니다. 최초 패키지 설치와 선택적인 AI 모델 다운로드에는 인터넷 연결이 필요합니다.

## 새 게임 진행 순서

1. 시작 화면에서 `새로 생성` 선택
2. 감독 이름과 감독 스타일 설정
3. 11개 감독 능력치를 20점 척도로 배분
4. KBO 10개 구단 중 담당 구단 선택
5. 시작 시점 선택
6. 이사회와 구단 비전 협의
7. 공식 선임 기사 확인
8. 수신함에서 취임 기자회견 진행
9. 스토브리그 업무 시작

선택할 수 있는 시작 시점은 다음과 같습니다.

| 시작 시점 | 게임 날짜 | 내용 |
|---|---:|---|
| 스토브리그 시작 | 2025-11-01 | FA·보류선수·2차 드래프트 준비부터 시작 |
| 2차 드래프트 이후 | 2025-11-27 | 지명 결과를 반영하고 선수단 정리부터 시작 |
| 계약·캠프 준비 단계 | 2025-12-15 | 계약을 마무리하고 캠프 준비부터 시작 |

## 현재 구현된 주요 기능

### 감독 생성과 구단 선택

- 염경엽·김경문·김성근 스타일 프리셋과 사용자 스타일
- 타격·투수·수비·주루 지도, 경기 운영, 투수 교체, 대타, 데이터 분석, 유망주 육성, 훈련·체력 관리, 리더십 능력치
- 20점 척도 능력 배분과 레이더 차트
- 10개 구단의 연고지, 창단연도, 우승 기록, 모기업, 단장·팬 성향, 목표와 마스코트 정보
- 사용자 구단 이름 지정

### 수신함과 스토브리그 일정

- 메시지 유형별 전용 UI: 이사회, 기자회견, 메디컬, 트레이드, 선수 면담, 선수단 변동, 리그 뉴스
- 읽은 메시지 회색 표시와 일자별 누적
- 다음 날짜 진행 시 최소 2초 로딩 화면과 다른 구단 진행 상황 표시
- 필수 업무 미처리 시 날짜 진행 차단
- 2025년 11월부터 2026년 2월까지의 KBO·구단 일정
- 11월 3일 보류선수·계약 현황 1차 검토와 선수별 감독 방침 저장
- 2차 드래프트 보호명단·지명 결과 흐름

### 선수단과 선수 상세 정보

- 10개 구단 선수 DB와 1군·2군 분류
- FM형 선수단 표, 현재 능력·잠재력·컨디션·피로·부상 상태
- 전체 화면 선수 상세 페이지와 실제 선수 사진 연결
- 타자·투수 능력치, 실제 2025 기록, 계약·연봉 정보
- 별도 FA 탭에서 등록일수, 시즌별 인정 기록, 부족 시즌과 예상 FA 시점 확인
- 비FA 다년계약과 옵션 계약 반영
- 메디컬 뉴스, 부상 진단, 치료 방침과 복귀 일정

### 전술

- 여러 전술 버전 생성·저장·활성화
- 1~9번 타순과 수비 포메이션 구성
- 1군 선수 드래그 앤 드롭 배치
- 1~5선발 로테이션과 불펜 역할 설정
- 경기 초반(1~3회), 중반(4~7회), 후반(8~9회) 운영 계획

### 이적과 계약

- 실제 선수 가치·연봉·연령·포지션 수요를 반영하는 트레이드 규칙 엔진
- 현금, 추가 선수, 추후 지명 선수와 복합 보상 협상
- 외국인 선수 재계약·방출과 생성형 외국인 FA 시장
- 구단 스카우터 능력에 따른 후보와 정보 정확도 차이
- 외국인 선수 세부 협상과 구단별 예산 표시
- FA 자격과 계약 만료 상태 연동

### 이사회와 대화형 업무

- 구단별 운영 성향과 목표를 반영하는 5단계 이사회 협의
- 구단 방향, 현재 전력, 재정, 육성·성과 균형을 반영하는 규칙 기반 평가
- 취임 기자회견과 지역지·KBS·MBC·SBS·SPOTV 기자 질문
- AI 호출 없이 반복 가능한 규칙 기반 선수 면담과 트레이드 협상

## 저장 데이터

| 경로 | 내용 |
|---|---|
| `data/players.db` | 선수, 능력치, 기록과 계약 데이터 |
| `data/kbo_fm_saves.db` | 생성한 감독, 구단, 날짜, 뉴스와 게임 상태 |
| `data/source/` | 선수단과 실제 기록 원본 CSV |
| `data/logs/crash.log` | 비정상 종료와 Python·Qt 오류 로그 |
| `data/ai_logs/` | 선택적인 로컬 AI 서버 로그 |

게임 진행 중 변경 사항은 게임 안에서 `게임 저장`을 눌렀을 때 세이브 DB에 반영됩니다. 저장하지 않고 종료하면 마지막 저장 이후 진행 내용은 유지되지 않습니다.

세이브를 백업하려면 게임을 완전히 종료한 뒤 `data/kbo_fm_saves.db`를 다른 폴더에 복사하세요. 다른 PC로 옮길 때도 같은 위치에 파일을 넣으면 됩니다.

## 선택 기능: 로컬 AI

로컬 AI는 게임 실행에 필수가 아닙니다. 현재는 이사회·구단 방향과 타 구단의 일부 판단에 사용하며, 트레이드와 선수 면담은 빠르고 일관된 규칙 엔진이 담당합니다. 향후 경기 운영 AI에도 연결할 예정입니다.

### 1. llama.cpp 설치

```powershell
winget install llama.cpp
```

설치 후 PowerShell을 새로 열어 `llama-server.exe`가 인식되는지 확인합니다.

```powershell
llama-server.exe --version
```

### 2. 모델 다운로드

권장 모델은 `Qwen3-4B-Q4_K_M.gguf`이며 약 2.5GB입니다.

```powershell
python -m pip install --upgrade huggingface_hub
New-Item -ItemType Directory -Force models | Out-Null
hf download ggml-org/Qwen3-4B-GGUF Qwen3-4B-Q4_K_M.gguf --local-dir models
```

저사양 PC에서는 `Qwen3-1.7B-Q4_K_M.gguf`를 사용할 수 있습니다. 파일을 다음 위치에 둡니다.

```text
KBOFM2025/
└─ models/
   ├─ Qwen3-4B-Q4_K_M.gguf
   └─ Qwen3-1.7B-Q4_K_M.gguf  # 선택적인 저사양 폴백
```

모델 파일은 용량 문제로 GitHub 저장소에 포함되지 않습니다. 모델이 있으면 `main.py`가 `llama-server`를 백그라운드에서 자동으로 시작합니다.

AI를 명시적으로 끄려면 다음과 같이 실행합니다.

```powershell
$env:KBOFM_AI_ENABLED="0"
python main.py
```

Ollama처럼 다른 OpenAI 호환 로컬 서버를 사용하려면 다음 환경변수를 지정합니다.

```powershell
$env:KBOFM_AI_BASE_URL="http://127.0.0.1:11434/v1"
$env:KBOFM_AI_MODEL="qwen3:4b"
python main.py
```

## 자주 발생하는 실행 문제

### `python` 또는 `py`를 찾을 수 없음

Python을 다시 설치하면서 `Add Python to PATH`를 선택한 뒤 터미널과 탐색기를 다시 엽니다.

### `No module named PySide6`

```powershell
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### 기존 가상환경이 다른 PC의 Python을 가리킴

프로젝트를 다른 PC로 복사했다면 기존 `venv` 또는 `.venv` 폴더를 삭제하고 `run_game.bat`을 다시 실행합니다. 가상환경은 PC마다 새로 만들어야 합니다.

### 창이 잠시 나타난 뒤 종료됨

PowerShell에서 실행하면 오류를 바로 확인할 수 있습니다.

```powershell
.venv\Scripts\python.exe main.py
```

비정상 종료 기록은 `data/logs/crash.log`에 남습니다. 오류를 제보할 때 이 파일의 마지막 부분과 어떤 화면에서 문제가 발생했는지 함께 전달해 주세요.

### 로컬 AI 연결 실패 또는 시간 초과

AI는 선택 기능이므로 우선 끄고 실행할 수 있습니다.

```powershell
$env:KBOFM_AI_ENABLED="0"
.venv\Scripts\python.exe main.py
```

AI를 사용하려면 다음 항목을 확인합니다.

- `models` 폴더에 GGUF 파일이 있는지
- `llama-server.exe --version`이 정상 실행되는지
- 8080 포트를 다른 프로그램이 사용 중인지
- `data/ai_logs/local_ai.stderr.log`의 오류 내용

### 선수 DB 초기화 또는 선수 ID 오류

게임을 종료한 뒤 `data/players.db`를 백업하고 이름을 변경한 다음 다시 실행하면 원본 CSV를 기준으로 DB가 재구성됩니다. 세이브 파일인 `data/kbo_fm_saves.db`는 먼저 별도로 백업하세요.

## 개발자를 위한 실행과 검사

테스트 실행:

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

실행 파일 빌드:

```powershell
.venv\Scripts\python.exe -m pip install pyinstaller
.venv\Scripts\pyinstaller.exe main.spec
```

빌드 결과는 `dist/main.exe`에 생성됩니다. 현재 `main.spec`은 이미지와 주요 선수·기록 데이터를 포함하지만 로컬 AI 모델과 개인 세이브는 포함하지 않습니다.

## 프로젝트 구조

```text
KBOFM2025/
├─ main.py                 # 실행 진입점
├─ run_game.bat            # Windows 자동 설치·실행
├─ requirements.txt        # 필수 Python 패키지
├─ main.spec               # PyInstaller 설정
├─ app/
│  ├─ application.py       # 부팅 화면과 앱 생명주기
│  ├─ windows.py           # 화면 연결과 메인 윈도우
│  ├─ ai/                  # 선택적인 로컬 AI 연결
│  ├─ config/              # 구단·감독·시즌 일정 설정
│  ├─ services/            # 시뮬레이션·협상·계약 규칙
│  └─ views/               # 수신함·선수단·전술·이적 UI
├─ database/               # 선수 DB와 세이브 저장소
├─ data/
│  ├─ config/
│  └─ source/
├─ image/                  # 구단·선수·구장·UI 이미지
├─ models/                 # 로컬 GGUF 모델(저장소 제외)
├─ scripts/                # 데이터 수집·가공·AI 실행 도구
└─ tests/                  # 규칙 엔진과 일정 테스트
```

## 데이터 기준과 주의사항

- 선수단 시작점: 2025년 10월 31일
- 실제 타격·투수·주루 기록: 2025 KBO 시즌
- 선수 프로필과 계약 정보: 프로젝트 데이터 스냅샷 기준
- 게임 안의 구단·팬·단장 성향: 실제 공개 자료를 참고한 게임 플레이용 해석값
- 생성형 외국인 선수와 일부 뉴스·이벤트: 게임용 가상 데이터

일부 선수의 수비·멘탈·잠재력, 계약 세부 조건과 사진은 데이터 신뢰도에 따라 `미평가` 또는 `-`로 표시될 수 있습니다.

## 현재 제한사항

- 정규시즌 타석 단위 경기 시뮬레이션과 경기 중 감독 AI는 개발 중입니다.
- 11월 이후 일정의 일부 업무는 화면과 규칙을 계속 확장하고 있습니다.
- 데이터 센터·의료 센터·재정 메뉴 일부는 후속 개발용 자리표시자입니다.
- 실제 구단의 내부 평가나 계약 판단과 게임 내 알고리즘 결과는 다를 수 있습니다.
- 개발 중 DB 스키마가 변경될 경우 오래된 세이브는 완전히 호환되지 않을 수 있습니다.

## 고지

이 프로젝트는 KBO 및 KBO 소속 구단과 공식적으로 관련이 없는 비공식 개인 개발 프로젝트입니다. 구단명, 선수명, 기록, 로고와 이미지의 권리는 각 권리자에게 있습니다. 프로젝트를 공개하거나 재배포할 때는 원자료와 이미지의 이용 조건을 별도로 확인해야 합니다.

## 개발 화면

아래 이미지는 개발 과정의 화면이며 현재 버전과 일부 다를 수 있습니다.

<img width="1191" height="761" alt="KBO FM 시작 화면" src="https://github.com/user-attachments/assets/557e04cd-adc6-4934-84f5-926f049f46db" />

<img width="1280" height="820" alt="KBO FM 선수 상세 화면" src="https://github.com/user-attachments/assets/ca411cf4-1ab5-4603-b76e-4d08c98d8ecf" />

<img width="1280" height="807" alt="KBO FM 게임 화면" src="https://github.com/user-attachments/assets/0e48b551-9f0e-464f-9b1d-bc574c9b2d19" />
