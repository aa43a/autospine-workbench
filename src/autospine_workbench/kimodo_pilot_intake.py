"""Pure M1 intake audit for one recorded Kimodo pilot export."""

from __future__ import annotations

from collections.abc import Mapping
import hashlib
import json
from typing import Any

from .camera_model_validation import (
    CameraModelError,
    camera_model_sha256,
    require_camera_matches_kimodo_map,
)
from .kimodo_npz_compile_run import (
    KimodoNpzCompileRunError,
    compile_kimodo_npz_motion_run,
)
from .kimodo_npz_map_validation import (
    KimodoNpzMapError,
    kimodo_npz_map_sha256,
)
from .kimodo_npz_source import (
    MAX_RAW_NPZ_BYTES,
    KimodoNpzSourceError,
    kimodo_npz_source_sha256,
)
from .kimodo_pilot_intake_validation import (
    AUTHORITY,
    CLAIMS,
    FORMAT,
    FORMAT_VERSION,
    MAX_EXTERNAL_PROVENANCE_BYTES,
    STATUS,
    kimodo_pilot_intake_report_sha256,
    require_kimodo_pilot_intake_report,
)


class KimodoPilotIntakeError(ValueError):
    """Raised when a real pilot intake cannot be admitted without guessing."""


def audit_kimodo_pilot_intake(
    raw_npz: bytes,
    source: Mapping[str, Any],
    mapping: Mapping[str, Any],
    camera: Mapping[str, Any],
    checkpoint_manifest: bytes,
    generation_request: bytes,
) -> dict[str, Any]:
    """Compile P7 in memory and bind recorded provenance plus a P8 camera."""

    try:
        raw = _bounded_bytes(raw_npz, MAX_RAW_NPZ_BYTES, "raw NPZ")
        checkpoint = _bounded_bytes(
            checkpoint_manifest, MAX_EXTERNAL_PROVENANCE_BYTES,
            "checkpoint manifest",
        )
        request = _bounded_bytes(
            generation_request, MAX_EXTERNAL_PROVENANCE_BYTES,
            "generation request",
        )
        sidecar = _snapshot(source, "source sidecar")
        map_document = _snapshot(mapping, "projection map")
        camera_document = _snapshot(camera, "camera")
        producer = sidecar.get("producer")
        if type(producer) is not dict or producer.get("status") != "recorded":
            raise KimodoPilotIntakeError(
                "Kimodo pilot intake requires recorded producer provenance"
            )
        _bind_external_digest(
            checkpoint, producer.get("checkpoint_manifest_sha256"),
            "checkpoint manifest",
        )
        _bind_external_digest(
            request, producer.get("generation_request_sha256"),
            "generation request",
        )
        compiled, run = compile_kimodo_npz_motion_run(
            raw, sidecar, map_document
        )
        require_camera_matches_kimodo_map(camera_document, map_document)
        run_document = run.document
        report = {
            "format": FORMAT,
            "format_version": FORMAT_VERSION,
            "source": {
                "raw_npz_sha256": hashlib.sha256(raw).hexdigest(),
                "raw_npz_byte_length": len(raw),
                "source_sha256": kimodo_npz_source_sha256(sidecar),
                "source_id": sidecar["source_id"],
                "map_sha256": kimodo_npz_map_sha256(map_document),
                "map_id": map_document["map_id"],
                "clip_id": map_document["clip"]["clip_id"],
                "camera_sha256": camera_model_sha256(camera_document),
                "camera_id": camera_document["camera_id"],
                "checkpoint_manifest_sha256": hashlib.sha256(
                    checkpoint
                ).hexdigest(),
                "checkpoint_manifest_byte_length": len(checkpoint),
                "generation_request_sha256": hashlib.sha256(request).hexdigest(),
                "generation_request_byte_length": len(request),
            },
            "producer": {
                field: producer[field] for field in (
                    "implementation", "repository_revision", "model_id",
                    "checkpoint_revision", "seed", "sample_index",
                )
            },
            "p7_preview": {
                "compiler_id": run_document["compiler"]["id"],
                "compiler_version": run_document["compiler"]["version"],
                "motion_ir_sha256": compiled.sha256,
                "compile_run_sha256": run.sha256,
                "array_inventory_sha256": compiled.array_inventory_sha256,
                "validation": run_document["validation"],
            },
            "p8_input": {
                "camera_map_binding": "verified",
                "projection": camera_document["projection"],
                "depth_positive": camera_document["depth_positive"],
            },
            "claims": dict(CLAIMS),
            "authority": dict(AUTHORITY),
            "status": STATUS,
        }
        report["intake_report_sha256"] = \
            kimodo_pilot_intake_report_sha256(report)
        require_kimodo_pilot_intake_report(report)
        return _snapshot(report, "intake report")
    except KimodoPilotIntakeError:
        raise
    except (
        CameraModelError, KimodoNpzCompileRunError, KimodoNpzMapError,
        KimodoNpzSourceError, KeyError, OverflowError, RecursionError,
        TypeError, ValueError,
    ) as exc:
        raise KimodoPilotIntakeError(
            f"Kimodo pilot intake audit failed: {exc}"
        ) from exc


def _bounded_bytes(value: Any, maximum: int, label: str) -> bytes:
    if type(value) is not bytes or not 1 <= len(value) <= maximum:
        raise KimodoPilotIntakeError(
            f"Kimodo pilot intake {label} bytes are invalid"
        )
    return value


def _bind_external_digest(value: bytes, expected: Any, label: str) -> None:
    if hashlib.sha256(value).hexdigest() != expected:
        raise KimodoPilotIntakeError(
            f"Kimodo pilot intake {label} identity differs from sidecar"
        )


def _snapshot(value: Mapping[str, Any], label: str) -> dict[str, Any]:
    try:
        result = json.loads(json.dumps(
            dict(value), ensure_ascii=False, allow_nan=False,
            sort_keys=True, separators=(",", ":"),
        ))
    except (OverflowError, TypeError, ValueError) as exc:
        raise KimodoPilotIntakeError(
            f"Kimodo pilot intake {label} is not canonical JSON"
        ) from exc
    if type(result) is not dict:
        raise KimodoPilotIntakeError(
            f"Kimodo pilot intake {label} must be an object"
        )
    return result


__all__ = [
    "KimodoPilotIntakeError", "MAX_EXTERNAL_PROVENANCE_BYTES",
    "audit_kimodo_pilot_intake",
]
