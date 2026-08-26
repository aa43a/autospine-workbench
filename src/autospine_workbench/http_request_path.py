"""Strict URL path segmentation for the local workbench API."""

from __future__ import annotations

from urllib.parse import unquote, urlsplit


def safe_url_path_parts(target: str) -> list[str]:
    """Decode path segments and reject traversal or separator aliases."""

    path = urlsplit(target).path
    try:
        parts = [unquote(part) for part in path.split("/") if part]
    except UnicodeError as exc:
        raise ValueError("invalid URL encoding") from exc
    if any(
        part in {".", ".."}
        or "\x00" in part
        or "/" in part
        or "\\" in part
        for part in parts
    ):
        raise ValueError("unsafe URL path")
    return parts
