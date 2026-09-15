"""당일 지연 정보 목업 Provider. 실제 운항 실적이 아니며 source="mock"으로 표시된다."""

from __future__ import annotations

import datetime as dt
import hashlib

from providers.delay import DELAY_THRESHOLD_MIN, DelayProvider, FlightStatus
from providers.mock_provider import _SCHEDULE_BY_AIRLINE
from rules import AIRLINE_PRIORITY


def _stable_int(seed: str, low: int, high: int) -> int:
    h = int(hashlib.sha256(seed.encode()).hexdigest(), 16)
    return low + (h % (high - low + 1))


class MockDelayProvider(DelayProvider):
    def get_today(self, origin: str, dest: str, date: dt.date) -> list[FlightStatus]:
        out: list[FlightStatus] = []
        for airline in AIRLINE_PRIORITY:
            for i, hhmm in enumerate(_SCHEDULE_BY_AIRLINE.get(airline, [])):
                h, m = map(int, hhmm.split(":"))
                scheduled = dt.datetime.combine(date, dt.time(h, m))
                seed = f"{airline}-{origin}-{dest}-{date.isoformat()}-{i}-delay"

                roll = _stable_int(seed, 0, 99)
                if roll < 4:
                    state, delay, estimated = "cancelled", None, None
                elif roll < 26:
                    delay = _stable_int(seed + "-min", DELAY_THRESHOLD_MIN, 75)
                    state = "delayed"
                    estimated = scheduled + dt.timedelta(minutes=delay)
                else:
                    delay = _stable_int(seed + "-min", 0, DELAY_THRESHOLD_MIN - 1)
                    state = "ontime"
                    estimated = scheduled + dt.timedelta(minutes=delay)

                out.append(FlightStatus(
                    airline_code=airline,
                    flight_no=f"{airline}{100 + i}",
                    origin=origin,
                    dest=dest,
                    scheduled_dt=scheduled.isoformat(),
                    estimated_dt=estimated.isoformat() if estimated else None,
                    state=state,
                    delay_minutes=delay,
                    source="mock",
                ))
        out.sort(key=lambda f: f.scheduled_dt)
        return out
