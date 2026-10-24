"""Engine selection: ENGINE=local (rules only) or ENGINE=gemma (rules + Gemma in Ollama) in config.env."""

from __future__ import annotations

import threading

from ..config import settings
from .base import Engine


def get_engine() -> Engine:
    from .local import LocalEngine

    if settings.engine == "gemma":
        from .gemma import GemmaEngine, Ollama

        try:
            llm = Ollama(settings.ollama_url, settings.ollama_model, settings.ollama_timeout)
        except ValueError as exc:
            print(f"  gemma is off: {exc}. Using the local engine.")
        else:
            threading.Thread(target=llm.warm, daemon=True).start()   # load the model without delaying start-up
            return GemmaEngine(settings.cat_speed, llm)
    elif settings.engine != "local":
        print(f"  unknown ENGINE={settings.engine!r} (use local or gemma). Using the local engine.")
    return LocalEngine(speed=settings.cat_speed)
