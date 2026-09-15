"""테스트/개발용 목업 Provider.

실제 가격이 아닌 재현 가능한 가짜 데이터를 생성한다. scan.py 파이프라인과
대시보드를 네트워크 없이 검증하기 위한 용도이며, 결과 JSON에는 항상
source="mock"으로 표시되어 실데이터와 절대 혼동되지 않는다.
"""

from __future__ import annotations

import datetime as dt
import hashlib

from providers.base import FlightOffer, FlightSearchProvider
from rules import AIRLINE_NAMES

_SCHEDULE_BY_AIRLINE = {
    # (출발시각 후보) — 실제 시간표가 아니라 데모용 예시 시각.
    "KE": ["07:00", "10:30", "15:20", "19:40"],
    "OZ": ["08:10", "13:00", "18:30"],
    "7C": ["06:30", "09:50", "17:10"],
    "TW": ["07:40", "20:10"],
    "BX": ["11:20"],
    "RS": ["21:00"],
    "ZE": ["16:00"],
}


def _deterministic_price(seed: str, low: int, high: int) -> int:
    h = int(hashlib.sha256(seed.encode()).hexdigest(), 16)
    return low + (h % (high - low + 1))


class MockProvider(FlightSearchProvider):
    def __init__(self, airline_code: str):
        self.airline_code = airline_code

    def search(self, origin: str, dest: str, date: dt.date) -> list[FlightOffer]:
        offers: list[FlightOffer] = []
        for i, hhmm in enumerate(_SCHEDULE_BY_AIRLINE.get(self.airline_code, [])):
            h, m = map(int, hhmm.split(":"))
            dep = dt.datetime.combine(date, dt.time(h, m))
            arr = dep + dt.timedelta(minutes=55)
            seed = f"{self.airline_code}-{origin}-{dest}-{date.isoformat()}-{i}"
            price = _deterministic_price(seed, 39000, 145000)
            bookable = _deterministic_price(seed + "-seat", 0, 9) > 0  # 10%는 매진으로 시뮬레이션
            offers.append(
                FlightOffer(
                    airline_code=self.airline_code,
                    airline_name=AIRLINE_NAMES.get(self.airline_code, self.airline_code),
                    flight_no=f"{self.airline_code}{100 + i}",
                    origin=origin,
                    dest=dest,
                    dep_dt=dep,
                    arr_dt=arr,
                    price_krw=price,
                    is_direct=True,
                    bookable=bookable,
                    source="mock",
                    booking_url=None,
                    fetched_at=dt.datetime.now(),
                )
            )
        return offers
