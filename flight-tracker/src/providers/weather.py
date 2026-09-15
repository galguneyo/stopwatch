"""공항별 날씨 예보 Provider.

항공권과 마찬가지로 이 세션에는 인터넷 접근이 없어 실제 기상 API 호출은
검증하지 못했다. 다만 Open-Meteo는 API 키가 필요 없는 공개 API라 항공사
스크래핑처럼 셀렉터를 몰라 막히는 문제는 없다 — 네트워크가 열린 환경에서
바로 시도해볼 수 있도록 구현해 두었다. 그래도 "이 세션에서 직접 실행해
검증하지는 못했다"는 사실은 동일하므로, 실패 시 조용히 목업으로 대체하지
않고 예외를 던진다.

일기예보는 물리적으로 먼 미래까지 신뢹할 수 없으므로, 항공권 조회 창(8주)
전체가 아니라 통상적인 단기예보 범위(약 14일)까지만 값을 채우고 그 이후는
"예보 없음"으로 명시한다.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import asdict, dataclass

FORECAST_HORIZON_DAYS = 14  # 일반적인 단기예보 신뢰 구간

AIRPORT_COORDS = {
    "GMP": (37.5583, 126.7906),
    "ICN": (37.4602, 126.4407),
    "CJU": (33.5113, 126.4930),
}

# WMO weather code -> 한글 요약 (Open-Meteo가 사용하는 표준 코드표)
_WMO_SUMMARY = {
    0: "맑음", 1: "대체로 맑음", 2: "부분 흐림", 3: "흐림",
    45: "안개", 48: "짙은 안개",
    51: "약한 이슬비", 53: "이슬비", 55: "강한 이슬비",
    61: "약한 비", 63: "비", 65: "강한 비",
    71: "약한 눈", 73: "눈", 75: "폭설",
    80: "약한 소나기", 81: "소나기", 82: "강한 소나기",
    95: "뇌우",
}


@dataclass
class WeatherInfo:
    airport_code: str
    date: str  # YYYY-MM-DD
    summary: str
    precip_probability_pct: int | None
    wind_speed_kmh: float | None
    temp_high_c: float | None
    temp_low_c: float | None
    source: str  # "live" | "mock"

    def to_dict(self) -> dict:
        return asdict(self)


class WeatherProvider:
    def get_forecast(self, airport_code: str, date: dt.date) -> WeatherInfo | None:
        """해당 날짜가 예보 범위 밖이면 None을 반환한다(가짜 값을 만들지 않는다)."""
        raise NotImplementedError


class WeatherProviderError(RuntimeError):
    pass


class OpenMeteoWeatherProvider(WeatherProvider):
    """api.open-meteo.com 기반 실провider. API 키 불필요.

    이 세션에서는 네트워크가 막혀 있어 실제 호출을 검증하지 못했다.
    네트워크가 열린 환경(GitHub Actions 등)에서 먼저 하루치로 확인 후 사용할 것.
    """

    BASE_URL = "https://api.open-meteo.com/v1/forecast"

    def get_forecast(self, airport_code: str, date: dt.date) -> WeatherInfo | None:
        if date - dt.date.today() > dt.timedelta(days=FORECAST_HORIZON_DAYS):
            return None
        if airport_code not in AIRPORT_COORDS:
            raise WeatherProviderError(f"알 수 없는 공항 코드: {airport_code}")

        try:
            import requests
        except ImportError as e:
            raise WeatherProviderError("requests 패키지가 필요합니다 (pip install requests)") from e

        lat, lon = AIRPORT_COORDS[airport_code]
        params = {
            "latitude": lat,
            "longitude": lon,
            "daily": "weathercode,precipitation_probability_max,windspeed_10m_max,temperature_2m_max,temperature_2m_min",
            "timezone": "Asia/Seoul",
            "start_date": date.isoformat(),
            "end_date": date.isoformat(),
        }
        try:
            res = requests.get(self.BASE_URL, params=params, timeout=10)
            res.raise_for_status()
            daily = res.json()["daily"]
        except Exception as e:  # noqa: BLE001
            raise WeatherProviderError(f"{airport_code} {date} 날씨 조회 실패: {e}") from e

        code = daily["weathercode"][0]
        return WeatherInfo(
            airport_code=airport_code,
            date=date.isoformat(),
            summary=_WMO_SUMMARY.get(code, f"코드 {code}"),
            precip_probability_pct=daily["precipitation_probability_max"][0],
            wind_speed_kmh=daily["windspeed_10m_max"][0],
            temp_high_c=daily["temperature_2m_max"][0],
            temp_low_c=daily["temperature_2m_min"][0],
            source="live",
        )
