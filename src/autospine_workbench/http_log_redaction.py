"""Redact ephemeral local read-session values from access-log arguments."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import unquote


_QUERY_PARAMETER = re.compile(r"([?&])([^=&\s]+)=([^&\s]*)")


def redact_http_log_arguments(values: tuple[Any, ...]) -> tuple[Any, ...]:
    return tuple(
        _QUERY_PARAMETER.sub(_redact_session_parameter, value)
        if type(value) is str else value
        for value in values
    )


def _redact_session_parameter(match: re.Match[str]) -> str:
    try:
        is_session = unquote(match.group(2), errors="strict") == "session"
    except UnicodeDecodeError:
        is_session = False
    if not is_session:
        return match.group(0)
    return f"{match.group(1)}{match.group(2)}=<redacted>"


__all__ = ["redact_http_log_arguments"]
