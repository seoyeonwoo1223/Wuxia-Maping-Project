# Wuxia-Maping-Project

2003년 공개된 **「무협용 중국전도 Ver. 2.0」**(Flash)을 현대적인 웹 지도로 다시 만드는 프로젝트.

## 원작 및 출처

- 원작: **낙방수재** (www.newmurim.com)
- 원작 내 고지: *"이 지도는 누구나 사용할 수 있고, 누구나 재배포 할 수 있습니다."*
- 원작의 자료 출처(원작 고지 기준): newmurim.com, chinese.yahoo.com, chinamap.co.kr
- 문제가 되는 내용이 있으면 이슈로 알려주세요. 확인 후 수정·삭제합니다.

## 구성

- `legacy/murim.swf` — 원본 exe(Flash 프로젝터)에서 잘라낸 SWF (Flash 5, 1100×768)
- `legacy/index.html` — Ruffle로 원본을 띄우는 참고용 뷰어
- `tools/swfdump.py` — SWF 태그 통계, JPEG·텍스트 추출
- `tools/fix_encoding.py` — CP949 텍스트 필드를 UTF-8로 바꾸고 SWF 6으로 올림 (Ruffle 한글 표시용)
- `tools/swflib.py`, `tools/swfsvg.py` — 의존성 없는 SWF 파서 / 벡터 도형 → SVG 변환
- `tools/extract.py` — 지도 SVG와 데이터(JSON)를 `docs/`로 추출

### 데이터 추출

```bash
python tools/extract.py legacy/murim.swf docs
```

- `docs/maps/china.svg`, `docs/maps/<성>.svg` — 전국도·성별 상세도 (텍스트 제외, 좌표 단위 px)
- `docs/data/places.json` — 성·도시·명승지·문파: 이름(한글/한자), 소속 성, 종류, 설명, 지도 좌표
- `docs/data/emperors.json` — 제왕연표, `landmarks.json` — 주요지명, `about.json` — 원작 고지
- `docs/data/report.json` — 연결 통계와 사용되지 않은 텍스트 목록
- 원작의 명승지 사진(JPEG)은 제3자 저작물로 보여 추출·사용하지 않음

### 웹 사이트

`docs/`가 빌드 없는 정적 사이트입니다 (바닐라 JS + 인라인 SVG, 글꼴은 Google Fonts의 Noto Sans KR / Noto Serif KR, OFL).

```bash
python -m http.server -d docs 8000   # http://localhost:8000
```

- 지도 이동·확대(드래그, 휠, 핀치), 지명·문파 검색, 설명 패널, 제왕연표, 주요지명, 원작 정보 페이지
- 주소: `#/map/<성>`, `#/place/<id>`, `#/emperors/<id>`, `#/landmarks/<id>`, `#/about`

### 원본 뷰어 실행

```bash
python tools/fix_encoding.py legacy/murim.swf legacy/murim_ko.swf
```

`legacy/font.ttf`에 한글 TTF(예: Noto Sans KR)를 두고 `legacy/`에서 `python -m http.server`.
