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
    mock_mode: bool
    host: str
    port: int
    open_browser: bool
    max_upload_mb: int
    upload_dir: Path
    ollama_url: str
    model_name: str
    mock_speed: float
    mock_error_rate: float


def load_settings() -> Settings:
    raw = _read_env_file(CONFIG_FILE)

    def get(key: str, default: str) -> str:
        return os.environ.get(key, raw.get(key, default))

    upload_dir = Path(get("UPLOAD_DIR", "data/uploads"))
    if not upload_dir.is_absolute():
        upload_dir = ROOT / upload_dir

    return Settings(
        mock_mode=_as_bool(get("MOCK_MODE", "true")),
        host=get("HOST", "127.0.0.1"),
        port=int(get("PORT", "8765")),
        open_browser=_as_bool(get("OPEN_BROWSER", "true")),
        max_upload_mb=int(get("MAX_UPLOAD_MB", "200")),
        upload_dir=upload_dir,
        ollama_url=get("OLLAMA_URL", "http://127.0.0.1:11434"),
        model_name=get("MODEL_NAME", "gemma3:4b"),
        mock_speed=max(0.05, float(get("MOCK_SPEED", "1.0"))),
        mock_error_rate=min(1.0, max(0.0, float(get("MOCK_ERROR_RATE", "0.0")))),
    )


settings = load_settings()
