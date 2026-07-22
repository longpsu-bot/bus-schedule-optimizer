from __future__ import annotations

import re
from collections.abc import Iterable
from datetime import datetime, time
from numbers import Real

import pandas as pd


def parse_runtime_options(value: object) -> tuple[int, ...]:
    """Parse inclusive runtime bounds such as ``55,65``.

    The smallest and largest positive integers define an inclusive range, so
    ``55,65`` accepts every integer from 55 through 65. A numeric value such as
    ``55.65`` is treated as the pair ``55,65`` only to recover from Excel
    locales that use a comma as the decimal separator.
    """
    if value is None or (
        isinstance(value, Real) and not isinstance(value, bool) and pd.isna(value)
    ):
        raise ValueError("Khoảng thời gian hành trình bị trống")
    if isinstance(value, str):
        normalized = re.sub(r"(?<=\d)[–-](?=\d)", ",", value.strip())
        raw_values: Iterable[object] = [item for item in re.split(r"[,;|/\s]+", normalized) if item]
    elif isinstance(value, Real) and not isinstance(value, bool):
        numeric_text = str(value)
        excel_pair = re.fullmatch(r"([1-9]\d+)\.([1-9]\d+)", numeric_text)
        raw_values = list(excel_pair.groups()) if excel_pair else [value]
    elif isinstance(value, Iterable):
        raw_values = value
    else:
        raw_values = [value]

    parsed: list[int] = []
    for raw in raw_values:
        try:
            numeric = float(raw)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Thời gian hành trình không hợp lệ: {raw}") from exc
        if not numeric.is_integer() or numeric <= 0:
            raise ValueError(f"Thời gian hành trình phải là số nguyên dương: {raw}")
        parsed.append(int(numeric))
    if not parsed:
        raise ValueError("Phải khai báo ít nhất một thời gian hành trình hợp lệ")
    bounds = sorted(set(parsed))
    return (bounds[0],) if len(bounds) == 1 else (bounds[0], bounds[-1])


def parse_time_to_seconds(value: object) -> int:
    """Parse Excel time, datetime/time, or HH:mm[:ss] into service-day seconds."""
    if value is None or (not isinstance(value, str) and pd.isna(value)):
        raise ValueError("Giá trị thời gian bị trống")
    if isinstance(value, datetime):
        return value.hour * 3600 + value.minute * 60 + value.second
    if isinstance(value, time):
        return value.hour * 3600 + value.minute * 60 + value.second
    if isinstance(value, Real) and not isinstance(value, bool):
        numeric = float(value)
        fraction = numeric % 1
        return int(round(fraction * 86400))
    text = str(value).strip()
    if text in {"24:00", "24:00:00"}:
        return 86400
    for pattern in ("%H:%M:%S", "%H:%M"):
        try:
            parsed = datetime.strptime(text, pattern)
            return parsed.hour * 3600 + parsed.minute * 60 + parsed.second
        except ValueError:
            continue
    try:
        parsed = pd.to_datetime(text)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Giờ không đúng định dạng: {value}") from exc
    return parsed.hour * 3600 + parsed.minute * 60 + parsed.second


def format_hhmm(seconds: int | float | None, include_seconds: bool = False) -> str:
    if seconds is None:
        return ""
    rounded = int(round(seconds))
    hours, remainder = divmod(rounded, 3600)
    minutes, secs = divmod(remainder, 60)
    if include_seconds and secs:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{hours:02d}:{minutes:02d}"


def block_label(start_seconds: int, end_seconds: int) -> str:
    return f"{format_hhmm(start_seconds)}–{format_hhmm(end_seconds)}"


def excel_time_fraction(seconds: int) -> float:
    return seconds / 86400
