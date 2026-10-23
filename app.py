"""Purrfessorrr Slothhh: start with `python app.py`.

Serves the API under /api and the static frontend at /.
Flags: --port 9000, --no-browser
"""

from __future__ import annotations

import argparse
import threading
import webbrowser
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from backend.api import router
from backend.config import settings

STATIC_DIR = Path(__file__).resolve().parent / "static"


class FreshStaticFiles(StaticFiles):
    """Static files that the browser re-checks on every load (cheap 304s),
    so edited JS/CSS and swapped-in sprites show up without a hard refresh."""

    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-cache"
        return response


app = FastAPI(title="Purrfessorrr Slothhh", docs_url="/api/docs", redoc_url=None)
app.include_router(router)
# Mounted last so /api routes win; html=True serves index.html at "/".
app.mount("/", FreshStaticFiles(directory=STATIC_DIR, html=True), name="static")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Purrfessorrr Slothhh locally.")
    parser.add_argument("--port", type=int, default=settings.port)
    parser.add_argument("--no-browser", action="store_true", help="don't open a browser tab")
    args = parser.parse_args()

    url = f"http://{settings.host}:{args.port}/"
    print(f"\n  Purrfessorrr Slothhh is waking up... slowly...\n  -> {url}\n")

    if settings.open_browser and not args.no_browser:
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()

    uvicorn.run(app, host=settings.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
