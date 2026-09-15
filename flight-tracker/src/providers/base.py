"""항공권 조회 Provider 공통 인터페이스.

모든 Provider(항공사별 실검색기, 목업 등)는 이 인터페이스를 구현한다.
scan.py는 이 인터페이스에만 의존하므로 실검색 로직을 교체/추가해도
날짜 규칙·대시보드 쪽 코드는 건드릴 필요가 없다.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, asdict


@dataclass
class FlightOffer:
    airline_code: str
    airline_name: str
    flight_no: str
    origin: str
    dest: str
    dep_dt: dt.datetime
    arr_dt: dt.datetime
    price_krw: int | None  # 실시간 확인 실패 시 None
    is_direct: bool
    bookable: bool  # 매진/예매마감이면 False
    source: str  # "live" | "mock" — 실데이터인지 목업인지 반드시 구분
    booking_url: str | None = None
    fetched_at: dt.datetime | None = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["dep_dt"] = self.dep_dt.isoformat()
        d["arr_dt"] = self.arr_dt.isoformat()
        d["fetched_at"] = self.fetched_at.isoformat() if self.fetched_at else None
        return d


class FlightSearchProvider:
    """항공사(또는 통합 검색)별 조회기의 공통 인터페이스."""

    airline_code: str = ""

    def search(self, origin: str, dest: str, date: dt.date) -> list[FlightOffer]:
        """origin->dest 직항 편만 반환한다. 네트워크 실패 시 빈 리스트가 아니라
        예외를 던져서 scan.py가 '조회 실패'와 '해당 항공편 없음'을 구분할 수 있게 한다.
        """
        raise NotImplementedError


class ProviderError(RuntimeError):
    """실검색 provider가 데이터를 가져오지 못했을 때 사용한다."""
