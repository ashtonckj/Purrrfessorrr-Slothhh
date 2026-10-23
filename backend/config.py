"""Settings loader.

Reads KEY=VALUE pairs from config.env at the project root, then lets real
environment variables override them. No python-dotenv dependency needed.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_FILE = ROOT / "config.env"


def _read_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _as_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    host: str
    port: int
    open_browser: bool
    max_upload_mb: int
    upload_dir: Path
    cat_speed: float
    engine: str               # "local" (rules only) or "gemma" (rules + Gemma in Ollama)
    ollama_url: str
    ollama_model: str
    ollama_timeout: float     # seconds per Gemma request


def load_settings() -> Settings:
    raw = _read_env_file(CONFIG_FILE)

    def get(key: str, default: str) -> str:
        return os.environ.get(key, raw.get(key, default))

    upload_dir = Path(get("UPLOAD_DIR", "data/uploads"))
    if not upload_dir.is_absolute():
        upload_dir = ROOT / upload_dir

    return Settings(
        host=get("HOST", "127.0.0.1"),
        port=int(get("PORT", "8765")),
        open_browser=_as_bool(get("OPEN_BROWSER", "true")),
        max_upload_mb=int(get("MAX_UPLOAD_MB", "200")),
        upload_dir=upload_dir,
        cat_speed=max(0.05, float(get("CAT_SPEED", "1.0"))),
        engine=get("ENGINE", "local").strip().lower(),
        ollama_url=get("OLLAMA_URL", "http://127.0.0.1:11434"),
        ollama_model=get("OLLAMA_MODEL", "gemma3:1b"),
        ollama_timeout=max(1.0, float(get("OLLAMA_TIMEOUT", "45"))),
    )


settings = load_settings()
