# 실데이터 연결 검증 기록

개발 세션(Claude Code 샌드박스)은 조직 네트워크 정책으로 외부 접속이 전면
차단되어 있어 실연결을 확인할 수 없습니다. 그래서 인터넷이 열린 **GitHub Actions
러너**에서 `src/verify_live.py`를 실제로 실행해 결과를 기록했습니다.

- 실행 워크플로: `.github/workflows/verify-live.yml`
- 실행 일시: 2026-09-15 08:04 UTC
- 실행 환경: `ubuntu-latest` / Python 3.11.16 / Playwright Chromium
- 실행 로그: Actions run `34944953393`

## 결론 요약

| 대상 | requests | 헤드리스 브라우저 | 판정 |
|---|---|---|---|
| Open-Meteo (날씨) | HTTP 200 | — | **실연결 성공** |
| 대한항공 (KE) | HTTP 403 | `ERR_HTTP2_PROTOCOL_ERROR` | 차단 |
| 아시아나 (OZ) | HTTP 403 | `ERR_HTTP2_PROTOCOL_ERROR` | 차단 |
| 제주항공 (7C) | HTTP 200 | HTTP 403 `JEJUAIR ERROR OCCURED` | 차단 |
| 티웨이 (TW) | HTTP 403 | HTTP 403 `Access Denied` | 차단(명시적) |
| 에어부산 (BX) | HTTP 403 | **HTTP 200 정상 로드** (form 3 / input 39) | 통과 |

## 1. 날씨 — 검증 완료

Open-Meteo를 실제로 호출해 받은 값입니다(가공하지 않은 실제 응답).

```
GMP 2026-09-16  대체로 맑음  강수 0%   풍속  7.4km/h  13.5~26.6°C  (source=live)
ICN 2026-09-16  대체로 맑음  강수 0%   풍속 16.6km/h  18.9~24.4°C  (source=live)
CJU 2026-09-16  약한 비      강수 90%  풍속 24.0km/h  20.8~25.8°C  (source=live)
```

API 키가 필요 없고 클라우드 IP에서도 정상 응답하므로, 날씨는
`.github/workflows/weather-scan.yml`로 **매일 자동 갱신**합니다.

## 2. 항공권 — 클라우드에서는 불가, 로컬 경로 필요

우선순위 1·2순위인 대한항공과 아시아나가 클라우드 IP에서 완전히 차단됩니다.
HTTP2 연결 자체가 끊기는 형태라, 셀렉터를 아무리 정확히 채워도 GitHub Actions
에서는 데이터를 가져올 수 없습니다. 티웨이는 `Access Denied`를 명시적으로
반환하고, 제주항공도 브라우저 접근 시 403입니다.

이는 셀렉터 문제가 아니라 **접속 출처(IP) 문제**입니다. 따라서 수집 경로를
클라우드가 아니라 가정용 IP(사용자 PC)로 두는 것이 맞습니다.

```bash
# 사용자 PC에서 (한 번만)
pip install -r requirements.txt
playwright install chromium

# 셀렉터 채운 뒤
python src/scan.py --provider live --weeks-ahead 8
python src/weekly_report.py
```

셀렉터 수집은 브라우저 개발자도구에서 한 번 확인해 `config/selectors.yaml`에
채우고 `verified: true`로 바꾸면 됩니다. 검증 전에는
`playwright_provider.py`가 의도적으로 실패하므로, 추측값으로 가짜 데이터가
만들어질 일은 없습니다.

에어부산만은 클라우드에서도 열리므로, 원하면 이 한 곳부터 자동화를 시작할 수
있습니다.

## 3. 재검증 방법

```bash
# 인터넷이 되는 환경이면 어디서든
python src/verify_live.py
```

GitHub에서는 Actions 탭 → "Verify live data connectivity" → Run workflow.
항공사 사이트 정책은 바뀔 수 있으므로, 수집이 갑자기 실패하면 이 스크립트를
먼저 돌려 차단인지 화면 구조 변경인지부터 구분하세요.
