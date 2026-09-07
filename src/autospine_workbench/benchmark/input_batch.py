"""Explicit split-scoped PNG checks; never turn machine signals into labels."""

import hashlib
from pathlib import Path

from ..resolved_project import canonical_sha256
from ..safe_input_files import read_real_file
from .input_quality import analyze_input_image
from .source_files import MAX_SOURCE_BYTES
from .validation import SPLIT_COUNTS, validate_benchmark_manifest


def lint_inputs(manifest, workspace, *, split="development"):
    validate_benchmark_manifest(manifest)
    if manifest["split_status"] != "frozen" or split not in SPLIT_COUNTS:
        raise ValueError("benchmark_frozen_split_required")
    rows = []
    for character in manifest["characters"]:
        if character["dataset_split"] != split:
            continue
        source = character["source"]
        try:
            raw = read_real_file(Path(workspace) / source["path"], MAX_SOURCE_BYTES, "benchmark image")
            if len(raw) != source["byte_size"] or hashlib.sha256(raw).hexdigest() != source["sha256"]:
                raise ValueError("source_content_changed")
            result = analyze_input_image(raw)
            if result["canvas"] != source["canvas"]:
                raise ValueError("source_canvas_changed")
            rows.append({"character_id": character["id"], "source_sha256": source["sha256"],
                         "status": "analyzed", "reason_code": None, "analysis": result})
        except (OSError, ValueError, RuntimeError) as exc:
            reason = getattr(exc, "reason_code", None)
            if reason is None:
                reason = str(exc) if str(exc) in {"source_content_changed", "source_canvas_changed"} else "source_unavailable"
            rows.append({"character_id": character["id"], "source_sha256": source["sha256"],
                         "status": "blocked", "reason_code": reason, "analysis": None})
    return {"schema": "autospine.benchmark-input-batch/v1", "authority": "none",
            "dataset_sha256": canonical_sha256(manifest), "dataset_split": split,
            "annotation_effect": "none", "rigging_evaluation": "not_run", "records": rows}
