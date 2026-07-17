# 선수 사진 로컬 저장소

실제 선수 사진은 `local` 폴더에 KBO 선수 ID로 저장합니다.

```text
image/players/local/66802.jpg
image/players/local/66802.png
image/players/local/66802.webp
```

`local` 폴더의 사진은 저작권·초상권 문제를 방지하기 위해 Git에서 제외됩니다. 선수 상세 페이지는 `webp`, `png`, `jpg`, `jpeg` 순서로 파일을 찾아 표시하고, 사진이 없으면 구단색 이름 카드를 사용합니다.

사진 URL과 출처 정보는 `data/source/player_photo_manifest.csv`에서 관리합니다. 출처와 이용 조건을 직접 확인한 행만 `approved=1`로 변경하세요.
