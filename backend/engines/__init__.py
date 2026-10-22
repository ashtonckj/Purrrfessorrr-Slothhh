"""Engine selection: mock today, real (pandas + Ollama) later."""

from __future__ import annotations

from ..config import settings
from .base import Engine


def get_engine() -> Engine:
    if settings.mock_mode:
        from .mock import MockEngine

        return MockEngine(speed=settings.mock_speed, error_rate=settings.mock_error_rate)
    raise RuntimeError(
        "MOCK_MODE=false but the real engine is not built yet. "
        "Set MOCK_MODE=true in config.env."
    )
