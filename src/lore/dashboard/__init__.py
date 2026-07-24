from __future__ import annotations

import base64
from pathlib import Path

_FAVICON_PATH = Path(__file__).parent / "static" / "favicon.png"


def _favicon_data_url() -> str:
    data = _FAVICON_PATH.read_bytes()
    b64 = base64.b64encode(data).decode("ascii")
    return f"data:image/png;base64,{b64}"


def launch(host: str = "127.0.0.1", port: int = 8765) -> None:
    from lore.dashboard.app import create_app

    create_app()

    from nicegui import ui

    ui.run(
        host=host,
        port=port,
        title="Lore Dashboard",
        favicon=_favicon_data_url(),
        reload=False,
    )
