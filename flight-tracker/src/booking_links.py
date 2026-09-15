"""항공편에서 항공사 예매 화면으로 나가는 링크를 만든다.

노선·날짜가 채워진 딥링크가 설정되어 있으면 그것을, 없으면 예매 진입 페이지를
돌려준다. 어느 쪽인지는 호출한 쪽이 알 수 있게 함께 반환해서, 화면에서
"날짜는 직접 선택해야 한다"고 안내할 수 있게 한다.
"""

from __future__ import annotations

import datetime as dt
from functools import lru_cache
from pathlib import Path
from typing import NamedTuple

CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "booking_links.yaml"


class BookingLink(NamedTuple):
    url: str | None
    is_deep: bool  # True면 노선·날짜가 채워진 검색 결과로 바로 간다


@lru_cache(maxsize=1)
def _config() -> dict:
    import yaml

    if not CONFIG_PATH.exists():
        return {}
    return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}


def resolve(airline_code: str, origin: str, dest: str, date: dt.date) -> BookingLink:
    cfg = _config().get(airline_code)
    if not cfg:
        return BookingLink(None, False)

    template = cfg.get("deep_link") or ""
    if template and cfg.get("verified"):
        url = template.format(
            origin=origin,
            dest=dest,
            date=date.strftime("%Y%m%d"),
            date_dash=date.isoformat(),
        )
        return BookingLink(url, True)

    return BookingLink(cfg.get("entry_url") or None, False)
