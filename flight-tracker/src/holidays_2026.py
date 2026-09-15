"""2026년 대한민국 법정공휴일 데이터.

출처(2026-09-15 기준, 다수 언론·공공정보 교차 확인):
- 한국경제, 위키트리, KKday, wegive, trip.com 등 2026년 공휴일 보도 (WebSearch 교차 확인)
- 요일은 그레고리력 기준으로 재계산하여 보도 내용과 일치함을 검증함

주의: 정부의 공식 관보/법정공휴일 고시를 실시간으로 조회할 수 있는 네트워크 접근이
이 개발 환경에서는 차단되어 있어(egress policy), 아래 목록은 2026-09-15 시점의
언론 보도를 근거로 작성되었습니다. 실제 운영 전 반드시 행정안전부 또는
data.go.kr의 "특일 정보" API(그때는 네트워크가 열려 있는 배포 환경, 예: GitHub
Actions)로 최종 확인/자동 갱신하는 것을 권장합니다.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Holiday:
    date: str  # YYYY-MM-DD
    name: str
    is_substitute: bool = False


HOLIDAYS_2026: list[Holiday] = [
    Holiday("2026-01-01", "신정"),
    Holiday("2026-02-16", "설날연휴"),
    Holiday("2026-02-17", "설날"),
    Holiday("2026-02-18", "설날연휴"),
    Holiday("2026-03-01", "삼일절"),
    Holiday("2026-03-02", "삼일절 대체공휴일", is_substitute=True),
    Holiday("2026-05-05", "어린이날"),
    Holiday("2026-05-24", "부처님오신날"),
    Holiday("2026-05-25", "부처님오신날 대체공휴일", is_substitute=True),
    Holiday("2026-06-03", "제9회 전국동시지방선거일(임시공휴일)"),
    Holiday("2026-06-06", "현충일"),
    Holiday("2026-07-17", "제헌절"),  # 2026년부터 공휴일로 부활(2008년 이후 최초)
    Holiday("2026-08-15", "광복절"),
    Holiday("2026-08-17", "광복절 대체공휴일", is_substitute=True),
    Holiday("2026-09-24", "추석연휴"),
    Holiday("2026-09-25", "추석"),
    Holiday("2026-09-26", "추석연휴"),
    Holiday("2026-10-03", "개천절"),
    Holiday("2026-10-05", "개천절 대체공휴일", is_substitute=True),
    Holiday("2026-10-09", "한글날"),
    Holiday("2026-12-25", "성탄절"),
]

HOLIDAY_BY_DATE: dict[str, Holiday] = {h.date: h for h in HOLIDAYS_2026}
