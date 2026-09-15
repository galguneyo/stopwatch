"""테스트/개발용 목업 Provider.

실제 가격이 아닌 재현 가능한 가짜 데이터를 생성한다. scan.py 파이프라인과
대시보드를 네트워크 없이 검증하기 위한 용도이며, 결과 JSON에는 항상
source="mock"으로 표시되어 실데이터와 절대 혼동되지 않는다.

하루 전체 시간대를 생성한다 (사용자가 지정한 요일/시간 창 밖의 편도 포함) —
대시보드에서 항공사를 펼치면 '전체 시간대'를 보여줘야 하기 때문이다.
어떤 편이 검색 조건(창) 안에 있는지는 scan.py가 별도로 태깅한다.
"""

from __future__ import annotations

import datetime as dt
import hashlib

from providers.base import FlightOffer, FlightSearchProvider, SeatStatus
from rules import AIRLINE_NAMES

# 하루 전체 시간표 예시(데모용). 실제 시간표가 아님.
_SCHEDULE_BY_AIRLINE = {
    "KE": ["07:00", "08:20", "10:30", "12:40", "15:20", "17:00", "19:40", "21:10"],
    "OZ": ["08:10", "11:30", "13:00", "16:20", "18:30", "20:40"],
    "7C": ["06:30", "09:50", "13:20", "17:10", "19:50"],
    "TW": ["07:40", "14:10", "20:10"],
    "BX": ["11:20", "16:50"],
    "RS": ["21:00"],
    "ZE": ["16:00"],
}

# 국내선 비즈니스/프레스티지 클래스는 실질적으로 대형항공사 일부 편에서만 유지되며
# LCC는 전 편 이코노미 단일clase다. 데모 목적의 가정치이며 실제 운영 현황이 아니다.
_HAS_BUSINESS_CABIN = {"KE", "OZ"}


def _stable_int(seed: str, low: int, high: int) -> int:
    h = int(hashlib.sha256(seed.encode()).hexdigest(), 16)
    return low + (h % (high - low + 1))


def synth_history(results: dict, runs: int) -> list:
    """목업 전용: 과거 관측 이력을 합성한다.

    추세·변동성·매진 속도는 관측이 여러 번 쌓여야 계산되는데, 목업은 몇 번을 돌려도
    같은 값이 나와 인사이트 화면이 비어 보인다. 이 함수는 "출발일이 가까울수록,
    수요가 몰리는 날일수록 가격이 오르고 좌석이 줄었다"는 형태의 이력을 만들어
    화면을 확인할 수 있게 한다.

    합성값이며 실제 시장 관측이 아니다 — source 는 "mock"으로 남고 화면에도
    목업 배너가 함께 뜬다.
    """
    import datetime as _dt

    from holidays_2026 import HOLIDAY_BY_DATE
    from insights import Observation, observations_from_results

    today = _dt.date.today()
    out: list[Observation] = []

    for current in observations_from_results(results):
        if current.lowest_krw is None:
            continue
        demand = 2.0 if current.date in HOLIDAY_BY_DATE else 1.0
        # 날짜마다 상승 폭이 조금씩 다르게 — 안 그러면 모든 날의 추세가 똑같이 나온다
        jitter = 0.7 + _stable_int(current.date + current.direction, 0, 60) / 100

        for step in range(runs, 0, -1):  # step이 클수록 먼 과거
            observed = _dt.datetime.combine(today, _dt.time(9, 0)) - _dt.timedelta(days=step * 7)
            discount = max(0.4, 1 - 0.035 * demand * jitter * step)
            out.append(Observation(
                observed_at=observed.isoformat(),
                direction=current.direction,
                date=current.date,
                lowest_krw=max(20000, int(current.lowest_krw * discount)),
                bookable_flights=current.bookable_flights + int(demand * step),
                bookable_carriers=min(7, current.bookable_carriers + (1 if step > 2 else 0)),
                total_flights=current.total_flights,
                source="mock",
            ))

    out.sort(key=lambda o: o.observed_at)
    return out


def _seat_status(seed: str) -> SeatStatus:
    roll = _stable_int(seed, 0, 99)
    if roll < 70:
        return "available"
    if roll < 90:
        return "limited"
    return "soldout"


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

            economy = _stable_int(seed + "-eco", 39000, 145000)
            business = None
            if self.airline_code in _HAS_BUSINESS_CABIN and _stable_int(seed + "-hasbiz", 0, 9) < 6:
                business = economy + _stable_int(seed + "-biz", 40000, 90000)

            status = _seat_status(seed + "-seat")

            offers.append(
                FlightOffer(
                    airline_code=self.airline_code,
                    airline_name=AIRLINE_NAMES.get(self.airline_code, self.airline_code),
                    flight_no=f"{self.airline_code}{100 + i}",
                    origin=origin,
                    dest=dest,
                    dep_dt=dep,
                    arr_dt=arr,
                    economy_price_krw=economy,
                    business_price_krw=business,
                    seat_status=status,
                    is_direct=True,
                    source="mock",
                    booking_url=None,
                    fetched_at=dt.datetime.now(),
                )
            )
        return offers
