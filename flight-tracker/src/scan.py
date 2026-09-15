"""주간 스캔 오케스트레이터.

서울<->제주 직항편을, 대한항공/아시아나 우선 -> LCC 순으로 조회한다.
사용자가 지정한 요일/시간대 규칙(예: 금요일 10시 이후)에 맞는지 여부는
각 항공편에 `in_target_window` 로 표시만 하고, 하루 전체 시간표를 그대로
저장한다 — 대시보드에서 항공사를 펼치면 "전체 시간대"를 보여줘야 하기 때문이다.
신호등(항공권 유무) 요약은 in_target_window=true 인 편만으로 계산한다.

사용법:
    python src/scan.py                 # provider=mock (기본, 네트워크 불필요)
    python src/scan.py --provider live # config/selectors.yaml 이 검증된 항공사만 실조회
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path

import rules
from providers.base import FlightOffer, ProviderError
from providers.mock_provider import MockProvider

DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "results.json"
WEEKS_AHEAD_DEFAULT = 8  # 약 2개월


def _make_provider(airline_code: str, provider_kind: str):
    if provider_kind == "mock":
        return MockProvider(airline_code)
    if provider_kind == "live":
        from providers.playwright_provider import PlaywrightFlightProvider

        return PlaywrightFlightProvider(airline_code)
    raise ValueError(provider_kind)


def scan_route(
    origin: str,
    dest: str,
    dates: list[dt.date],
    provider_kind: str,
    direction: str,
) -> tuple[list[dict], list[dict]]:
    results: list[dict] = []
    skipped: list[dict] = []
    time_filter = rules.is_valid_outbound_departure if direction == "outbound" else rules.is_valid_inbound_arrival

    for airline_code in rules.AIRLINE_PRIORITY:
        provider = _make_provider(airline_code, provider_kind)
        for date in dates:
            try:
                offers: list[FlightOffer] = provider.search(origin, dest, date)
            except ProviderError as e:
                skipped.append({"airline": airline_code, "date": date.isoformat(), "reason": str(e)})
                continue

            flag = rules.demand_flag(date)
            for offer in offers:
                if not offer.is_direct:
                    continue
                relevant_dt = offer.dep_dt if direction == "outbound" else offer.arr_dt
                results.append(
                    {
                        **offer.to_dict(),
                        "in_target_window": time_filter(relevant_dt),
                        "demand": {
                            "is_holiday": flag.is_holiday,
                            "holiday_name": flag.holiday_name,
                            "is_sandwich_day": flag.is_sandwich_day,
                            "is_long_weekend": flag.is_long_weekend,
                            "is_high_demand": flag.is_high_demand,
                        },
                    }
                )
    return results, skipped


def run(provider_kind: str, weeks_ahead: int) -> dict:
    today = dt.date.today()
    outbound_dates = rules.candidate_outbound_dates(today, weeks_ahead)
    inbound_dates = rules.candidate_inbound_dates(today, weeks_ahead)

    outbound_results, outbound_skipped = scan_route("GMP", "CJU", outbound_dates, provider_kind, "outbound")
    inbound_results, inbound_skipped = scan_route("CJU", "GMP", inbound_dates, provider_kind, "inbound")

    output = {
        "generated_at": dt.datetime.now().isoformat(),
        "provider": provider_kind,
        "window_weeks": weeks_ahead,
        "rules": {
            "outbound": "금요일 10:00 이후 출발 또는 토요일 오전(00:00-11:59) 출발",
            "inbound": "일요일 18:00 이후 도착 또는 월요일 전체",
            "airline_priority": rules.AIRLINE_PRIORITY,
            "direct_only": True,
        },
        "outbound": {"route": "GMP->CJU", "flights": outbound_results, "skipped": outbound_skipped},
        "inbound": {"route": "CJU->GMP", "flights": inbound_results, "skipped": inbound_skipped},
    }
    return output


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", choices=["mock", "live"], default="mock")
    parser.add_argument("--weeks-ahead", type=int, default=WEEKS_AHEAD_DEFAULT)
    args = parser.parse_args()

    output = run(args.provider, args.weeks_ahead)
    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    DATA_PATH.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")

    n_out = sum(1 for f in output["outbound"]["flights"] if f["in_target_window"])
    n_in = sum(1 for f in output["inbound"]["flights"] if f["in_target_window"])
    print(f"[scan] provider={args.provider} outbound(창내)={n_out}건 inbound(창내)={n_in}건 -> {DATA_PATH}")
    if output["outbound"]["skipped"] or output["inbound"]["skipped"]:
        print(
            f"[scan] 건너뛴 항공사/날짜: outbound={len(output['outbound']['skipped'])}, "
            f"inbound={len(output['inbound']['skipped'])} (사유는 results.json 참조)"
        )


if __name__ == "__main__":
    main()
