"""Bounded duplicate-safe JSON request decoding for local HTTP routes."""

from __future__ import annotations

from dataclasses import dataclass
from http import HTTPStatus
import json
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

    content_type = (
        handler.headers.get("Content-Type", "")
        .split(";", 1)[0]
        .strip()
        .lower()
    )
    if content_type != "application/json":
        raise HttpJsonRequestError(
            HTTPStatus.UNSUPPORTED_MEDIA_TYPE,
            "unsupported_media_type",
            "Content-Type must be application/json.",
        )
    raw_length = handler.headers.get("Content-Length")
    try:
        content_length = int(raw_length or "")
    except ValueError:
        content_length = -1
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
    """Decode strict UTF-8 JSON while rejecting duplicate object fields."""

    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON field: {key}")
            result[key] = value
        return result

    try:
        value = json.loads(
            raw.decode("utf-8"), object_pairs_hook=reject_duplicates,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
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
