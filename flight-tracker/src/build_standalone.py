"""대시보드를 단일 HTML 파일로 묶는다.

dashboard/index.html 은 데이터를 fetch로 읽기 때문에, 파일을 그냥 더블클릭해서
열면(file:// 스킴) 브라우저 보안정책에 막혀 아무것도 표시되지 않는다. 이 스크립트는
데이터 JSON과 항공사 로고를 HTML 안에 넣어, 서버 없이 열리는 파일 하나를 만든다.

내장된 데이터는 만든 시점에 고정된 저장본이므로, 화면의 갱신 표시도
"10분마다 자동 갱신"이 아니라 "저장본 · 언제 기준"으로 바뀐다 — 멈춰 있는 값을
실시간인 것처럼 보이게 하지 않기 위해서다.

사용법:
    python src/build_standalone.py
    # -> dist/갈매기의-귀향-플래너.html
"""

from __future__ import annotations

import base64
import datetime as dt
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "dashboard" / "index.html"
ASSETS = ROOT / "dashboard" / "assets"
DATA = ROOT / "data"
OUT = ROOT / "dist" / "갈매기의-귀향-플래너.html"


def _data_uri(path: Path) -> str:
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/svg+xml;base64,{encoded}"


def build() -> Path:
    html = SOURCE.read_text(encoding="utf-8")

    snapshot = {
        "generated_at": dt.datetime.now().isoformat(),
        "results": json.loads((DATA / "results.json").read_text(encoding="utf-8")),
        "weather": json.loads((DATA / "weather.json").read_text(encoding="utf-8")),
        "delays": json.loads((DATA / "delays.json").read_text(encoding="utf-8")),
        "insights": json.loads((DATA / "insights.json").read_text(encoding="utf-8")),
    }
    # </script> 가 문자열 안에 들어가면 스크립트 태그가 조기에 닫히므로 이스케이프한다.
    payload = json.dumps(snapshot, ensure_ascii=False).replace("</", "<\\/")

    html = html.replace(
        "<script>\nconst DATA_BASE",
        f"<script>\nwindow.__SNAPSHOT__ = {payload};\n</script>\n<script>\nconst DATA_BASE",
        1,
    )

    for name in ("ke", "oz"):
        html = html.replace(f"assets/{name}.svg", _data_uri(ASSETS / f"{name}.svg"))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(html, encoding="utf-8")
    return OUT


def main() -> None:
    out = build()
    size_kb = out.stat().st_size / 1024
    print(f"[build_standalone] {out} ({size_kb:,.0f} KB)")
    print("  브라우저로 바로 열 수 있습니다 (서버 불필요).")


if __name__ == "__main__":
    main()
