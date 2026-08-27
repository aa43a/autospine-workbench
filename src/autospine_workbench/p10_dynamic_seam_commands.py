"""Zero-write application command for P10.5d dynamic seam evidence."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any

from .body_sway_continuous_proof_profile import (
    MAX_DOCUMENT_BYTES as MAX_CONTINUOUS_PROOF_BYTES,
)
from .body_sway_continuous_proof_validation import (
    body_sway_continuous_proof_sha256,
)
from .body_sway_dynamic_seam import (
    BodySwayDynamicSeamProbeError,
    compile_body_sway_dynamic_seam_probe,
)
from .body_sway_dynamic_seam_head_checks import (
    require_current_body_sway_dynamic_seam_heads,
)
from .body_sway_dynamic_seam_source import (
    build_body_sway_dynamic_seam_source,
)
from .body_sway_dynamic_seam_validation import (
    body_sway_dynamic_seam_probe_sha256,
    require_body_sway_dynamic_seam_probe,
)
from .manifest_artifacts import require_sha256
from .reviewed_seam_anchor_set_bundle_reader import (
    VerifiedReviewedSeamAnchorSetBundleReader,
)
from .safe_input_files import read_real_file, strict_json_object


class P10DynamicSeamCommandError(RuntimeError):
    """Raised when one exact read-only P10.5d command cannot complete."""


@dataclass(frozen=True, slots=True)
class P10DynamicSeamCommandResult:
    """Frozen, path-free command output with copy-isolated JSON access."""

    project_id: str
    clip_id: str
    continuous_proof_sha256: str
    reviewed_set_sha256: str
    reviewed_set_bundle_sha256: str
    source_set_sha256: str
    probe_sha256: str
    _canonical_json: str = field(repr=False)

    @property
    def document(self) -> dict[str, Any]:
        return json.loads(self._canonical_json)


def compile_body_sway_dynamic_seam_probe_command(
    state_root: Path,
    project_id: str,
    continuous_proof_path: Path,
    *,
    reviewed_set_sha256: str,
    reviewed_set_bundle_sha256: str,
) -> P10DynamicSeamCommandResult:
    """Compile exact historical inputs between two current-head checks."""

    try:
        proof = strict_json_object(
            read_real_file(
                continuous_proof_path,
                MAX_CONTINUOUS_PROOF_BYTES,
                "body-sway continuous proof",
            ),
            "body-sway continuous proof",
        )
        proof_sha256 = body_sway_continuous_proof_sha256(proof)
        if proof.get("project_id") != project_id:
            raise P10DynamicSeamCommandError(
                "Body-sway continuous proof project differs from address"
            )
        require_sha256(
            reviewed_set_sha256,
            "Reviewed seam-anchor set digest",
        )
        require_sha256(
            reviewed_set_bundle_sha256,
            "Reviewed seam-anchor set bundle digest",
        )
        bundle = VerifiedReviewedSeamAnchorSetBundleReader(
            Path(state_root)
        ).load(
            project_id,
            reviewed_set_sha256,
            reviewed_set_bundle_sha256,
        )
        _require_exact_bundle_address(
            bundle,
            project_id,
            reviewed_set_sha256,
            reviewed_set_bundle_sha256,
        )
        source = build_body_sway_dynamic_seam_source(
            continuous_proof=proof,
            seam_anchor_candidates=bundle.candidates,
            seam_anchor_review_decision=bundle.decision,
            reviewed_seam_anchor_set=bundle.reviewed_set,
            reviewed_set_bundle_sha256=bundle.bundle_sha256,
        )
        if source["body_sway_continuous_proof_sha256"] != proof_sha256 \
                or source["reviewed_seam_anchor_set_sha256"] \
                != bundle.set_sha256 \
                or source["reviewed_seam_anchor_set_bundle_sha256"] \
                != bundle.bundle_sha256:
            raise P10DynamicSeamCommandError(
                "Exact input identity changed during source closure"
            )
        before = require_current_body_sway_dynamic_seam_heads(
            Path(state_root), source
        )
        probe = compile_body_sway_dynamic_seam_probe(source)
        after = require_current_body_sway_dynamic_seam_heads(
            Path(state_root), source
        )
        _require_unchanged_observations(before, after)
        probe_document = probe.document
        require_body_sway_dynamic_seam_probe(probe_document)
        probe_sha256 = body_sway_dynamic_seam_probe_sha256(probe_document)
        if probe.sha256 != probe_sha256:
            raise P10DynamicSeamCommandError(
                "Dynamic seam probe identity differs from validated bytes"
            )
        head_document = _head_observation(before, after)
        document = {
            "project_id": probe_document["project_id"],
            "clip_id": probe_document["clip_id"],
            "continuous_proof_sha256": proof_sha256,
            "reviewed_seam_anchor_set_sha256": bundle.set_sha256,
            "reviewed_seam_anchor_set_bundle_sha256": bundle.bundle_sha256,
            "source_set_sha256": source["source_set_sha256"],
            "body_sway_dynamic_seam_probe_sha256": probe_sha256,
            "probe": probe_document,
            "head_observation": head_document,
        }
        return P10DynamicSeamCommandResult(
            project_id=document["project_id"],
            clip_id=document["clip_id"],
            continuous_proof_sha256=proof_sha256,
            reviewed_set_sha256=bundle.set_sha256,
            reviewed_set_bundle_sha256=bundle.bundle_sha256,
            source_set_sha256=source["source_set_sha256"],
            probe_sha256=probe_sha256,
            _canonical_json=_canonical(document),
        )
    except P10DynamicSeamCommandError:
        raise
    except _COMMAND_FAILURES as exc:
        raise P10DynamicSeamCommandError(
            "Body-sway dynamic seam probe compilation failed"
        ) from exc


def _require_exact_bundle_address(bundle, project, set_sha, bundle_sha) -> None:
    if bundle.project_id != project or bundle.set_sha256 != set_sha \
            or bundle.bundle_sha256 != bundle_sha:
        raise P10DynamicSeamCommandError(
            "Reviewed seam-anchor bundle differs from explicit address"
        )


def _require_unchanged_observations(before, after) -> None:
    if before.identity != after.identity:
        raise P10DynamicSeamCommandError(
            "Dynamic seam review head identity changed during analysis"
        )
    if before.canonical_bytes != after.canonical_bytes:
        raise P10DynamicSeamCommandError(
            "Dynamic seam review head documents changed during analysis"
        )


def _head_observation(before, after) -> dict[str, Any]:
    return {
        "method": "outer-before-after-analysis-of-inner-double-snapshots",
        "scope": "compile_time",
        "before": before.document,
        "after": after.document,
        "checks": {
            "before_after_identity": "exact_match",
            "before_after_documents": "canonical_bytes_exact_match",
        },
        "permanent_authority_claimed": False,
    }


def _canonical(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


_COMMAND_FAILURES = (
    AttributeError,
    BodySwayDynamicSeamProbeError,
    KeyError,
    OSError,
    OverflowError,
    RecursionError,
    RuntimeError,
    TypeError,
    UnicodeError,
    ValueError,
)
