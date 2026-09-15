"""날씨 목업 Provider. 실제 기상 데이터가 아니며 source="mock"으로 표시된다."""

from __future__ import annotations

import datetime as dt
import hashlib

from providers.weather import FORECAST_HORIZON_DAYS, WeatherInfo, WeatherProvider

_SUMMARIES = ["맑음", "대체로 맑음", "부분 흐림", "흐림", "약한 비", "비"]


def _stable_int(seed: str, low: int, high: int) -> int:
    h = int(hashlib.sha256(seed.encode()).hexdigest(), 16)
    return low + (h % (high - low + 1))


class MockWeatherProvider(WeatherProvider):
    def get_forecast(self, airport_code: str, date: dt.date) -> WeatherInfo | None:
        if date - dt.date.today() > dt.timedelta(days=FORECAST_HORIZON_DAYS):
            return None
        seed = f"{airport_code}-{date.isoformat()}"
        summary = _SUMMARIES[_stable_int(seed + "-s", 0, len(_SUMMARIES) - 1)]
        precip = _stable_int(seed + "-p", 0, 90) if "비" in summary else _stable_int(seed + "-p", 0, 20)
        wind = round(_stable_int(seed + "-w", 5, 45) / 10 * 10, 1)
        high = _stable_int(seed + "-h", 15, 27)
        low = high - _stable_int(seed + "-l", 3, 9)
        return WeatherInfo(
            airport_code=airport_code,
            date=date.isoformat(),
            summary=summary,
            precip_probability_pct=precip,
            wind_speed_kmh=float(wind),
            temp_high_c=float(high),
            temp_low_c=float(low),
            source="mock",
        )
