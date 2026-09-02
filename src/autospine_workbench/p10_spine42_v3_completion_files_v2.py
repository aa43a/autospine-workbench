"""Read-only exact run-root checks for P10.7a v2 candidate discovery."""

from __future__ import annotations

from pathlib import Path
import stat

from .spine42_bundle_files import (
    Spine42BundleFilesError, is_alias, require_real_directory,
)

_EXPECTED = {"request.json": "file", "events": "directory"}


class P10Spine42V3CompletionFilesV2Error(RuntimeError):
    """Raised when a P10.7a run root is not the exact fixed inventory."""


def require_p10_spine42_v3_completion_run_files_v2(directory):
    """Require request.json plus events and reject every alias or extra."""

    try:
        root = require_real_directory(
            Path(directory), "P10.7a v2 completion run")
        children = list(root.iterdir())
        names = [child.name for child in children]
        if len(children) != len(_EXPECTED) or set(names) != set(_EXPECTED) \
                or len({name.casefold() for name in names}) != len(names):
            _fail("P10.7a v2 run root inventory differs")
        for child in children:
            if is_alias(child):
                _fail("P10.7a v2 run root contains an alias")
            mode = child.lstat().st_mode
            valid = stat.S_ISREG(mode) if _EXPECTED[child.name] == "file" \
                else stat.S_ISDIR(mode)
            if not valid:
                _fail("P10.7a v2 run root entry type differs")
        return root
    except P10Spine42V3CompletionFilesV2Error:
        raise
    except (OSError, TypeError, ValueError,
            Spine42BundleFilesError) as exc:
        raise P10Spine42V3CompletionFilesV2Error(
            "P10.7a v2 run root cannot be inspected safely") from exc


def _fail(message):
    raise P10Spine42V3CompletionFilesV2Error(message)


__all__ = [
    "P10Spine42V3CompletionFilesV2Error",
    "require_p10_spine42_v3_completion_run_files_v2",
]
