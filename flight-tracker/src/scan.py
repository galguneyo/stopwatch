"""주간 스캔 오케스트레이터.

서울<->제주 직항편을, 대한항공/아시아나 우선 -> LCC 순으로 조회하고
사용자 지정 요일/시간대 규칙에 맞는 항공편만 걸러 data/results.json 에 저장한다.

사용법:
    python src/scan.py                 # provider=mock (기본, 네트워크 불필요)
    python src/scan.py --provider live # config/selectors.yaml 이 검증된 항공사만 실조회

--provider live 인데 아직 검증된 셀렉터가 없는 항공사는 자동으로 건너뛰고
결과 JSON의 "skipped" 목록에 사유와 함께 남긴다 (조용히 목업으로 대체하지 않는다 —
사용자가 "이건 실데이터가 아니다"를 모른 채 실데이터로 오인하지 않도록 하기 위함).
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


def _seoul_origin_for(airline_code: str) -> str:
    # 대부분 GMP. 필요 시 항공사별로 조정 가능하도록 분리해둔다.
    return "GMP"


def scan_route(
    origin: str,
    dest: str,
    dates: list[dt.date],
    provider_kind: str,
    time_filter,
) -> tuple[list[dict], list[dict]]:
    results: list[dict] = []
    skipped: list[dict] = []

    for airline_code in rules.AIRLINE_PRIORITY:
        provider = _make_provider(airline_code, provider_kind)
        for date in dates:
            try:
                offers: list[FlightOffer] = provider.search(origin, dest, date)
            except ProviderError as e:
                skipped.append({"airline": airline_code, "date": date.isoformat(), "reason": str(e)})
                continue

            for offer in offers:
                if not offer.is_direct:
                    continue
                relevant_dt = offer.dep_dt if time_filter is rules.is_valid_outbound_departure else offer.arr_dt
                if not time_filter(relevant_dt):
                    continue
                flag = rules.demand_flag(date)
                results.append(
                    {
                        **offer.to_dict(),
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

    outbound_results, outbound_skipped = scan_route(
        "GMP", "CJU", outbound_dates, provider_kind, rules.is_valid_outbound_departure
    )
    inbound_results, inbound_skipped = scan_route(
        "CJU", "GMP", inbound_dates, provider_kind, rules.is_valid_inbound_arrival
    )

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
    n_out = len(output["outbound"]["flights"])
    n_in = len(output["inbound"]["flights"])
    print(f"[scan] provider={args.provider} outbound={n_out}건 inbound={n_in}건 -> {DATA_PATH}")
    if output["outbound"]["skipped"] or output["inbound"]["skipped"]:
        print(
            f"[scan] 건너뛴 항공사/날짜: outbound={len(output['outbound']['skipped'])}, "
            f"inbound={len(output['inbound']['skipped'])} (사유는 results.json 참조)"
        )


if __name__ == "__main__":
    main()
