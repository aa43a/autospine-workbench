"""Bounded duplicate-safe JSON request decoding for local HTTP routes."""

from __future__ import annotations

from dataclasses import dataclass
from http import HTTPStatus
import json
import math
import time
from typing import Any


MAX_REQUEST_BODY = 1024 * 1024
REJECTED_BODY_DRAIN_SECONDS = 0.25
_DRAIN_CHUNK_BYTES = 64 * 1024


@dataclass(frozen=True, slots=True)
class HttpJsonRequestError(ValueError):
    """Stable public failure for one malformed JSON request."""

    status: int
    code: str
    public_message: str

    def __str__(self) -> str:
        return self.public_message


def read_json_object_request(
    handler: Any,
    *,
    maximum_bytes: int = MAX_REQUEST_BODY,
) -> dict[str, Any]:
    """Read exactly one bounded application/json object from a handler."""

    content_types = handler.headers.get_all("Content-Type", []) or []
    content_type = content_types[0] if len(content_types) == 1 else ""
    content_type = content_type.split(";", 1)[0].strip().lower()
    if content_type != "application/json":
        raise HttpJsonRequestError(
            HTTPStatus.UNSUPPORTED_MEDIA_TYPE,
            "unsupported_media_type",
            "Content-Type must be application/json.",
        )
    if handler.headers.get_all("Transfer-Encoding", []):
        raise HttpJsonRequestError(
            HTTPStatus.BAD_REQUEST,
            "unsupported_transfer_encoding",
            "Transfer-Encoding is not supported.",
        )
    raw_lengths = handler.headers.get_all("Content-Length", []) or []
    raw_length = raw_lengths[0] if len(raw_lengths) == 1 else ""
    content_length = int(raw_length) if _decimal_length(raw_length) else -1
    if content_length < 0:
        raise HttpJsonRequestError(
            HTTPStatus.LENGTH_REQUIRED,
            "length_required",
            "A valid Content-Length header is required.",
        )
    if content_length > maximum_bytes:
        raise HttpJsonRequestError(
            HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
            "request_too_large",
            f"Request bodies are limited to {maximum_bytes} bytes.",
        )
    raw = handler.rfile.read(content_length)
    if len(raw) != content_length:
        raise HttpJsonRequestError(
            HTTPStatus.BAD_REQUEST,
            "short_body",
            "Request body was incomplete.",
        )
    return decode_json_object(raw)


def drain_bounded_request_body(
    handler: Any,
    *,
    maximum_bytes: int = MAX_REQUEST_BODY,
    maximum_seconds: float = REJECTED_BODY_DRAIN_SECONDS,
) -> bool:
    """Best-effort drain one unambiguous bounded body without waiting forever.

    This is only for a route that rejects request metadata before reading any
    body bytes. Ambiguous framing is never consumed, and an incomplete drain
    forces the HTTP/1.1 connection closed after the fixed response.
    """

    if type(maximum_bytes) is not int or maximum_bytes < 0 \
            or type(maximum_seconds) not in {int, float} \
            or not math.isfinite(maximum_seconds) or maximum_seconds <= 0:
        raise ValueError("Rejected-body drain bounds are invalid")
    length = _safe_bounded_length(handler, maximum_bytes)
    if length is None:
        _close_after_response(handler)
        return False
    if length == 0:
        return True
    connection = getattr(handler, "connection", None)
    get_timeout = getattr(connection, "gettimeout", None)
    set_timeout = getattr(connection, "settimeout", None)
    reader = getattr(getattr(handler, "rfile", None), "read1", None)
    if not callable(reader):
        reader = getattr(getattr(handler, "rfile", None), "read", None)
    if not callable(get_timeout) or not callable(set_timeout) \
            or not callable(reader):
        _close_after_response(handler)
        return False
    drained, original_timeout, timeout_known = False, None, False
    try:
        original_timeout = get_timeout()
        timeout_known = True
        deadline = time.monotonic() + maximum_seconds
        remaining = length
        while remaining:
            wait = deadline - time.monotonic()
            if wait <= 0:
                break
            set_timeout(wait)
            chunk = reader(min(remaining, _DRAIN_CHUNK_BYTES))
            if not isinstance(chunk, bytes) or not chunk:
                break
            remaining -= len(chunk)
        drained = remaining == 0
    except (BlockingIOError, OSError, TimeoutError, TypeError, ValueError):
        drained = False
    finally:
        try:
            if timeout_known:
                set_timeout(original_timeout)
            else:
                drained = False
        except (OSError, TypeError, ValueError):
            drained = False
    if not drained:
        _close_after_response(handler)
    return drained


def _safe_bounded_length(handler: Any, maximum_bytes: int) -> int | None:
    try:
        headers = handler.headers
        if headers.get_all("Transfer-Encoding", []):
            return None
        values = headers.get_all("Content-Length", []) or []
    except (AttributeError, TypeError, ValueError):
        return None
    if len(values) != 1 or not _decimal_length(values[0]):
        return None
    length = int(values[0])
    return length if length <= maximum_bytes else None


def _decimal_length(value: Any) -> bool:
    return type(value) is str and 0 < len(value) <= 20 \
        and value.isascii() and value.isdecimal()


def _close_after_response(handler: Any) -> None:
    try:
        handler.close_connection = True
    except (AttributeError, TypeError, ValueError):
        pass


def decode_json_object(raw: bytes) -> dict[str, Any]:
    """Decode strict UTF-8 JSON, duplicate fields, and non-finite values."""

    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON field: {key}")
            result[key] = value
        return result

    def reject_nonfinite(value: str) -> Any:
        raise ValueError(f"non-finite JSON number: {value}")

    def finite_float(value: str) -> float:
        parsed = float(value)
        if not math.isfinite(parsed):
            raise ValueError(f"out-of-range JSON number: {value}")
        return parsed

    try:
        value = json.loads(
            raw.decode("utf-8"), object_pairs_hook=reject_duplicates,
            parse_constant=reject_nonfinite,
            parse_float=finite_float,
        )
    except (
        UnicodeDecodeError, json.JSONDecodeError, RecursionError, ValueError,
    ) as exc:
        raise HttpJsonRequestError(
            HTTPStatus.BAD_REQUEST,
            "invalid_json",
            "Request body must be strict UTF-8 JSON without duplicate fields.",
        ) from exc
    if not isinstance(value, dict):
        raise HttpJsonRequestError(
            HTTPStatus.BAD_REQUEST,
            "invalid_json",
            "Request body must be a JSON object.",
        )
    return value
