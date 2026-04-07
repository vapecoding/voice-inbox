from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone, tzinfo
from functools import lru_cache

try:
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
except ImportError:  # pragma: no cover
    ZoneInfo = None
    ZoneInfoNotFoundError = Exception


DEFAULT_DISPLAY_TIMEZONE = "UTC+05:00"
TIMEZONE_OFFSET_RE = re.compile(r"^(?:UTC)?\s*([+-])\s*(\d{1,2})(?::?(\d{2}))?$", re.IGNORECASE)


def _build_fixed_offset(sign: str, hours_text: str, minutes_text: str | None) -> timezone:
    hours = int(hours_text)
    minutes = int(minutes_text or "0")
    if hours > 23 or minutes > 59:
        raise ValueError("смещение должно быть в диапазоне UTC-23:59..UTC+23:59")

    delta = timedelta(hours=hours, minutes=minutes)
    if sign == "-":
        delta = -delta
    return timezone(delta)


def _format_offset_label(offset: timedelta) -> str:
    total_minutes = int(offset.total_seconds() // 60)
    sign = "+" if total_minutes >= 0 else "-"
    absolute_minutes = abs(total_minutes)
    hours, minutes = divmod(absolute_minutes, 60)
    return f"UTC{sign}{hours:02d}:{minutes:02d}"


@lru_cache(maxsize=None)
def resolve_display_timezone(value: str | None) -> tzinfo:
    spec = (value or DEFAULT_DISPLAY_TIMEZONE).strip()
    offset_match = TIMEZONE_OFFSET_RE.fullmatch(spec)
    if offset_match:
        return _build_fixed_offset(*offset_match.groups())

    if ZoneInfo is not None:
        try:
            return ZoneInfo(spec)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("неизвестный часовой пояс") from exc

    raise ValueError("не удалось определить часовой пояс")


def normalize_timezone_label(value: str | None) -> str:
    timezone_info = resolve_display_timezone(value)
    timezone_key = getattr(timezone_info, "key", None)
    if timezone_key:
        return timezone_key

    offset = timezone_info.utcoffset(None)
    return _format_offset_label(offset or timedelta())


def parse_utc_datetime(value: str, display_timezone: tzinfo) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    else:
        parsed = parsed.astimezone(timezone.utc)
    return parsed.astimezone(display_timezone)
