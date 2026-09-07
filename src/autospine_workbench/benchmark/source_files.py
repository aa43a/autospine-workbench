"""Read-only benchmark source verification, separate from rigging outcomes."""

import hashlib
from pathlib import Path, PurePosixPath
import struct

from ..resolved_project import canonical_sha256
from ..safe_input_files import SafeInputFileError, read_real_file
from .validation import validate_benchmark_manifest

MAX_SOURCE_BYTES = 256 << 20


def verify_sources(manifest, workspace):
    validate_benchmark_manifest(manifest)
    rows, seen = [], set()
    for character in manifest["characters"]:
        for source in [character["source"], *[p["source"] for p in character["psd_candidates"]]]:
            key = (source["path"], source["sha256"])
            if key in seen:
                continue
            seen.add(key)
            reason = _check_source(source, workspace)
            rows.append({"path": source["path"], "expected_sha256": source["sha256"],
                         "status": "verified" if reason is None else "blocked", "reason_code": reason})
    rows.sort(key=lambda row: row["path"])
    return {"schema": "autospine.benchmark-source-verification/v1", "authority": "none",
            "dataset_sha256": canonical_sha256(manifest),
            "status": "verified" if all(row["status"] == "verified" for row in rows) else "blocked",
            "counts": {"total": len(rows), "verified": sum(row["status"] == "verified" for row in rows)},
            "files": rows, "rigging_evaluation": "not_run"}


def _check_source(source, workspace):
    name = source["path"]
    path = PurePosixPath(name)
    if path.is_absolute() or any(part in {".", ".."} for part in name.split("/")) \
            or "\\" in name or ":" in name:
        return "source_path_invalid"
    try:
        raw = read_real_file(Path(workspace).joinpath(*path.parts), MAX_SOURCE_BYTES, "benchmark source")
    except (SafeInputFileError, OSError):
        return "source_unavailable"
    if len(raw) != source["byte_size"] or hashlib.sha256(raw).hexdigest() != source["sha256"]:
        return "source_content_changed"
    try:
        if name.lower().endswith(".png") and raw[:8] == b"\x89PNG\r\n\x1a\n" and raw[12:16] == b"IHDR":
            canvas = list(struct.unpack(">II", raw[16:24]))
        elif name.lower().endswith(".psd") and raw[:6] == b"8BPS\x00\x01":
            height, width = struct.unpack(">II", raw[14:22])
            canvas = [width, height]
        else:
            return "source_format_invalid"
    except struct.error:
        return "source_format_invalid"
    return None if canvas == source["canvas"] else "source_canvas_changed"
