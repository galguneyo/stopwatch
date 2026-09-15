import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import insights  # noqa: E402
from insights import Observation  # noqa: E402


def obs(date, observed_at, lowest, flights, direction="outbound"):
    return Observation(
        observed_at=observed_at, direction=direction, date=date,
        lowest_krw=lowest, bookable_flights=flights, bookable_carriers=3,
        total_flights=10, source="mock",
    )


def results_with(date, lowest, flights, provider="mock"):
    return {
        "generated_at": "2026-09-15T09:00:00",
        "provider": provider,
        "outbound": {"flights": [{
            "dep_dt": f"{date}T10:30:00", "in_target_window": True,
            "seat_status": "available", "economy_price_krw": lowest, "airline_code": "KE",
        } for _ in range(flights)], "skipped": []},
        "inbound": {"flights": [], "skipped": []},
    }


def test_single_observation_reports_insufficient_not_a_guess():
    res = results_with("2026-10-16", 60000, 5)  # 평일 금요일, 수요 요인 없음
    out = insights.build(res, history=[], today=dt.date(2026, 9, 15))
    row = out["by_direction"]["outbound"][0]
    assert row["observations"] == 0
    assert row["trend_pct"] is None
    assert row["volatility_pct"] is None
    assert row["verdict"] == "insufficient"
    assert any("관측" in r for r in row["reasons"])


def test_rising_price_and_seat_burn_push_to_book_now():
    date = "2026-10-16"
    history = [
        obs(date, "2026-09-01T09:00:00", 50000, 12),
        obs(date, "2026-09-08T09:00:00", 58000, 8),
        obs(date, "2026-09-15T09:00:00", 66000, 4),
    ]
    res = results_with(date, 66000, 4)
    out = insights.build(res, history, today=dt.date(2026, 9, 15))
    row = out["by_direction"]["outbound"][0]

    assert row["trend_pct"] == 32.0            # 50000 -> 66000
    assert row["volatility_pct"] == 32.0
    assert row["flights_lost_per_day"] is not None
    assert row["verdict"] == "book_now"
    assert out["top_actions"][0]["date"] == date


def test_holiday_raises_urgency_even_without_history():
    res = results_with("2026-09-25", 80000, 6)  # 추석
    out = insights.build(res, history=[], today=dt.date(2026, 9, 15))
    row = out["by_direction"]["outbound"][0]
    assert row["demand"]["is_holiday"] is True
    assert row["urgency"] >= 30
    assert any("추석" in r for r in row["reasons"])


def test_sold_out_date_is_marked_gone():
    # 매진은 '편이 없는 것'이 아니라 '편은 있는데 전부 매진'인 상태다.
    res = results_with("2026-10-16", 60000, 3)
    for f in res["outbound"]["flights"]:
        f["seat_status"] = "soldout"
    out = insights.build(res, history=[], today=dt.date(2026, 9, 15))
    row = out["by_direction"]["outbound"][0]
    assert row["bookable_flights"] == 0
    assert row["lowest_krw"] is None
    assert row["verdict"] == "gone"


def test_price_index_compares_against_window_median():
    res = {
        "generated_at": "2026-09-15T09:00:00", "provider": "mock",
        "outbound": {"flights": [
            {"dep_dt": "2026-10-16T10:30:00", "in_target_window": True,
             "seat_status": "available", "economy_price_krw": 50000, "airline_code": "KE"},
            {"dep_dt": "2026-10-17T10:30:00", "in_target_window": True,
             "seat_status": "available", "economy_price_krw": 100000, "airline_code": "KE"},
            {"dep_dt": "2026-10-23T10:30:00", "in_target_window": True,
             "seat_status": "available", "economy_price_krw": 150000, "airline_code": "KE"},
        ], "skipped": []},
        "inbound": {"flights": [], "skipped": []},
    }
    out = insights.build(res, history=[], today=dt.date(2026, 9, 15))
    rows = {r["date"]: r for r in out["by_direction"]["outbound"]}
    assert rows["2026-10-17"]["price_index"] == 1.0    # 중앙값 자신
    assert rows["2026-10-16"]["price_index"] == 0.5
    assert rows["2026-10-23"]["price_index"] == 1.5


def test_observations_ignore_flights_outside_the_time_window():
    res = results_with("2026-10-16", 60000, 2)
    res["outbound"]["flights"].append({
        "dep_dt": "2026-10-16T07:00:00", "in_target_window": False,
        "seat_status": "available", "economy_price_krw": 10000, "airline_code": "KE",
    })
    out = insights.build(res, history=[], today=dt.date(2026, 9, 15))
    row = out["by_direction"]["outbound"][0]
    assert row["lowest_krw"] == 60000          # 창 밖의 10,000원은 무시
    assert row["bookable_flights"] == 2
