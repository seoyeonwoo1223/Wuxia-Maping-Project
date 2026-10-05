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

### 원본 뷰어 실행

```bash
python tools/fix_encoding.py legacy/murim.swf legacy/murim_ko.swf
```

`legacy/font.ttf`에 한글 TTF(예: Noto Sans KR)를 두고 `legacy/`에서 `python -m http.server`.
