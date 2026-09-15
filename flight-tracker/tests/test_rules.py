import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import rules  # noqa: E402


def test_new_years_day_sandwich_day():
    # 2026-01-01(목, 신정) / 01-02(금) / 01-03(토) / 01-04(일)
    assert rules.is_day_off(dt.date(2026, 1, 1)) is True
    assert rules.is_sandwich_day(dt.date(2026, 1, 2)) is True
    assert rules.is_sandwich_day(dt.date(2026, 1, 1)) is False  # 공휴일 자체는 제외


def test_children_day_monday_sandwich():
    # 2026-05-05(화, 어린이날) -> 05-04(월)이 샌드위치 데이
    assert dt.date(2026, 5, 5).weekday() == 1  # 화요일
    assert rules.is_sandwich_day(dt.date(2026, 5, 4)) is True


def test_substitute_holidays():
    assert rules.is_holiday(dt.date(2026, 3, 2))  # 삼일절 대체공휴일
    assert rules.is_holiday(dt.date(2026, 8, 17))  # 광복절 대체공휴일
    assert rules.is_holiday(dt.date(2026, 10, 5))  # 개천절 대체공휴일


def test_long_weekend_chuseok():
    flag = rules.demand_flag(dt.date(2026, 9, 25))
    assert flag.is_holiday is True
    assert flag.is_long_weekend is True  # 9/24(목)~9/27(일) 4일 연휴


def test_outbound_departure_window():
    # 금요일 09:59 -> 불가, 10:00 -> 가능
    fri_before = dt.datetime(2026, 9, 18, 9, 59)  # 2026-09-18은 금요일
    fri_after = dt.datetime(2026, 9, 18, 10, 0)
    assert fri_before.weekday() == 4
    assert rules.is_valid_outbound_departure(fri_before) is False
    assert rules.is_valid_outbound_departure(fri_after) is True

    sat_morning = dt.datetime(2026, 9, 19, 8, 0)
    sat_noon = dt.datetime(2026, 9, 19, 12, 0)
    assert rules.is_valid_outbound_departure(sat_morning) is True
    assert rules.is_valid_outbound_departure(sat_noon) is False

    sunday = dt.datetime(2026, 9, 20, 8, 0)
    assert rules.is_valid_outbound_departure(sunday) is False


def test_inbound_arrival_window():
    sun_before = dt.datetime(2026, 9, 20, 17, 59)
    sun_after = dt.datetime(2026, 9, 20, 18, 0)
    assert rules.is_valid_inbound_arrival(sun_before) is False
    assert rules.is_valid_inbound_arrival(sun_after) is True

    monday_early = dt.datetime(2026, 9, 21, 0, 30)
    monday_late = dt.datetime(2026, 9, 21, 23, 30)
    assert rules.is_valid_inbound_arrival(monday_early) is True
    assert rules.is_valid_inbound_arrival(monday_late) is True

    tuesday = dt.datetime(2026, 9, 22, 10, 0)
    assert rules.is_valid_inbound_arrival(tuesday) is False


def test_candidate_dates_only_expected_weekdays():
    start = dt.date(2026, 9, 15)  # 화요일
    outbound = rules.candidate_outbound_dates(start, weeks_ahead=2)
    assert all(d.weekday() in (4, 5) for d in outbound)

    inbound = rules.candidate_inbound_dates(start, weeks_ahead=2)
    assert all(d.weekday() in (6, 0) for d in inbound)


def test_airline_priority_sort():
    shuffled = ["ZE", "OZ", "7C", "KE", "BX"]
    assert rules.sort_by_airline_priority(shuffled) == ["KE", "OZ", "7C", "BX", "ZE"]
