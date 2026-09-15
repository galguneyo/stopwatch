"""실데이터 연결 검증 스크립트.

개발 세션(샌드박스)은 조직 네트워크 정책으로 외부 접속이 전면 차단되어 있어
실제 연결을 확인할 수 없다. 이 스크립트는 인터넷이 열린 환경 — GitHub Actions
러너나 사용자 PC — 에서 실행해 "무엇이 실제로 되고 무엇이 막히는지"를
추측 없이 기록하기 위한 것이다.

검증 항목
  1) 호스트 도달성 — 항공사/기상 API에 실제로 연결되는가
  2) 날씨 실연결 — Open-Meteo를 실제 호출해 응답 값을 출력 (셀렉터 불필요)
  3) 항공사 예매 화면 — 브라우저로 열어 봇 차단 여부와 DOM 구조 단서를 수집

실패해도 프로세스는 0으로 종료한다. 목적이 "합격/불합격"이 아니라
"현장 상황 기록"이기 때문이다.
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from providers.weather import AIRPORT_COORDS, OpenMeteoWeatherProvider, WeatherProviderError

# 각 항공사 국내선 예매 진입 화면. 딥링크(날짜/노선이 박힌 URL)는 사이트마다
# 규격이 다르고 이 세션에서 확인할 수 없었으므로, 우선 진입 화면이 클라우드
# IP에서 열리는지부터 확인한다.
AIRLINE_ENTRY = {
    "KE": ("대한항공", "https://www.koreanair.com/kr/ko"),
    "OZ": ("아시아나항공", "https://flyasiana.com/C/KR/KO/index"),
    "7C": ("제주항공", "https://www.jejuair.net/jejuair/main.do"),
    "TW": ("티웨이항공", "https://www.twayair.com/app/main"),
    "BX": ("에어부산", "https://www.airbusan.com/content/individual/"),
    "RS": ("에어서울", "https://flyairseoul.com"),
    "ZE": ("이스타항공", "https://www.eastarjet.com"),
}

BOT_MARKERS = [
    "captcha", "recaptcha", "access denied", "forbidden", "blocked",
    "비정상적인 접근", "자동 입력 방지", "접근이 차단",
]

LINE = "-" * 68

# 로그가 길어지면 앞부분이 잘려 결론을 놓치기 쉬우므로, 각 검증의 판정을 모아
# 맨 마지막에 한 번 더 요약해서 찍는다.
VERDICTS: list[tuple[str, str]] = []


def record(label: str, verdict: str) -> None:
    VERDICTS.append((label, verdict))


def section(title: str) -> None:
    print(f"\n{LINE}\n{title}\n{LINE}")


def check_reachability() -> None:
    section("1) 호스트 도달성")
    import requests

    hosts = [
        "https://api.open-meteo.com/v1/forecast?latitude=37.5&longitude=127&daily=weathercode&timezone=Asia%2FSeoul",
        # 지연/결항 공공API 호스트. 서비스 키가 없어도 호스트 도달성은 확인할 수 있다
        # (키 없이 호출하면 인증 오류가 오는 것이 정상이며, 그것 자체가 '연결됨'의 증거다).
        "https://apis.data.go.kr",
        "https://www.data.go.kr",
    ]
    hosts += [url for _, url in AIRLINE_ENTRY.values()]

    for url in hosts:
        host = url.split("/")[2]
        try:
            res = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
            print(f"  {host:<28} HTTP {res.status_code}  ({len(res.content):,} bytes)")
            record(f"도달성 {host}", f"HTTP {res.status_code}")
        except Exception as e:  # noqa: BLE001
            print(f"  {host:<28} 실패: {type(e).__name__}: {e}")
            record(f"도달성 {host}", f"실패 {type(e).__name__}")


def check_weather() -> None:
    section("2) 날씨 실연결 (Open-Meteo, API 키 불필요)")
    provider = OpenMeteoWeatherProvider()
    target = dt.date.today() + dt.timedelta(days=1)

    for code in AIRPORT_COORDS:
        try:
            info = provider.get_forecast(code, target)
        except WeatherProviderError as e:
            print(f"  {code} 실패: {e}")
            continue
        if info is None:
            print(f"  {code} 예보 범위 밖")
            continue
        print(f"  {code} {info.date}  {info.summary}  "
              f"강수 {info.precip_probability_pct}%  풍속 {info.wind_speed_kmh}km/h  "
              f"{info.temp_low_c}~{info.temp_high_c}°C  (source={info.source})")
        record(f"날씨 {code}", f"{info.summary} / 강수 {info.precip_probability_pct}%")

    print("\n  => 값이 출력됐다면 weather live provider는 실연결 검증 완료.")


def check_airlines() -> None:
    section("3) 항공사 예매 화면 접근 (Playwright)")
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("  playwright 미설치 — 건너뜀")
        return

    with sync_playwright() as p:
        browser = p.chromium.launch()
        for code, (name, url) in AIRLINE_ENTRY.items():
            ctx = browser.new_context(
                locale="ko-KR",
                user_agent=("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                            "(KHTML, like Gecko) Chrome/125.0 Safari/537.36"),
            )
            page = ctx.new_page()
            print(f"\n  [{code}] {name}  {url}")
            try:
                res = page.goto(url, timeout=45000, wait_until="domcontentloaded")
                page.wait_for_timeout(3500)
                body = (page.inner_text("body") or "")[:4000].lower()
                hits = [m for m in BOT_MARKERS if m in body]
                print(f"    HTTP {res.status if res else '?'} | 최종 URL {page.url[:90]}")
                print(f"    타이틀: {page.title()[:70]}")
                print(f"    봇차단 징후: {hits or '없음'}")
                print(f"    '제주' 문자열: {'있음' if '제주' in body else '없음'}"
                      f" | 본문 길이 {len(body):,}")
                print(f"    form {page.locator('form').count()} | "
                      f"input {page.locator('input').count()} | "
                      f"button {page.locator('button').count()}")
            except Exception as e:  # noqa: BLE001
                print(f"    실패: {type(e).__name__}: {str(e)[:160]}")
            finally:
                ctx.close()
        browser.close()

    print("\n  => 봇차단 징후가 없고 본문이 정상이면 셀렉터 수집 단계로 진행 가능.")
    print("     차단된다면 클라우드 IP 대신 사용자 PC에서 수집해야 한다.")


def main() -> None:
    print(f"검증 시각: {dt.datetime.now().isoformat()}")
    print(f"실행 환경: {sys.platform} / python {sys.version.split()[0]}")
    for step in (check_reachability, check_weather, check_airlines):
        try:
            step()
        except Exception as e:  # noqa: BLE001
            print(f"\n  단계 실패: {type(e).__name__}: {e}")

    section("요약")
    width = max((len(label) for label, _ in VERDICTS), default=0)
    for label, verdict in VERDICTS:
        print(f"  {label:<{width}}  {verdict}")


if __name__ == "__main__":
    main()
