"""관측 이력으로부터 구매 판단 인사이트를 계산한다.

원칙: 모든 근거 문구는 실제로 계산한 수치에서만 나온다. 이력이 모자라면
추세·변동성을 추정하지 않고 "관측 N회"라고 밝힌다. 작년 패턴이나 업계 통념 같은,
이 저장소가 실제로 관측하지 않은 것은 근거로 쓰지 않는다.

계산 종류
  - 가격 지수 : 같은 조회 구간 내 다른 후보일들의 최저가 중앙값 대비 몇 %인지
                (스냅샷 1회만 있어도 계산 가능)
  - 추세      : 최저가가 처음 관측 대비 얼마나 움직였는지 (관측 2회 이상)
  - 변동성    : 최저가의 (최대-최소)/최소 (관측 3회 이상)
  - 매진 속도 : 예약 가능 편수가 하루에 몇 편씩 줄었는지, 이 속도면 언제 동나는지
                (관측 2회 이상, 단순 선형 외삽임을 명시)
"""

from __future__ import annotations

import datetime as dt
import json
import statistics
from dataclasses import asdict, dataclass, field
from pathlib import Path

HISTORY_PATH = Path(__file__).resolve().parents[1] / "data" / "history.jsonl"

MIN_OBS_TREND = 2
MIN_OBS_VOLATILITY = 3

VERDICT_LABELS = {
    "gone": "매진",
    "book_now": "지금 예약",
    "watch": "주시",
    "relaxed": "여유",
    "insufficient": "관측 부족",
}


@dataclass
class Observation:
    observed_at: str
    direction: str
    date: str
    lowest_krw: int | None
    bookable_flights: int
    bookable_carriers: int
    total_flights: int
    source: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class DateInsight:
    direction: str
    date: str
    days_until: int
    observations: int
    lowest_krw: int | None
    price_index: float | None
    trend_pct: float | None
    volatility_pct: float | None
    bookable_flights: int
    flights_lost_per_day: float | None
    days_to_soldout: float | None
    demand: dict
    urgency: int
    verdict: str
    headline: str
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def observations_from_results(results: dict) -> list[Observation]:
    """스캔 결과 한 건을 날짜별 관측 레코드로 압축한다."""
    out: list[Observation] = []
    observed_at = results["generated_at"]
    source = results["provider"]

    for direction in ("outbound", "inbound"):
        by_date: dict[str, list[dict]] = {}
        for f in results[direction]["flights"]:
            if not f["in_target_window"]:
                continue
            by_date.setdefault(f["dep_dt"][:10], []).append(f)

        for date, flights in by_date.items():
            open_flights = [f for f in flights if f["seat_status"] != "soldout" and f["economy_price_krw"] is not None]
            prices = [f["economy_price_krw"] for f in open_flights]
            out.append(Observation(
                observed_at=observed_at,
                direction=direction,
                date=date,
                lowest_krw=min(prices) if prices else None,
                bookable_flights=len(open_flights),
                bookable_carriers=len({f["airline_code"] for f in open_flights}),
                total_flights=len(flights),
                source=source,
            ))
    return out


