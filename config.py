from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from time_utils import DEFAULT_DISPLAY_TIMEZONE, resolve_display_timezone


class ConfigError(RuntimeError):
    pass


@dataclass(slots=True)
class Config:
    telegram_bot_token: str
    deepgram_api_key: str
    groq_api_key: str | None
    web_password: str
    web_port: int
    database_path: Path
    public_base_url: str | None
    server_host: str | None
    display_timezone: str

    @property
    def web_base_url(self) -> str | None:
        if self.public_base_url:
            return self.public_base_url.rstrip("/")
        if self.server_host:
            return f"http://{self.server_host}:{self.web_port}"
        return None


def load_config(env_path: str | Path | None = None) -> Config:
    load_dotenv(dotenv_path=env_path, override=False)

    telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    deepgram_api_key = os.getenv("DEEPGRAM_API_KEY", "").strip()
    groq_api_key = os.getenv("GROQ_API_KEY", "").strip() or None
    web_password = os.getenv("WEB_PASSWORD", "").strip()
    web_port = int(os.getenv("WEB_PORT", "8080"))
    database_path = Path(os.getenv("DATABASE_PATH", "voice_inbox.db"))
    public_base_url = os.getenv("PUBLIC_BASE_URL", "").strip() or None
    server_host = os.getenv("SERVER_HOST", "").strip() or None
    display_timezone = os.getenv("DISPLAY_TIMEZONE", DEFAULT_DISPLAY_TIMEZONE).strip() or DEFAULT_DISPLAY_TIMEZONE

    missing = []
    if not telegram_bot_token:
        missing.append("TELEGRAM_BOT_TOKEN")
    if not deepgram_api_key:
        missing.append("DEEPGRAM_API_KEY")
    if not web_password:
        missing.append("WEB_PASSWORD")

    if missing:
        raise ConfigError(", ".join(missing))

    try:
        resolve_display_timezone(display_timezone)
    except ValueError as exc:
        raise ConfigError(f"DISPLAY_TIMEZONE: {exc}") from exc

    return Config(
        telegram_bot_token=telegram_bot_token,
        deepgram_api_key=deepgram_api_key,
        groq_api_key=groq_api_key,
        web_password=web_password,
        web_port=web_port,
        database_path=database_path,
        public_base_url=public_base_url,
        server_host=server_host,
        display_timezone=display_timezone,
    )
