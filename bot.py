from __future__ import annotations

import logging
from datetime import datetime
from io import BytesIO
from typing import Iterable

import httpx
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InputFile, Update
from telegram.constants import ChatAction
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

import db
from config import Config
from time_utils import parse_utc_datetime, resolve_display_timezone

logger = logging.getLogger(__name__)

TRANSCRIPTION_ERROR_MESSAGE = "❌ Не удалось обработать голосовое сообщение."
SUMMARY_ERROR_MESSAGE = "❌ Не удалось сгенерировать summary. Попробуйте позже."
UNSUPPORTED_MESSAGE = "Я принимаю только голосовые сообщения. Текст = поиск по записям."

MONTHS_RU = (
    "января",
    "февраля",
    "марта",
    "апреля",
    "мая",
    "июня",
    "июля",
    "августа",
    "сентября",
    "октября",
    "ноября",
    "декабря",
)


class VoiceInboxBot:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.display_timezone = resolve_display_timezone(config.display_timezone)
        self.active_topics: dict[int, int] = {}
        self.deepgram_client = httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=10.0))
        self.groq_client = httpx.AsyncClient(timeout=httpx.Timeout(15.0, connect=10.0))

    def build_application(self) -> Application:
        application = ApplicationBuilder().token(self.config.telegram_bot_token).build()
        application.add_handler(CommandHandler("start", self.start))
        application.add_handler(CommandHandler("help", self.help_command))
        application.add_handler(CommandHandler("topic", self.start_topic))
        application.add_handler(CallbackQueryHandler(self.handle_callback))
        application.add_handler(MessageHandler(filters.VOICE, self.handle_voice))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_search))
        application.add_handler(
            MessageHandler(filters.ALL & ~filters.TEXT & ~filters.COMMAND & ~filters.VOICE, self.handle_unsupported)
        )
        application.add_error_handler(self.handle_error)
        return application

    async def close(self) -> None:
        await self.deepgram_client.aclose()
        await self.groq_client.aclose()

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_private(update):
            return
        await update.effective_message.reply_text(
            "Привет. Отправьте голосовое сообщение, и я сохраню транскрипцию.\n"
            "Текстовые сообщения использую как поиск по записям.\n"
            "Команда /topic начинает пакет голосовых в одной теме."
        )

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_private(update):
            return
        await update.effective_message.reply_text(
            "/start — краткая инструкция\n"
            "/help — список команд\n"
            "/topic — начать тему для нескольких голосовых\n\n"
            "Голосовое: транскрипция + кнопки summary/текст/файл\n"
            "Текст: поиск по сохранённым записям"
        )

    async def start_topic(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_private(update):
            return

        user = update.effective_user
        if user is None:
            return

        existing_topic_id = self.active_topics.get(user.id)
        if existing_topic_id:
            await update.effective_message.reply_text(
                "📂 У вас уже есть активная тема. Завершите её текущей кнопкой.",
                reply_markup=self._topic_close_markup(),
            )
            return

        topic_id = db.create_topic()
        self.active_topics[user.id] = topic_id
        logger.info("Topic created: id=%s", topic_id)
        await update.effective_message.reply_text(
            "📂 Тема начата. Отправляйте голосовые — они будут объединены.",
            reply_markup=self._topic_close_markup(),
        )

    async def handle_voice(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_private(update):
            return

        message = update.effective_message
        voice = message.voice if message else None
        if message is None or voice is None:
            return

        try:
            logger.info("Voice received: duration=%ss, message_id=%s", voice.duration, message.message_id)
            await context.bot.send_chat_action(chat_id=message.chat_id, action=ChatAction.TYPING)
            telegram_file = await context.bot.get_file(voice.file_id)
            audio_bytes = await telegram_file.download_as_bytearray()
            logger.info("DeepGram request: %ss audio, %s bytes", voice.duration, len(audio_bytes))
            transcript, speech_detected = await self._transcribe_voice(bytes(audio_bytes))
            logger.info("DeepGram response: %s chars transcript", len(transcript))

            topic_id = self.active_topics.get(message.from_user.id) if message.from_user else None
            recording_id = db.save_recording(
                topic_id=topic_id,
                telegram_message_id=message.message_id,
                telegram_chat_id=message.chat_id,
                telegram_file_id=voice.file_id,
                duration=voice.duration,
                transcript=transcript,
                forward_from=self._extract_forward_from(message),
            )
            logger.info("Recording saved: id=%s, topic_id=%s", recording_id, topic_id)

            reply_text = f"✅ Сохранено ({format_duration(voice.duration)})"
            if not speech_detected:
                reply_text += "\n⚠️ Речь не распознана."
            await message.reply_text(reply_text, reply_markup=self._recording_actions_markup(recording_id))
        except httpx.HTTPStatusError as exc:
            logger.error("DeepGram error: %s", exc, exc_info=True)
            status_code = exc.response.status_code
            if status_code == 401:
                await message.reply_text("❌ Ошибка транскрипции. Проверьте DEEPGRAM_API_KEY в логах.")
            elif status_code == 429:
                await message.reply_text("⏳ Сервис транскрипции перегружен. Попробуйте через минуту.")
            else:
                await message.reply_text(TRANSCRIPTION_ERROR_MESSAGE)
        except (httpx.TimeoutException, httpx.NetworkError):
            logger.error("DeepGram network error", exc_info=True)
            await message.reply_text("❌ Не удалось связаться с сервисом транскрипции.")
        except Exception:
            logger.error("Unexpected voice handler error", exc_info=True)
            await message.reply_text(TRANSCRIPTION_ERROR_MESSAGE)

    async def handle_search(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_private(update):
            return

        message = update.effective_message
        if message is None:
            return

        query = (message.text or "").strip()
        if not query:
            return

        try:
            rows = db.search_recordings(query, limit=10)
            logger.info('Search: query="%s", found=%s', query, len(rows))
            if not rows:
                await message.reply_text(f"🔍 Ничего не найдено по запросу «{query}»")
                return

            base_url = self.config.web_base_url
            lines = [f'🔍 Найдено {len(rows)} записей по "{query}":', ""]
            for index, row in enumerate(rows, start=1):
                created_at = parse_utc_datetime(row["created_at"], self.display_timezone)
                lines.append(f"{index}. {format_short_datetime(created_at)} ({format_duration(int(row['duration']))})")
                lines.append(f'   "{build_snippet(row["transcript"], query)}"')
                if base_url:
                    lines.append(f"   → {base_url}/r/{row['id']}")
                lines.append("")
            await message.reply_text("\n".join(lines).strip())
        except Exception:
            logger.error("Search handler error", exc_info=True)
            await message.reply_text("❌ Ошибка поиска. Попробуйте ещё раз.")

    async def handle_unsupported(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_private(update):
            return
        if update.effective_message:
            await update.effective_message.reply_text(UNSUPPORTED_MESSAGE)

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        if query is None or query.message is None:
            return

        await query.answer()

        try:
            if query.data == "topic:close":
                await self._close_active_topic(update)
                return

            action, entity_type, entity_id_text = (query.data or "").split(":", 2)
            entity_id = int(entity_id_text)
        except (ValueError, AttributeError):
            await query.message.reply_text("❌ Не удалось обработать действие.")
            return

        try:
            if entity_type == "recording":
                await self._handle_recording_action(action, entity_id, query)
            elif entity_type == "topic":
                await self._handle_topic_action(action, entity_id, query)
            else:
                await query.message.reply_text("❌ Неизвестное действие.")
        except Exception:
            logger.error("Callback handler error", exc_info=True)
            await query.message.reply_text("❌ Ошибка выполнения действия.")

    async def handle_error(self, update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        error = context.error
        exc_info = None
        if error is not None:
            exc_info = (type(error), error, error.__traceback__)
        logger.error("Unhandled telegram error: %s", error, exc_info=exc_info)

        maybe_update = update if isinstance(update, Update) else None
        if maybe_update and maybe_update.effective_message:
            try:
                await maybe_update.effective_message.reply_text("❌ Внутренняя ошибка. Попробуйте позже.")
            except Exception:
                logger.error("Failed to send error notification", exc_info=True)

    async def _close_active_topic(self, update: Update) -> None:
        query = update.callback_query
        user = update.effective_user
        if query is None or query.message is None or user is None:
            return

        topic_id = self.active_topics.pop(user.id, None)
        if topic_id is None:
            await query.message.reply_text("📂 Активной темы нет.")
            return

        db.close_topic(topic_id)
        stats = db.get_topic_stats(topic_id)
        logger.info("Topic closed: id=%s, %s recordings", topic_id, stats["recording_count"])

        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except Exception:
            logger.debug("Could not clear topic close button", exc_info=True)

        await query.message.reply_text(
            f"📂 Тема закрыта. {stats['recording_count']} голосовых, общая длительность "
            f"{format_duration(stats['total_duration'])}",
            reply_markup=self._topic_actions_markup(topic_id),
        )

    async def _handle_recording_action(self, action: str, recording_id: int, query) -> None:
        row = db.get_recording(recording_id)
        if row is None:
            await query.message.reply_text("❌ Запись не найдена.")
            return

        if action == "summary":
            summary_row = db.get_latest_summary_for_recording(recording_id)
            if summary_row:
                await query.message.reply_text(f"📝 Summary:\n\n{summary_row['summary']}")
                return

            summary_text = await self._generate_summary(row["transcript"], is_topic=False)
            if summary_text is None:
                await query.message.reply_text(SUMMARY_ERROR_MESSAGE)
                return
            db.save_summary(recording_id=recording_id, text=summary_text)
            logger.info("Groq response: %s chars summary", len(summary_text))
            await query.message.reply_text(f"📝 Summary:\n\n{summary_text}")
            return

        if action == "text":
            await self._send_long_text(query.message, row["transcript"])
            return

        if action == "file":
            await self._send_text_file(
                query.message,
                filename=f"recording-{recording_id}.txt",
                content=row["transcript"],
            )
            return

        await query.message.reply_text("❌ Неизвестное действие.")

    async def _handle_topic_action(self, action: str, topic_id: int, query) -> None:
        topic, recordings = db.get_topic_with_recordings(topic_id)
        if topic is None:
            await query.message.reply_text("❌ Тема не найдена.")
            return

        combined_text = build_topic_text(recordings, self.display_timezone)

        if action == "summary":
            summary_row = db.get_latest_summary_for_topic(topic_id)
            if summary_row:
                await query.message.reply_text(f"📝 Summary темы:\n\n{summary_row['summary']}")
                return

            summary_text = await self._generate_summary(combined_text, is_topic=True)
            if summary_text is None:
                await query.message.reply_text(SUMMARY_ERROR_MESSAGE)
                return
            db.save_summary(topic_id=topic_id, text=summary_text)
            logger.info("Groq response: %s chars summary", len(summary_text))
            await query.message.reply_text(f"📝 Summary темы:\n\n{summary_text}")
            return

        if action == "text":
            await self._send_long_text(query.message, combined_text)
            return

        if action == "file":
            await self._send_text_file(
                query.message,
                filename=f"topic-{topic_id}.txt",
                content=combined_text,
            )
            return

        await query.message.reply_text("❌ Неизвестное действие.")

    async def _transcribe_voice(self, audio_bytes: bytes) -> tuple[str, bool]:
        response = await self.deepgram_client.post(
            "https://api.deepgram.com/v1/listen?model=nova-2&language=ru",
            headers={
                "Authorization": f"Token {self.config.deepgram_api_key}",
                "Content-Type": "audio/ogg",
            },
            content=audio_bytes,
        )
        response.raise_for_status()
        payload = response.json()
        transcript = (
            payload.get("results", {})
            .get("channels", [{}])[0]
            .get("alternatives", [{}])[0]
            .get("transcript", "")
            .strip()
        )
        if not transcript:
            return "(нет речи)", False
        return transcript, True

    async def _generate_summary(self, transcript: str, *, is_topic: bool) -> str | None:
        if not self.config.groq_api_key:
            logger.warning("GROQ_API_KEY не задан, summary отключены")
            return None

        system_prompt = (
            "Сделай краткий пересказ темы на русском языке. 2-3 предложения, только суть."
            if is_topic
            else "Сделай краткий пересказ голосовой заметки на русском языке. 2-3 предложения, только суть."
        )
        logger.info("Groq request: %s chars input", len(transcript))

        try:
            response = await self.groq_client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.config.groq_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "llama-3.3-70b-versatile",
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": transcript},
                    ],
                    "temperature": 0.3,
                    "max_tokens": 500,
                },
            )
            response.raise_for_status()
            payload = response.json()
            return (
                payload.get("choices", [{}])[0]
                .get("message", {})
                .get("content", "")
                .strip()
            )
        except Exception as exc:
            logger.error("Groq error: %s", exc, exc_info=True)
            return None

    async def _send_long_text(self, message, text: str) -> None:
        for chunk in split_message(text):
            await message.reply_text(chunk)

    async def _send_text_file(self, message, filename: str, content: str) -> None:
        buffer = BytesIO(content.encode("utf-8"))
        buffer.name = filename
        await message.reply_document(document=InputFile(buffer))

    def _recording_actions_markup(self, recording_id: int) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("📝 Summary", callback_data=f"summary:recording:{recording_id}"),
                    InlineKeyboardButton("📄 Текстом", callback_data=f"text:recording:{recording_id}"),
                    InlineKeyboardButton("📁 Файлом", callback_data=f"file:recording:{recording_id}"),
                ]
            ]
        )

    def _topic_actions_markup(self, topic_id: int) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("📝 Summary темы", callback_data=f"summary:topic:{topic_id}"),
                    InlineKeyboardButton("📄 Вся тема текстом", callback_data=f"text:topic:{topic_id}"),
                    InlineKeyboardButton("📁 Файлом", callback_data=f"file:topic:{topic_id}"),
                ]
            ]
        )

    def _topic_close_markup(self) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            [[InlineKeyboardButton("✅ Завершить тему", callback_data="topic:close")]]
        )

    def _is_private(self, update: Update) -> bool:
        chat = update.effective_chat
        return bool(chat and chat.type == "private")

    def _extract_forward_from(self, message) -> str | None:
        origin = getattr(message, "forward_origin", None)
        if origin is not None:
            sender_user = getattr(origin, "sender_user", None)
            if sender_user is not None:
                return sender_user.full_name

            sender_chat = getattr(origin, "sender_chat", None)
            if sender_chat is not None:
                signature = getattr(origin, "author_signature", None)
                return signature or sender_chat.title

            sender_user_name = getattr(origin, "sender_user_name", None)
            if sender_user_name:
                return sender_user_name

        forward_from = getattr(message, "forward_from", None)
        if forward_from is not None:
            return forward_from.full_name

        forward_sender_name = getattr(message, "forward_sender_name", None)
        if forward_sender_name:
            return forward_sender_name
        return None