def append_history(observations: list[Observation], path: Path = HISTORY_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        for obs in observations:
            fh.write(json.dumps(obs.to_dict(), ensure_ascii=False) + "\n")


def load_history(path: Path = HISTORY_PATH) -> list[Observation]:
    if not path.exists():
        return []
    out: list[Observation] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            out.append(Observation(**json.loads(line)))
    return out


def _series(history: list[Observation], direction: str, date: str) -> list[Observation]:
    rows = [o for o in history if o.direction == direction and o.date == date]
    rows.sort(key=lambda o: o.observed_at)
    return rows


def _pct(new: float, old: float) -> float | None:
    if not old:
        return None
    return round((new - old) / old * 100, 1)


def _days_between(a: str, b: str) -> float:
    return (dt.datetime.fromisoformat(b) - dt.datetime.fromisoformat(a)).total_seconds() / 86400


def build(results: dict, history: list[Observation], today: dt.date | None = None) -> dict:
    today = today or dt.date.today()
    current = observations_from_results(results)

    # 이력 파일에는 목업 관측과 실관측이 함께 쌓일 수 있다. 목업으로 만든 추세를
    # 실데이터 판단의 근거로 쓰면 안 되므로, 지금 돌린 것과 같은 출처만 본다.
    history = [o for o in history if o.source == results["provider"]]

    by_direction: dict[str, list[dict]] = {}
    for direction in ("outbound", "inbound"):
        now_rows = [o for o in current if o.direction == direction]
        medians = [o.lowest_krw for o in now_rows if o.lowest_krw is not None]
        median_price = statistics.median(medians) if medians else None

        insights = [
            _insight_for(o, _series(history, direction, o.date), median_price, today)
            for o in sorted(now_rows, key=lambda o: o.date)
        ]
        by_direction[direction] = [i.to_dict() for i in insights]

    ranked = sorted(
        (i for rows in by_direction.values() for i in rows if i["verdict"] in ("book_now", "watch")),
        key=lambda i: (-i["urgency"], i["date"]),
    )

    return {
        "generated_at": dt.datetime.now().isoformat(),
        "source": results["provider"],
        "observation_runs": len({o.observed_at for o in history}) or 1,
        "by_direction": by_direction,
        "top_actions": ranked[:4],
    }


def _insight_for(
    now: Observation,
    series: list[Observation],
    median_price: float | None,
    today: dt.date,
) -> DateInsight:
    days_until = (dt.date.fromisoformat(now.date) - today).days
    obs = len(series)
    reasons: list[str] = []
    urgency = 0

    price_index = None
    if now.lowest_krw is not None and median_price:
        price_index = round(now.lowest_krw / median_price, 3)
        delta = (price_index - 1) * 100
        if abs(delta) >= 12:
            reasons.append(f"같은 기간 다른 후보일 중앙값 대비 {delta:+.0f}%")

    prices = [o.lowest_krw for o in series if o.lowest_krw is not None]

    trend_pct = None
    if len(prices) >= MIN_OBS_TREND:
        trend_pct = _pct(prices[-1], prices[0])
        if trend_pct is not None and abs(trend_pct) >= 5:
            reasons.append(f"최저가가 첫 관측 대비 {trend_pct:+.0f}% ({obs}회 관측)")
            if trend_pct >= 10:
                urgency += 25
            elif trend_pct <= -10:
                urgency -= 10

    volatility_pct = None
    if len(prices) >= MIN_OBS_VOLATILITY and min(prices):
        volatility_pct = round((max(prices) - min(prices)) / min(prices) * 100, 1)
        if volatility_pct >= 25:
            reasons.append(f"가격 변동 폭이 {volatility_pct:.0f}%로 큽니다")
            urgency += 10

    flights_lost_per_day = None
    days_to_soldout = None
    if obs >= MIN_OBS_TREND:
        span = _days_between(series[0].observed_at, series[-1].observed_at)
        lost = series[0].bookable_flights - series[-1].bookable_flights
        if span > 0 and lost > 0:
            flights_lost_per_day = round(lost / span, 2)
            reasons.append(f"예약 가능 편이 {series[0].bookable_flights}→{series[-1].bookable_flights}편으로 줄었습니다")
            if flights_lost_per_day > 0:
                days_to_soldout = round(now.bookable_flights / flights_lost_per_day, 1)
                if days_to_soldout <= days_until:
                    reasons.append(f"이 속도가 이어지면 출발 {days_until}일 전보다 앞서 매진될 수 있습니다 (단순 선형 추정)")
                    urgency += 30

    demand = _demand_for(now)
    if demand.get("is_holiday"):
        reasons.append(f"{demand.get('holiday_name')} — 수요가 몰리는 날")
        urgency += 30
    elif demand.get("is_sandwich_day"):
        reasons.append("샌드위치 데이 — 연차 사용이 몰립니다")
        urgency += 25
    elif demand.get("is_long_weekend"):
        reasons.append("3일 이상 연휴 구간")
        urgency += 20

    if 0 <= days_until <= 21 and urgency >= 20:
        reasons.append(f"출발까지 {days_until}일 남았습니다")
        urgency += 15

    if now.bookable_flights == 0:
        verdict = "gone"
        urgency = 100
    elif obs < MIN_OBS_TREND and urgency < 20:
        verdict = "insufficient"
    elif urgency >= 60:
        verdict = "book_now"
    elif urgency >= 35:
        verdict = "watch"
    else:
        verdict = "relaxed"

    if obs < MIN_OBS_TREND:
        reasons.append(f"관측 {obs}회 — 추세·매진 속도는 관측이 쌓인 뒤 계산됩니다")

    return DateInsight(
        direction=now.direction,
        date=now.date,
        days_until=days_until,
        observations=obs,
        lowest_krw=now.lowest_krw,
        price_index=price_index,
        trend_pct=trend_pct,
        volatility_pct=volatility_pct,
        bookable_flights=now.bookable_flights,
        flights_lost_per_day=flights_lost_per_day,
        days_to_soldout=days_to_soldout,
        demand=demand,
        urgency=max(0, min(100, urgency)),
        verdict=verdict,
        headline=_headline(verdict, now, days_until),
        reasons=reasons,
    )


_DEMAND_CACHE: dict[str, dict] = {}


def _demand_for(obs: Observation) -> dict:
    if obs.date not in _DEMAND_CACHE:
        import rules

        flag = rules.demand_flag(dt.date.fromisoformat(obs.date))
        _DEMAND_CACHE[obs.date] = {
            "is_holiday": flag.is_holiday,
            "holiday_name": flag.holiday_name,
            "is_sandwich_day": flag.is_sandwich_day,
            "is_long_weekend": flag.is_long_weekend,
        }
    return _DEMAND_CACHE[obs.date]


def _headline(verdict: str, now: Observation, days_until: int) -> str:
    route = "서울→제주" if now.direction == "outbound" else "제주→서울"
    if verdict == "gone":
        return f"{route} {now.date} 조건에 맞는 좌석이 없습니다"
    if verdict == "book_now":
        return f"{route} {now.date} 지금 예약하세요"
    if verdict == "watch":
        return f"{route} {now.date} 지켜볼 구간입니다"
    if verdict == "insufficient":
        return f"{route} {now.date} 아직 판단할 관측이 부족합니다"
    return f"{route} {now.date} 서두르지 않아도 됩니다"
