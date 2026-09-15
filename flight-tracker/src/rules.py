"""검색 대상 날짜/시간대/공휴일 판정을 담당하는 순수 로직 모듈.

네트워크나 항공사 데이터에 의존하지 않으므로 전부 단위테스트 가능하다.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from holidays_2026 import HOLIDAY_BY_DATE

# 서울 <-> 제주 직항 노선. 서울측 공항은 김포(GMP)가 절대다수이며,
# 일부 LCC가 인천(ICN)-제주 노선을 운영하므로 함께 감시 대상에 둔다.
SEOUL_AIRPORTS = ("GMP", "ICN")
JEJU_AIRPORT = "CJU"

ROUTE_OUTBOUND = ("SEOUL", "CJU")  # 서울 출발 -> 제주 도착
ROUTE_INBOUND = ("CJU", "SEOUL")  # 제주 출발 -> 서울 도착

# 항공사 우선순위: 대한항공/아시아나 최우선, 이후 LCC.
AIRLINE_PRIORITY: list[str] = [
    "KE",  # 대한항공
    "OZ",  # 아시아나항공
    "7C",  # 제주항공
    "TW",  # 티웨이항공
    "BX",  # 에어부산
    "RS",  # 에어서울
    "ZE",  # 이스타항공
]

AIRLINE_NAMES: dict[str, str] = {
    "KE": "대한항공",
    "OZ": "아시아나항공",
    "7C": "제주항공",
    "TW": "티웨이항공",
    "BX": "에어부산",
    "RS": "에어서울",
    "ZE": "이스타항공",
}


def is_holiday(date: dt.date) -> bool:
    return date.isoformat() in HOLIDAY_BY_DATE


def holiday_name(date: dt.date) -> str | None:
    h = HOLIDAY_BY_DATE.get(date.isoformat())
    return h.name if h else None


def is_day_off(date: dt.date) -> bool:
    """주말이거나 공휴일이면 '쉬는 날'로 간주."""
    return date.weekday() >= 5 or is_holiday(date)  # 5=토, 6=일


def is_sandwich_day(date: dt.date) -> bool:
    """앞뒤 하루씩만 쉬는 날 사이에 낀 평일(공휴일 아님)인지 판정.

    예) 2026-01-02(금)는 1/1(목, 신정) 다음날이자 1/3(토) 전날이므로 샌드위치 데이.
    """
    if is_day_off(date):
        return False
    prev_off = is_day_off(date - dt.timedelta(days=1))
    next_off = is_day_off(date + dt.timedelta(days=1))
    return prev_off and next_off


@dataclass(frozen=True)
class DemandFlag:
    is_holiday: bool
    holiday_name: str | None
    is_sandwich_day: bool
    is_long_weekend: bool  # 공휴일이 주말과 붙어 3일 이상 연휴를 이루는지

    @property
    def is_high_demand(self) -> bool:
        return self.is_holiday or self.is_sandwich_day or self.is_long_weekend


def _is_part_of_long_weekend(date: dt.date) -> bool:
    """해당 날짜를 포함해 연속된 '쉬는 날' 블록이 3일 이상인지."""
    if not is_day_off(date):
        return False
    start = date
    while is_day_off(start - dt.timedelta(days=1)):
        start -= dt.timedelta(days=1)
    end = date
    while is_day_off(end + dt.timedelta(days=1)):
        end += dt.timedelta(days=1)
    return (end - start).days + 1 >= 3


def demand_flag(date: dt.date) -> DemandFlag:
    return DemandFlag(
        is_holiday=is_holiday(date),
        holiday_name=holiday_name(date),
        is_sandwich_day=is_sandwich_day(date),
        is_long_weekend=_is_part_of_long_weekend(date),
    )


def is_valid_outbound_departure(dt_: dt.datetime) -> bool:
    """서울->제주: 금요일 오전 10시 이후, 또는 토요일 오전(00:00~11:59) 출발."""
    weekday = dt_.weekday()  # 월=0 ... 금=4, 토=5, 일=6
    if weekday == 4:  # 금요일
        return dt_.time() >= dt.time(10, 0)
    if weekday == 5:  # 토요일
        return dt_.time() < dt.time(12, 0)
    return False


def is_valid_inbound_arrival(dt_: dt.datetime) -> bool:
    """제주->서울: 일요일 저녁 6시 이후 도착, 또는 월요일 전체."""
    weekday = dt_.weekday()
    if weekday == 6:  # 일요일
        return dt_.time() >= dt.time(18, 0)
    if weekday == 0:  # 월요일
        return True
    return False


def candidate_outbound_dates(start: dt.date, weeks_ahead: int) -> list[dt.date]:
    """앞으로 weeks_ahead주 동안의 금요일/토요일 날짜 목록(서울->제주 후보일)."""
    dates: list[dt.date] = []
    d = start
    end = start + dt.timedelta(weeks=weeks_ahead)
    while d <= end:
        if d.weekday() in (4, 5):  # 금, 토
            dates.append(d)
        d += dt.timedelta(days=1)
    return dates


def candidate_inbound_dates(start: dt.date, weeks_ahead: int) -> list[dt.date]:
    """앞으로 weeks_ahead주 동안의 일요일/월요일 날짜 목록(제주->서울 후보일)."""
    dates: list[dt.date] = []
    d = start
    end = start + dt.timedelta(weeks=weeks_ahead)
    while d <= end:
        if d.weekday() in (6, 0):  # 일, 월
            dates.append(d)
        d += dt.timedelta(days=1)
    return dates


def sort_by_airline_priority(airline_codes: list[str]) -> list[str]:
    def key(code: str) -> int:
        try:
            return AIRLINE_PRIORITY.index(code)
        except ValueError:
            return len(AIRLINE_PRIORITY)

    return sorted(airline_codes, key=key)
