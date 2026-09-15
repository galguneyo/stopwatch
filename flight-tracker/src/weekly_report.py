"""주차별 사전예약 확인 리포트 생성기.

data/results.json 을 읽어 ISO 주차 단위로 묶어, 그 주에 예약해야 할
서울->제주 / 제주->서울 후보 항공편을 요약한 마크다운 리포트를 만든다.
매주 반복되는 "이번 주엔 어떤 편을 예약해야 하나"라는 실무 확인 용도.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
from collections import defaultdict
from pathlib import Path

DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "results.json"
REPORT_PATH = Path(__file__).resolve().parents[1] / "reports" / "latest.md"


def _week_key(iso_date: str) -> tuple[int, int]:
    d = dt.date.fromisoformat(iso_date[:10])
    y, w, _ = d.isocalendar()
    return (y, w)


def _week_label(year: int, week: int) -> str:
    monday = dt.date.fromisocalendar(year, week, 1)
    sunday = monday + dt.timedelta(days=6)
    return f"{year}년 {week}주차 ({monday.isoformat()} ~ {sunday.isoformat()})"


def _best_per_airline(flights: list[dict]) -> list[dict]:
    """항공사별 최저가(예약 가능한 것만, 지정 시간대 내) 1건씩, 우선순위 순으로."""
    from rules import AIRLINE_PRIORITY

    best: dict[str, dict] = {}
    for f in flights:
        if not f["in_target_window"]:
            continue
        if f["seat_status"] == "soldout" or f["economy_price_krw"] is None:
            continue
        code = f["airline_code"]
        if code not in best or f["economy_price_krw"] < best[code]["economy_price_krw"]:
            best[code] = f
    return [best[c] for c in AIRLINE_PRIORITY if c in best]


def _format_flight_line(f: dict) -> str:
    time = f["dep_dt"][11:16]
    price = f"{f['economy_price_krw']:,}원" if f["economy_price_krw"] is not None else "가격 미확인"
    status_note = " (잔여좌석 적음)" if f["seat_status"] == "limited" else ""
    return f"  - {time} {f['airline_name']} {f['flight_no']} — 이코노미 {price}{status_note}"


def build_report(data: dict) -> str:
    lines: list[str] = []
    lines.append(f"# 서울-제주 주차별 사전예약 확인 리포트")
    lines.append("")
    lines.append(f"- 생성 시각: {data['generated_at']}")
    lines.append(f"- 조회 방식: **{data['provider']}**" + ("  ⚠️ 목업 데이터 — 실가격 아님" if data["provider"] == "mock" else ""))
    lines.append(f"- 조회 범위: 향후 {data['window_weeks']}주")
    lines.append("")

    by_week: dict[tuple[int, int], dict[str, list[dict]]] = defaultdict(lambda: {"outbound": [], "inbound": []})
    for f in data["outbound"]["flights"]:
        if f["in_target_window"]:
            by_week[_week_key(f["dep_dt"])]["outbound"].append(f)
    for f in data["inbound"]["flights"]:
        if f["in_target_window"]:
            by_week[_week_key(f["dep_dt"])]["inbound"].append(f)

    if not by_week:
        lines.append("_이번 조회에서는 조건에 맞는 항공편이 없습니다._")
        return "\n".join(lines)

    for year, week in sorted(by_week.keys()):
        bucket = by_week[(year, week)]
        lines.append(f"## {_week_label(year, week)}")

        by_date_out: dict[str, list[dict]] = defaultdict(list)
        for f in bucket["outbound"]:
            by_date_out[f["dep_dt"][:10]].append(f)
        by_date_in: dict[str, list[dict]] = defaultdict(list)
        for f in bucket["inbound"]:
            by_date_in[f["dep_dt"][:10]].append(f)

        demand_notes = set()
        for date_str, flights in {**by_date_out, **by_date_in}.items():
            d = flights[0]["demand"]
            if d["is_holiday"]:
                demand_notes.add(f"{date_str} {d['holiday_name']}")
            elif d["is_sandwich_day"]:
                demand_notes.add(f"{date_str} 샌드위치 데이")
            elif d["is_long_weekend"]:
                demand_notes.add(f"{date_str} 연휴 포함")

        if demand_notes:
            lines.append(f"⚠️ **수요 집중 예상**: {', '.join(sorted(demand_notes))} — 조기 예약 권장")

        lines.append("")
        lines.append("**서울 -> 제주**")
        if not by_date_out:
            lines.append("  - 해당 없음")
        for date_str in sorted(by_date_out):
            weekday = ["월", "화", "수", "목", "금", "토", "일"][dt.date.fromisoformat(date_str).weekday()]
            lines.append(f"- {date_str} ({weekday})")
            for f in _best_per_airline(by_date_out[date_str]):
                lines.append(_format_flight_line(f))

        lines.append("")
        lines.append("**제주 -> 서울**")
        if not by_date_in:
            lines.append("  - 해당 없음")
        for date_str in sorted(by_date_in):
            weekday = ["월", "화", "수", "목", "금", "토", "일"][dt.date.fromisoformat(date_str).weekday()]
            lines.append(f"- {date_str} ({weekday})")
            for f in _best_per_airline(by_date_in[date_str]):
                lines.append(_format_flight_line(f))

        lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default=str(DATA_PATH))
    parser.add_argument("--out", default=str(REPORT_PATH))
    args = parser.parse_args()

    data = json.loads(Path(args.data).read_text(encoding="utf-8"))
    report = build_report(data)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report, encoding="utf-8")
    print(report)


if __name__ == "__main__":
    main()
