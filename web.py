from __future__ import annotations

import logging
import secrets
from datetime import datetime
from typing import Any

from flask import Flask, make_response, redirect, render_template, request, url_for

import db
from config import Config
from time_utils import normalize_timezone_label, parse_utc_datetime, resolve_display_timezone

logger = logging.getLogger(__name__)

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


def create_app(config: Config) -> Flask:
    app = Flask(__name__)
    session_tokens: set[str] = set()
    display_timezone = resolve_display_timezone(config.display_timezone)
    display_timezone_label = normalize_timezone_label(config.display_timezone)

    def parse_db_datetime(value: str) -> datetime:
        return parse_utc_datetime(value, display_timezone)

    @app.before_request
    def require_login():
        if request.endpoint in {"login", "robots_txt", "static"}:
            return None

        token = request.cookies.get("session_token")
        if token in session_tokens:
            return None
        return redirect(url_for("login"))

    @app.after_request
    def add_headers(response):
        response.headers["X-Robots-Tag"] = "noindex, nofollow"
        return response

    @app.context_processor
    def inject_template_globals() -> dict[str, str]:
        return {"display_timezone_label": display_timezone_label}

    @app.template_filter("duration")
    def duration_filter(value: int) -> str:
        return format_duration(int(value or 0))

    @app.template_filter("day_label")
    def day_label_filter(value: str) -> str:
        return format_day_label(parse_db_datetime(value))

    @app.template_filter("time_label")
    def time_label_filter(value: str) -> str:
        return parse_db_datetime(value).strftime("%H:%M")

    @app.template_filter("datetime_label")
    def datetime_label_filter(value: str) -> str:
        return format_datetime_label(parse_db_datetime(value))

    @app.template_filter("excerpt")
    def excerpt_filter(value: str, limit: int = 180) -> str:
        if len(value) <= limit:
            return value
        return f"{value[:limit].rstrip()}..."

    @app.get("/")
    def index():
        page = parse_page(request.args.get("page", "1"))
        items, total = db.get_feed_items(page=page, per_page=20)
        grouped_items = group_feed_items(items, parse_db_datetime)
        archive_stats = db.get_archive_stats()
        total_pages = max((total - 1) // 20 + 1, 1) if total else 1
        return render_template(
            "index.html",
            grouped_items=grouped_items,
            archive_stats=archive_stats,
            page=page,
            total_pages=total_pages,
            has_prev=page > 1,
            has_next=page < total_pages,
        )

    @app.route("/login", methods=["GET", "POST"])
    def login():
        error = None
        if request.method == "POST":
            password = (request.form.get("password") or "").strip()
            if password == config.web_password:
                logger.info("Web login: success")
                token = secrets.token_urlsafe(32)
                session_tokens.add(token)
                response = make_response(redirect(url_for("index")))
                response.set_cookie(
                    "session_token",
                    token,
                    httponly=True,
                    samesite="Lax",
                    max_age=60 * 60 * 24 * 30,
                )
                return response
            logger.info("Web login: wrong password")
            error = "Неверный пароль"
        return render_template("login.html", error=error)

    @app.post("/logout")
    def logout():
        token = request.cookies.get("session_token")
        if token:
            session_tokens.discard(token)
        response = make_response(redirect(url_for("login")))
        response.delete_cookie("session_token")
        return response

    @app.get("/r/<int:recording_id>")
    def recording_detail(recording_id: int):
        row = db.get_recording(recording_id)
        if row is None:
            return "Запись не найдена", 404

        summaries = db.get_summaries_for_recording(recording_id)
        return render_template(
            "recording.html",
            entity_type="recording",
            recording=row,
            summaries=summaries,
        )

    @app.get("/r/topic/<int:topic_id>")
    def topic_detail(topic_id: int):
        topic, recordings = db.get_topic_with_recordings(topic_id)
        if topic is None:
            return "Запись не найдена", 404

        summaries = db.get_summaries_for_topic(topic_id)
        total_duration = sum(int(row["duration"]) for row in recordings)
        return render_template(
            "recording.html",
            entity_type="topic",
            topic=topic,
            recordings=recordings,
            total_duration=total_duration,
            summaries=summaries,
        )

    @app.post("/delete/<int:recording_id>")
    def delete_recording(recording_id: int):
        db.delete_recording(recording_id)
        logger.info("Web delete: recording id=%s", recording_id)
        return redirect(url_for("index"))

    @app.post("/delete-topic/<int:topic_id>")
    def delete_topic(topic_id: int):
        db.delete_topic(topic_id)
        logger.info("Web delete: topic id=%s", topic_id)
        return redirect(url_for("index"))

    @app.get("/robots.txt")
    def robots_txt():
        response = make_response("User-agent: *\nDisallow: /\n")
        response.mimetype = "text/plain"
        return response

    @app.errorhandler(500)
    def server_error(error):
        logger.error("Web internal error", exc_info=error)
        return "Внутренняя ошибка", 500

    return app


def parse_page(value: str) -> int:
    try:
        page = int(value)
    except (TypeError, ValueError):
        return 1
    return max(page, 1)


def group_feed_items(items: list[dict[str, Any]], parse_datetime) -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    for item in items:
        created_at = parse_datetime(item["created_at"])
        day_key = created_at.strftime("%Y-%m-%d")
        if not groups or groups[-1]["day_key"] != day_key:
            groups.append(
                {
                    "day_key": day_key,
                    "day_label": format_day_label(created_at),
                    "items": [],
                }
            )
        groups[-1]["items"].append(item)
    return groups


def format_day_label(value: datetime) -> str:
    return f"{value.day} {MONTHS_RU[value.month - 1]} {value.year}"


def format_datetime_label(value: datetime) -> str:
    return f"{value.day} {MONTHS_RU[value.month - 1]} {value.year}, {value.strftime('%H:%M')}"


def format_duration(total_seconds: int) -> str:
    minutes, seconds = divmod(max(total_seconds, 0), 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"
