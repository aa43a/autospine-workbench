"""Zero-write application command for P10.6a motion-consumer admission."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any

from .body_sway_dynamic_seam_head_checks import (
    require_current_body_sway_dynamic_seam_heads,
)
from .body_sway_dynamic_seam_validation import (
    MAX_DOCUMENT_BYTES as MAX_DYNAMIC_SEAM_PROBE_BYTES,
    body_sway_dynamic_seam_probe_sha256,
)
from .body_sway_motion_consumer_admission import (
    BodySwayMotionConsumerAdmissionError,
    compile_body_sway_motion_consumer_admission_core,
    seal_body_sway_motion_consumer_admission,
)
from .body_sway_motion_consumer_validation import (
    body_sway_motion_consumer_admission_sha256,
    require_body_sway_motion_consumer_admission,
)
from .manifest_artifacts import require_sha256
from .reviewed_motion_bundle_reader import (
    VerifiedReviewedMotionBundleReader,
)
from .safe_input_files import read_real_file, strict_json_object


class P10MotionConsumerAdmissionCommandError(RuntimeError):
    """Raised when one exact read-only P10.6a command cannot complete."""


@dataclass(frozen=True, slots=True)
class P10MotionConsumerAdmissionCommandResult:
    """Frozen, path-free command output with copy-isolated JSON access."""

    project_id: str
    clip_id: str
    dynamic_seam_probe_sha256: str
    motion_instance_v2_sha256: str
    reviewed_motion_bundle_sha256: str
    admission_sha256: str
    _canonical_json: str = field(repr=False)

    @property
    def document(self) -> dict[str, Any]:
        return json.loads(self._canonical_json)


def compile_body_sway_motion_consumer_admission_command(
    state_root: Path,
    project_id: str,
    dynamic_seam_probe_path: Path,
    *,
    dynamic_seam_probe_sha256: str,
) -> P10MotionConsumerAdmissionCommandResult:
    """Replay one probe and P9 bundle around two current-head checks."""

    try:
        probe = strict_json_object(
            read_real_file(
                dynamic_seam_probe_path,
                MAX_DYNAMIC_SEAM_PROBE_BYTES,
                "body-sway dynamic seam probe",
            ),
            "body-sway dynamic seam probe",
        )
        expected_probe_sha = require_sha256(
            dynamic_seam_probe_sha256,
            "Body-sway dynamic seam probe digest",
        )
        actual_probe_sha = body_sway_dynamic_seam_probe_sha256(probe)
        if actual_probe_sha != expected_probe_sha:
            raise P10MotionConsumerAdmissionCommandError(
                "Dynamic seam probe differs from its explicit address"
            )
        if probe.get("project_id") != project_id:
            raise P10MotionConsumerAdmissionCommandError(
                "Dynamic seam probe project differs from address"
            )
        p9 = _p9_address(probe)
        bundle = VerifiedReviewedMotionBundleReader(Path(state_root)).load(
            project_id,
            p9["motion_instance_v2_sha256"],
            p9["bundle_sha256"],
        )
        _require_exact_bundle(bundle, probe, project_id, p9)
        source = probe["source"]
        before = require_current_body_sway_dynamic_seam_heads(
            Path(state_root), source
        )
        core = compile_body_sway_motion_consumer_admission_core(
            probe, bundle
        )
        after = require_current_body_sway_dynamic_seam_heads(
            Path(state_root), source
        )
        _require_unchanged_observations(before, after)
        admission = seal_body_sway_motion_consumer_admission(
            core, before, after
        )
        admission_document = admission.document
        require_body_sway_motion_consumer_admission(
            admission_document,
            dynamic_seam_probe=probe,
            reviewed_bundle=bundle,
        )
        admission_sha = body_sway_motion_consumer_admission_sha256(
            admission_document,
            dynamic_seam_probe=probe,
            reviewed_bundle=bundle,
        )
        if admission.sha256 != admission_sha:
            raise P10MotionConsumerAdmissionCommandError(
                "Motion-consumer admission identity differs from validated bytes"
            )
        document = _result_document(
            admission_document, actual_probe_sha, p9, admission_sha,
            before, after,
        )
        return P10MotionConsumerAdmissionCommandResult(
            project_id=document["project_id"],
            clip_id=document["clip_id"],
            dynamic_seam_probe_sha256=actual_probe_sha,
            motion_instance_v2_sha256=p9["motion_instance_v2_sha256"],
            reviewed_motion_bundle_sha256=p9["bundle_sha256"],
            admission_sha256=admission_sha,
            _canonical_json=_canonical(document),
        )
    except P10MotionConsumerAdmissionCommandError:
        raise
    except _COMMAND_FAILURES as exc:
        raise P10MotionConsumerAdmissionCommandError(
            "Body-sway motion-consumer admission compilation failed"
        ) from exc


def _p9_address(probe: Mapping[str, Any]) -> dict[str, str]:
    p9 = probe["source"]["body_sway_continuous_preview_proof"] \
        ["source"]["amplitude_envelope_candidate"]["source"] \
        ["reviewed_probe_report"]["source"]["p9"]
    return {
        "motion_instance_v2_sha256": p9["motion_instance_v2_sha256"],
        "bundle_sha256": p9["bundle_sha256"],
    }


def _require_exact_bundle(bundle, probe, project_id, p9) -> None:
    if bundle.project_id != project_id \
            or bundle.clip_id != probe["clip_id"] \
            or bundle.motion_instance_v2_sha256 \
                != p9["motion_instance_v2_sha256"] \
            or bundle.bundle_sha256 != p9["bundle_sha256"]:
        raise P10MotionConsumerAdmissionCommandError(
            "Reviewed-motion bundle differs from embedded exact address"
        )


def _require_unchanged_observations(before, after) -> None:
    if before.identity != after.identity:
        raise P10MotionConsumerAdmissionCommandError(
            "Motion-consumer review head identity changed during compilation"
        )
    if before.canonical_bytes != after.canonical_bytes:
        raise P10MotionConsumerAdmissionCommandError(
            "Motion-consumer review head documents changed during compilation"
        )


def _result_document(admission, probe_sha, p9, admission_sha,
                     before, after) -> dict[str, Any]:
    return {
        "project_id": admission["project_id"],
        "clip_id": admission["clip_id"],
        "dynamic_seam_probe_sha256": probe_sha,
        "reviewed_motion_address": {
            "motion_instance_v2_sha256": p9["motion_instance_v2_sha256"],
            "reviewed_motion_bundle_sha256": p9["bundle_sha256"],
        },
        "body_sway_motion_consumer_admission_sha256": admission_sha,
        "admission": admission,
        "head_observation": {
            "method": "outer-before-after-consumer-core-compilation",
            "scope": "compile_time",
            "before": before.document,
            "after": after.document,
            "checks": {
                "before_after_identity": "exact_match",
                "before_after_documents": "canonical_bytes_exact_match",
            },
            "permanent_authority_claimed": False,
        },
    }


def _canonical(value: Any) -> str:
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    )


_COMMAND_FAILURES = (
    AttributeError,
    BodySwayMotionConsumerAdmissionError,
    KeyError,
    OSError,
    OverflowError,
    RecursionError,
    RuntimeError,
    TypeError,
    UnicodeError,
    ValueError,
)
