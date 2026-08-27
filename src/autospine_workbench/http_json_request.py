"""Bounded duplicate-safe JSON request decoding for local HTTP routes."""

from __future__ import annotations

from dataclasses import dataclass
from http import HTTPStatus
import json
import math
from typing import Any


MAX_REQUEST_BODY = 1024 * 1024


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
    content_length = int(raw_length) \
        if raw_length.isascii() and raw_length.isdecimal() else -1
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
