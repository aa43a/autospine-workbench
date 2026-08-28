"""Validate a readable P10.7c draft and emit canonical JSON bytes."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src"
if str(SOURCE) not in sys.path:
    sys.path.insert(0, str(SOURCE))

from autospine_workbench.safe_input_files import (  # noqa: E402
    read_real_file,
    strict_json_object,
)
from autospine_workbench.spine42_v3_setup_regression_manifest import (  # noqa: E402
    MAX_REQUEST_BYTES,
    canonical_request_bytes,
    require_spine42_v3_setup_regression_request,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Emit one validated P10.7c request without a trailing newline"
    )
    parser.add_argument("draft", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        raw = read_real_file(args.draft, MAX_REQUEST_BYTES, "request draft")
        value = require_spine42_v3_setup_regression_request(
            strict_json_object(raw, "request draft")
        )
        output = canonical_request_bytes(value)
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        parser.error(str(exc))
    try:
        _write_new_atomic(args.output, output)
    except OSError as exc:
        parser.error(f"output must be a new writable file: {exc}")
    print(f"wrote={args.output};bytes={len(output)}")
    return 0


def _write_new_atomic(output_path: Path, data: bytes) -> None:
    """Publish complete bytes without overwriting an existing destination."""

    output_path = Path(output_path)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=output_path.parent, prefix=f".{output_path.name}.",
            suffix=".tmp", delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary_path, output_path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
