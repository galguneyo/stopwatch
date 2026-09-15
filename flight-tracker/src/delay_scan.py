"""당일 서울↔제주 운항 지연 현황을 조회해 data/delays.json 으로 저장한다.

예약 후보일은 몇 주 뒤지만, "이 노선이 요즘 얼마나 제때 뜨는가"는 오늘 실적으로만
알 수 있다. 대시보드는 이 값을 참고 지표로 함께 보여준다.

사용법:
    python src/delay_scan.py                 # provider=mock (기본)
    python src/delay_scan.py --provider live # 공공API 실조회 (KAC_SERVICE_KEY 필요)
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path

from providers.delay import DelayProviderError, summarize

DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "delays.json"
ROUTES = [("GMP", "CJU"), ("CJU", "GMP")]


def _make_provider(kind: str):
    if kind == "mock":
        from providers.mock_delay import MockDelayProvider

        return MockDelayProvider()
    if kind == "live":
        from providers.delay import KacDelayProvider

        return KacDelayProvider()
    raise ValueError(kind)


def run(provider_kind: str) -> dict:
    provider = _make_provider(provider_kind)
    today = dt.date.today()

    routes: dict[str, dict] = {}
    errors: list[dict] = []

    for origin, dest in ROUTES:
        key = f"{origin}-{dest}"
        try:
            flights = provider.get_today(origin, dest, today)
        except DelayProviderError as e:
            errors.append({"route": key, "reason": str(e)})
            routes[key] = {"flights": [], "summary": summarize([])}
            continue
        routes[key] = {
            "flights": [f.to_dict() for f in flights],
            "summary": summarize(flights),
        }

    return {
        "generated_at": dt.datetime.now().isoformat(),
        "provider": provider_kind,
        "date": today.isoformat(),
        "routes": routes,
        "errors": errors,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", choices=["mock", "live"], default="mock")
    args = parser.parse_args()

    output = run(args.provider)
    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    DATA_PATH.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")

    for key, route in output["routes"].items():
        s = route["summary"]
        rate = f"{s['ontime_rate']:.0%}" if s["ontime_rate"] is not None else "—"
        print(f"[delay_scan] {key} {s['total']}편 · 정시율 {rate} · 지연 {s['delayed']} · 결항 {s['cancelled']}")
    if output["errors"]:
        print(f"[delay_scan] 실패 {len(output['errors'])}건 (delays.json의 errors 참조)")


if __name__ == "__main__":
    main()
