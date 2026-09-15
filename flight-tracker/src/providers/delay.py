"""당일 항공기 출발/도착 지연 정보 Provider.

국내선 지연·결항 정보는 한국공항공사가 공공데이터포털에 공개한
"실시간 항공운항 현황 정보 상세 조회 서비스"(data.go.kr 15113771)가 정확히
그 용도다. 다만 서비스 키(활용신청)가 필요하고, 정확한 엔드포인트 경로와
응답 필드명은 포털 로그인 뒤 문서에서 확인해야 한다.

그래서 항공사 셀렉터와 같은 원칙을 적용한다 — 확인되지 않은 값을 코드에
박아 넣지 않고 `config/delay_api.yaml`에 두고, `verified: true`가 되기 전에는
의도적으로 실패한다. 추측한 필드명으로 조용히 빈 데이터를 만들어내면
"지연 없음"처럼 보여서 오히려 위험하기 때문이다.
"""

from __future__ import annotations

import datetime as dt
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "delay_api.yaml"

FlightState = Literal["ontime", "delayed", "cancelled", "departed", "arrived", "unknown"]

# 지연으로 간주하는 최소 분. 국내선은 15분을 정시운항 기준으로 쓰는 것이 관례다.
DELAY_THRESHOLD_MIN = 15


@dataclass
class FlightStatus:
    airline_code: str
    flight_no: str
    origin: str
    dest: str
    scheduled_dt: str  # ISO8601
    estimated_dt: str | None  # 변경된 시각 (없으면 None)
    state: FlightState
    delay_minutes: int | None
    source: str  # "live" | "mock"

    def to_dict(self) -> dict:
        return asdict(self)


class DelayProvider:
    def get_today(self, origin: str, dest: str, date: dt.date) -> list[FlightStatus]:
        raise NotImplementedError


class DelayProviderError(RuntimeError):
    pass


def summarize(flights: list[FlightStatus]) -> dict[str, Any]:
    """정시율·평균 지연을 계산한다. 결항은 정시율 분모에서 제외하지 않는다 —
    이용자 입장에서 결항은 '정시에 못 간 것'이기 때문이다."""
    total = len(flights)
    if not total:
        return {"total": 0, "delayed": 0, "cancelled": 0, "ontime_rate": None, "avg_delay_min": None}

    cancelled = sum(1 for f in flights if f.state == "cancelled")
    delayed = [f for f in flights if f.state == "delayed" and f.delay_minutes is not None]
    ontime = total - cancelled - len(delayed)

    return {
        "total": total,
        "delayed": len(delayed),
        "cancelled": cancelled,
        "ontime_rate": round(ontime / total, 3),
        "avg_delay_min": round(sum(f.delay_minutes for f in delayed) / len(delayed)) if delayed else None,
    }


def _load_config() -> dict[str, Any]:
    import yaml

    if not CONFIG_PATH.exists():
        raise DelayProviderError(f"{CONFIG_PATH} 가 없습니다.")
    cfg = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}
    if not cfg.get("verified"):
        raise DelayProviderError(
            "config/delay_api.yaml 이 아직 검증(verified: true)되지 않았습니다. "
            "공공데이터포털에서 서비스 키를 발급받고 엔드포인트·필드명을 채운 뒤 사용하세요."
        )
    return cfg


class KacDelayProvider(DelayProvider):
    """한국공항공사 실시간 항공운항 현황 API 기반 provider.

    서비스 키는 코드에 넣지 않고 환경변수 `KAC_SERVICE_KEY`(GitHub Actions에서는
    리포지토리 시크릿)로 주입한다.
    """

    def get_today(self, origin: str, dest: str, date: dt.date) -> list[FlightStatus]:
        cfg = _load_config()
        key = os.environ.get("KAC_SERVICE_KEY")
        if not key:
            raise DelayProviderError("환경변수 KAC_SERVICE_KEY 가 설정되지 않았습니다.")

        try:
            import requests
        except ImportError as e:
            raise DelayProviderError("requests 패키지가 필요합니다.") from e

        fields = cfg["response_fields"]
        params = {cfg["params"]["service_key"]: key, **cfg["params"].get("fixed", {})}
        params[cfg["params"]["departure_airport"]] = origin
        params[cfg["params"]["arrival_airport"]] = dest

        try:
            res = requests.get(cfg["endpoint"], params=params, timeout=20)
            res.raise_for_status()
            payload = res.json()
        except Exception as e:  # noqa: BLE001
            raise DelayProviderError(f"{origin}->{dest} 지연 정보 조회 실패: {e}") from e

        items = payload
        for step in cfg["items_path"]:
            items = items.get(step, {}) if isinstance(items, dict) else {}
        if isinstance(items, dict):
            items = [items]

        out: list[FlightStatus] = []
        for row in items or []:
            scheduled = _parse_time(row.get(fields["scheduled"]), date)
            estimated = _parse_time(row.get(fields["estimated"]), date)
            raw_state = str(row.get(fields["state"], "")).strip()
            delay = None
            if scheduled and estimated:
                delay = int((estimated - scheduled).total_seconds() // 60)

            out.append(FlightStatus(
                airline_code=str(row.get(fields["airline"], ""))[:2],
                flight_no=str(row.get(fields["flight_no"], "")),
                origin=origin,
                dest=dest,
                scheduled_dt=scheduled.isoformat() if scheduled else "",
                estimated_dt=estimated.isoformat() if estimated else None,
                state=_classify(raw_state, delay, cfg.get("state_keywords", {})),
                delay_minutes=delay,
                source="live",
            ))
        return out


def _parse_time(value: Any, date: dt.date) -> dt.datetime | None:
    """공공API는 보통 'HHMM' 또는 'YYYYMMDDHHMM' 형식을 쓴다."""
    if value is None:
        return None
    text = str(value).strip()
    if not text.isdigit():
        return None
    if len(text) == 4:
        return dt.datetime.combine(date, dt.time(int(text[:2]), int(text[2:])))
    if len(text) == 12:
        return dt.datetime.strptime(text, "%Y%m%d%H%M")
    return None


def _classify(raw: str, delay: int | None, keywords: dict[str, list[str]]) -> FlightState:
    for state, words in keywords.items():
        if any(w and w in raw for w in words):
            return state  # type: ignore[return-value]
    if delay is not None and delay >= DELAY_THRESHOLD_MIN:
        return "delayed"
    if delay is not None:
        return "ontime"
    return "unknown"
