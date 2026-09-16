# 선수 사진 로컬 저장소

실제 선수 사진은 KBO 선수 ID를 파일명으로 사용합니다. 크롤링한 원본은
`local/highres-originals`, 게임에서 바로 읽는 최적화본은 `local/game-ready`에
저장합니다. 최적화 과정은 배경 제거·크롭을 하지 않고 원본 종횡비를 유지합니다.

```text
image/players/local/highres-originals/52605.jpg
image/players/local/game-ready/52605.jpg
```

`local` 폴더의 사진은 저작권·초상권 문제를 방지하기 위해 Git에서 제외됩니다.
게임은 `game-ready`를 우선 사용하고 파일이 없을 때 `highres-originals`, 기존
`local` 파일 순서로 폴백합니다. 선수 상세, 라인업, 이적 소식, 에이전트 협의,
계약 협상, 선수 면담은 모두 같은 ID 기반 사진 해석기를 사용합니다.

게임용 사본 생성과 검증:

```powershell
node scripts/player-photo-tools/prepare-game-player-photos.mjs
node scripts/player-photo-tools/verify-player-photo-connection.mjs
```

사진 URL과 출처 정보는 `data/source/player_photo_manifest.csv`에서 관리합니다. 출처와 이용 조건을 직접 확인한 행만 `approved=1`로 변경하세요.
