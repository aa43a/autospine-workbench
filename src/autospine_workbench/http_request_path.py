"""Strict URL path segmentation for the local workbench API."""

from __future__ import annotations

from urllib.parse import unquote, urlsplit


def safe_url_path_parts(target: str) -> list[str]:
    """Decode path segments and reject traversal or separator aliases."""

    path = urlsplit(target).path
    if path == "/":
        return []
    raw_parts = path.split("/")
    if not path.startswith("/") or raw_parts[0] \
            or any(part == "" for part in raw_parts[1:]):
        raise ValueError("noncanonical URL path")
    try:
        parts = [unquote(part) for part in raw_parts[1:]]
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
