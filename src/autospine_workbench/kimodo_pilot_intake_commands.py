"""Read-once filesystem boundary for the real Kimodo pilot intake audit."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from .camera_model_validation import MAX_DOCUMENT_BYTES as MAX_CAMERA_BYTES
from .kimodo_npz_map_validation import MAX_DOCUMENT_BYTES as MAX_MAP_BYTES
from .kimodo_npz_source import MAX_RAW_NPZ_BYTES, MAX_SOURCE_DOCUMENT_BYTES
from .kimodo_pilot_intake import (
    MAX_EXTERNAL_PROVENANCE_BYTES,
    KimodoPilotIntakeError,
    audit_kimodo_pilot_intake,
)
from .kimodo_pilot_intake_validation import (
    require_kimodo_pilot_intake_report,
)
from .safe_input_files import (
    SafeInputFileError,
    read_real_file,
    strict_json_object,
)


class KimodoPilotIntakeCommandError(RuntimeError):
    """Raised when explicit pilot files cannot be audited safely."""


@dataclass(frozen=True, slots=True)
class KimodoPilotIntakeCommandResult:
    """Canonical, isolated audit result for CLI serialization."""

    _canonical_json: str

    @property
    def document(self) -> dict[str, Any]:
        return json.loads(self._canonical_json)

    @property
    def report_sha256(self) -> str:
        return self.document["intake_report_sha256"]


def audit_kimodo_pilot_intake_command(
    raw_npz_path: Path,
    sidecar_path: Path,
    map_path: Path,
    camera_path: Path,
    checkpoint_manifest_path: Path,
    generation_request_path: Path,
) -> KimodoPilotIntakeCommandResult:
    """Read six explicit files once and return a path-free canonical report."""

    try:
        raw_npz = read_real_file(
            raw_npz_path, MAX_RAW_NPZ_BYTES, "Kimodo pilot raw NPZ"
        )
        source = strict_json_object(read_real_file(
            sidecar_path, MAX_SOURCE_DOCUMENT_BYTES,
            "Kimodo pilot source sidecar",
        ), "Kimodo pilot source sidecar")
        mapping = strict_json_object(read_real_file(
            map_path, MAX_MAP_BYTES, "Kimodo pilot projection map",
        ), "Kimodo pilot projection map")
        camera = strict_json_object(read_real_file(
            camera_path, MAX_CAMERA_BYTES, "Kimodo pilot camera",
        ), "Kimodo pilot camera")
        checkpoint = read_real_file(
            checkpoint_manifest_path, MAX_EXTERNAL_PROVENANCE_BYTES,
            "Kimodo pilot checkpoint manifest",
        )
        request = read_real_file(
            generation_request_path, MAX_EXTERNAL_PROVENANCE_BYTES,
            "Kimodo pilot generation request",
        )
        report = audit_kimodo_pilot_intake(
            raw_npz, source, mapping, camera, checkpoint, request
        )
        require_kimodo_pilot_intake_report(report)
        canonical = json.dumps(
            report, ensure_ascii=False, allow_nan=False,
            sort_keys=True, separators=(",", ":"),
        )
        return KimodoPilotIntakeCommandResult(canonical)
    except KimodoPilotIntakeCommandError:
        raise
    except (
        KimodoPilotIntakeError, OSError, OverflowError, RecursionError,
        SafeInputFileError, TypeError, ValueError,
    ) as exc:
        raise KimodoPilotIntakeCommandError(
            "Kimodo pilot intake command failed"
        ) from exc


__all__ = [
    "KimodoPilotIntakeCommandError", "KimodoPilotIntakeCommandResult",
    "audit_kimodo_pilot_intake_command",
]
