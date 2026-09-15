"""공항별 날씨 예보를 조회해 data/weather.json 으로 저장한다.

항공권과 달리 날씨는 갱신 주기가 짧아야 의미가 있으므로, 매주가 아니라
매일 실행하는 것을 권장한다 (weather-scan.yml 참고). 예보 범위(약 14일)를
넘는 날짜는 항목 자체를 만들지 않는다 — 대시보드가 "예보 없음"으로 표시한다.

사용법:
    python src/weather_scan.py                 # provider=mock (기본)
    python src/weather_scan.py --provider live # Open-Meteo 실조회 (네트워크 필요)
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path

from providers.weather import AIRPORT_COORDS, FORECAST_HORIZON_DAYS, WeatherProviderError

DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "weather.json"


def _make_provider(kind: str):
    if kind == "mock":
        from providers.mock_weather import MockWeatherProvider

        return MockWeatherProvider()
    if kind == "live":
        from providers.weather import OpenMeteoWeatherProvider

        return OpenMeteoWeatherProvider()
    raise ValueError(kind)


def run(provider_kind: str) -> dict:
    provider = _make_provider(provider_kind)
    today = dt.date.today()

    by_airport: dict[str, dict[str, dict]] = {code: {} for code in AIRPORT_COORDS}
    errors: list[dict] = []

    for airport_code in AIRPORT_COORDS:
        for offset in range(FORECAST_HORIZON_DAYS + 1):
            date = today + dt.timedelta(days=offset)
            try:
                info = provider.get_forecast(airport_code, date)
            except WeatherProviderError as e:
                errors.append({"airport": airport_code, "date": date.isoformat(), "reason": str(e)})
                continue
            if info is not None:
                by_airport[airport_code][date.isoformat()] = info.to_dict()

    return {
        "generated_at": dt.datetime.now().isoformat(),
        "provider": provider_kind,
        "forecast_horizon_days": FORECAST_HORIZON_DAYS,
        "by_airport": by_airport,
        "errors": errors,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", choices=["mock", "live"], default="mock")
    args = parser.parse_args()

    output = run(args.provider)
    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    DATA_PATH.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    n = sum(len(v) for v in output["by_airport"].values())
    print(f"[weather_scan] provider={args.provider} {n}건 -> {DATA_PATH}")
    if output["errors"]:
        print(f"[weather_scan] 실패 {len(output['errors'])}건 (weather.json의 errors 참조)")


if __name__ == "__main__":
    main()