def build_topic_text(recordings: Iterable, display_timezone) -> str:
    blocks = []
    for index, row in enumerate(recordings, start=1):
        created_at = parse_utc_datetime(row["created_at"], display_timezone)
        blocks.append(
            f"Запись {index} ({created_at.strftime('%d.%m %H:%M')}, {format_duration(int(row['duration']))})\n"
            f"{row['transcript']}"
        )
    return "\n\n".join(blocks) if blocks else "(пустая тема)"


def split_message(text: str, limit: int = 4096) -> list[str]:
    if len(text) <= limit:
        return [text]

    chunks: list[str] = []
    remaining = text
    while remaining:
        if len(remaining) <= limit:
            chunks.append(remaining)
            break

        split_at = remaining.rfind("\n", 0, limit)
        if split_at <= 0:
            split_at = limit
        chunks.append(remaining[:split_at].strip())
        remaining = remaining[split_at:].strip()
    return chunks


def build_snippet(text: str, query: str, radius: int = 50) -> str:
    lowered_text = text.casefold()
    lowered_query = query.casefold()
    index = lowered_text.find(lowered_query)
    if index == -1:
        snippet = text[: radius * 2].strip()
        return f"{snippet}..." if len(text) > len(snippet) else snippet

    start = max(0, index - radius)
    end = min(len(text), index + len(query) + radius)
    snippet = text[start:end].strip()
    if start > 0:
        snippet = f"...{snippet}"
    if end < len(text):
        snippet = f"{snippet}..."
    return snippet


def format_duration(total_seconds: int) -> str:
    minutes, seconds = divmod(max(total_seconds, 0), 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"


def format_short_datetime(value: datetime) -> str:
    return f"{value.day} {MONTHS_RU[value.month - 1]}, {value.strftime('%H:%M')}"
