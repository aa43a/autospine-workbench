"""Streaming local-file responses shared by workbench routes."""

from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Any, Callable


CHUNK_BYTES = 64 * 1024


def send_file_response(
    handler: Any,
    path: Path,
    common_headers: Callable[[], None],
    *,
    extra_headers: dict[str, str] | None = None,
) -> None:
    """Send one already-authorized real file without exposing read errors."""

    try:
        metadata = path.stat()
        content_type = (
            mimetypes.guess_type(path.name)[0]
            or "application/octet-stream"
        )
        handler.send_response(200)
        common_headers()
        handler.send_header("Content-Type", content_type)
        handler.send_header("Content-Length", str(metadata.st_size))
        handler.send_header(
            "ETag", f'W/"{metadata.st_mtime_ns:x}-{metadata.st_size:x}"',
        )
        for key, value in (extra_headers or {}).items():
            handler.send_header(key, value)
        handler.end_headers()
        if handler.command == "HEAD":
            return
        with path.open("rb") as source:
            while chunk := source.read(CHUNK_BYTES):
                handler.wfile.write(chunk)
    except (OSError, BrokenPipeError, ConnectionError):
        if not handler.wfile.closed:
            handler.close_connection = True
