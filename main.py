from __future__ import annotations

import asyncio
import logging
import sys
import threading

from waitress import serve

import db
from bot import VoiceInboxBot
from config import ConfigError, load_config
from web import create_app

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("voice-inbox")


def run_web_server(app, port: int) -> None:
    serve(app, host="0.0.0.0", port=port)


def main() -> None:
    try:
        config = load_config()
    except ConfigError as exc:
        missing_names = {name.strip() for name in str(exc).split(",")}
        if "TELEGRAM_BOT_TOKEN" in missing_names:
            sys.exit("TELEGRAM_BOT_TOKEN не задан в .env")
        if "DEEPGRAM_API_KEY" in missing_names:
            sys.exit("DEEPGRAM_API_KEY не задан в .env")
        if "WEB_PASSWORD" in missing_names:
            sys.exit("WEB_PASSWORD не задан в .env")
        sys.exit(str(exc))

    if not config.groq_api_key:
        logger.warning("GROQ_API_KEY не задан, summary отключены")

    db.set_database_path(config.database_path)
    db.init_db()
    closed_topics = db.close_open_topics()
    if closed_topics:
        logger.info("Closed %s unfinished topics on startup", closed_topics)

    app = create_app(config)
    web_thread = threading.Thread(target=run_web_server, args=(app, config.web_port), daemon=True)
    web_thread.start()

    bot_service = VoiceInboxBot(config)
    application = bot_service.build_application()

    logger.info("Bot started, web panel on port %s", config.web_port)
    try:
        application.run_polling()
    finally:
        asyncio.run(bot_service.close())


if __name__ == "__main__":
    main()
