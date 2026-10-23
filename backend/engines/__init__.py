"""Engine selection. Swap in another `Engine` here (e.g. pandas + Ollama) later."""

from __future__ import annotations

from ..config import settings
from .base import Engine


def get_engine() -> Engine:
    from .local import LocalEngine

    return LocalEngine(speed=settings.cat_speed)
