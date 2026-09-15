"""실항공사 웹사이트에서 실시간 조회를 하는 범용 Playwright Provider.

★★★ 반드시 읽을 것 ★★★
이 코드는 이 개발 세션(네트워크 egress가 정책적으로 차단된 샌드박스)에서는
실행/검증이 불가능했다. 대한항공·아시아나 등 공식 사이트에 실시간으로
붙는 공개 API가 존재하지 않기 때문에(2026-09-15 기준 data.go.kr 확인 결과,
국내선 "운항 스케줄" 공공API는 있으나 "실시간 판매가/좌석" API는 없음),
실질적으로 남은 방법은 각 사 예매 화면을 브라우저 자동화로 조회하는 것뿐이다.

따라서 이 파일은 "셀렉터만 채우면 동작하는" 범용 엔진으로 작성했고,
사이트별 CSS 셀렉터는 config/selectors.yaml 에서 관리한다. 셀렉터 값은
실제 네트워크가 열려 있는 환경(예: 로컬 PC, 또는 GitHub Actions 러너)에서
브라우저 개발자도구로 한 번 직접 확인해 채워 넣어야 한다 — 지금 이 세션에서
값을 추측해 채우면 틀린 정보를 사실인 것처럼 제공하는 셈이 되므로 비워둔다.

또한 항공사 사이트는 대체로 봇 탐지/캡차를 사용하므로(reCAPTCHA 등),
운영 시 요청 간격 조절, User-Agent, 실패 시 재시도/알림 로직이 필요하다.
이 파일은 그 뼈대만 제공한다.
"""

from __future__ import annotations

import datetime as dt
import re
from pathlib import Path
from typing import Any

import yaml

from providers.base import FlightOffer, FlightSearchProvider, ProviderError
from rules import AIRLINE_NAMES

SELECTORS_PATH = Path(__file__).resolve().parents[2] / "config" / "selectors.yaml"


def _load_selector_config(airline_code: str) -> dict[str, Any]:
    if not SELECTORS_PATH.exists():
        raise ProviderError(f"{SELECTORS_PATH} 가 없습니다.")
    all_cfg = yaml.safe_load(SELECTORS_PATH.read_text(encoding="utf-8")) or {}
    cfg = all_cfg.get(airline_code)
    if not cfg:
        raise ProviderError(f"{airline_code} 셀렉터 설정이 없습니다.")
    if not cfg.get("verified"):
        raise ProviderError(
            f"{airline_code} 셀렉터가 아직 실사이트에서 검증(verified: true)되지 않았습니다. "
            "config/selectors.yaml 을 실제 네트워크 환경에서 채운 뒤 사용하세요."
        )
    return cfg


class PlaywrightFlightProvider(FlightSearchProvider):
    """selectors.yaml 설정을 읽어 항공사 예매 검색 화면을 조회하는 범용 provider."""

    def __init__(self, airline_code: str, headless: bool = True, timeout_ms: int = 20000):
        self.airline_code = airline_code
        self.headless = headless
        self.timeout_ms = timeout_ms

    def search(self, origin: str, dest: str, date: dt.date) -> list[FlightOffer]:
        cfg = _load_selector_config(self.airline_code)

        try:
            from playwright.sync_api import sync_playwright
        except ImportError as e:
            raise ProviderError(
                "playwright가 설치되어 있지 않습니다. `pip install playwright` 후 "
                "`playwright install chromium` 을 실행하세요."
            ) from e

        url = cfg["search_url_template"].format(origin=origin, dest=dest, date=date.strftime("%Y%m%d"))

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=self.headless)
            page = browser.new_page()
            try:
                page.goto(url, timeout=self.timeout_ms)
                page.wait_for_selector(cfg["result_row_selector"], timeout=self.timeout_ms)
                rows = page.query_selector_all(cfg["result_row_selector"])
                offers = [self._parse_row(row, cfg, origin, dest, date) for row in rows]
                return [o for o in offers if o is not None]
            except Exception as e:  # noqa: BLE001 - 운영 시 알림으로 전환
                raise ProviderError(f"{self.airline_code} 조회 실패: {e}") from e
            finally:
                browser.close()

    def _parse_row(self, row, cfg: dict, origin: str, dest: str, date: dt.date) -> FlightOffer | None:
        def text(sel_key: str) -> str:
            el = row.query_selector(cfg[sel_key])
            return el.inner_text().strip() if el else ""

        flight_no = text("flight_no_selector")
        dep_text = text("dep_time_selector")  # 예: "10:30"
        arr_text = text("arr_time_selector")
        price_text = text("price_selector")
        sold_out = row.query_selector(cfg.get("sold_out_selector", "")) is not None

        price_digits = re.sub(r"[^0-9]", "", price_text)
        price = int(price_digits) if price_digits else None

        dep_dt = _combine(date, dep_text)
        arr_dt = _combine(date, arr_text)
        if dep_dt is None or arr_dt is None:
            return None

        return FlightOffer(
            airline_code=self.airline_code,
            airline_name=AIRLINE_NAMES.get(self.airline_code, self.airline_code),
            flight_no=flight_no or self.airline_code,
            origin=origin,
            dest=dest,
            dep_dt=dep_dt,
            arr_dt=arr_dt,
            price_krw=price,
            is_direct=True,
            bookable=not sold_out,
            source="live",
            booking_url=None,
            fetched_at=dt.datetime.now(),
        )


def _combine(date: dt.date, hhmm: str) -> dt.datetime | None:
    m = re.match(r"^(\d{1,2}):(\d{2})", hhmm)
    if not m:
        return None
    return dt.datetime.combine(date, dt.time(int(m.group(1)), int(m.group(2))))
