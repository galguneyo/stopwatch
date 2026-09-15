import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import booking_links  # noqa: E402


def test_unverified_config_falls_back_to_entry_page():
    link = booking_links.resolve("KE", "GMP", "CJU", dt.date(2026, 9, 18))
    assert link.url.startswith("https://")
    assert link.is_deep is False   # 딥링크를 추측해 넣지 않았음


def test_every_airline_has_a_reachable_looking_entry_url():
    for code in ("KE", "OZ", "7C", "TW", "BX", "RS", "ZE"):
        link = booking_links.resolve(code, "GMP", "CJU", dt.date(2026, 9, 18))
        assert link.url and link.url.startswith("https://"), code


def test_unknown_airline_yields_no_link_rather_than_a_guess():
    link = booking_links.resolve("XX", "GMP", "CJU", dt.date(2026, 9, 18))
    assert link.url is None
    assert link.is_deep is False


def test_verified_deep_link_is_filled_with_route_and_date(monkeypatch):
    monkeypatch.setattr(booking_links, "_config", lambda: {
        "KE": {
            "verified": True,
            "entry_url": "https://example.com",
            "deep_link": "https://example.com/s?d={origin}&a={dest}&on={date}&iso={date_dash}",
        }
    })
    link = booking_links.resolve("KE", "GMP", "CJU", dt.date(2026, 9, 18))
    assert link.is_deep is True
    assert link.url == "https://example.com/s?d=GMP&a=CJU&on=20260918&iso=2026-09-18"


def test_deep_link_ignored_while_unverified(monkeypatch):
    monkeypatch.setattr(booking_links, "_config", lambda: {
        "KE": {
            "verified": False,
            "entry_url": "https://example.com",
            "deep_link": "https://example.com/s?d={origin}",
        }
    })
    link = booking_links.resolve("KE", "GMP", "CJU", dt.date(2026, 9, 18))
    assert link.url == "https://example.com"
    assert link.is_deep is False
