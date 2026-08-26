"""Containment-checked static-file routing for the local workbench."""

from __future__ import annotations

from pathlib import Path
from typing import Callable


def serve_static_response(
    parts: list[str],
    web_root: Path | None,
    send_file: Callable[[Path], None],
) -> bool:
    """Serve an exact file or a safe frontend-history fallback."""

    if web_root is None:
        return False
    relative = Path(*parts) if parts else Path("index.html")
    candidate = web_root / relative
    try:
        root = web_root.resolve(strict=True)
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, ValueError):
        if not parts or "." in parts[-1]:
            return False
        candidate = web_root / "index.html"
        try:
            resolved = candidate.resolve(strict=True)
            resolved.relative_to(web_root.resolve(strict=True))
        except (OSError, ValueError):
            return False
    if not resolved.is_file():
        return False
    send_file(resolved)
    return True
