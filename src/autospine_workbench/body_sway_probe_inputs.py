"""Exact in-memory admission for one reviewed body-sway structural probe."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
import json
from typing import Any

from .idle_behavior_candidates import (
    IdleBehaviorCandidateError,
    compile_idle_behavior_candidates,
)
from .idle_behavior_candidate_validation import (
    IdleBehaviorCandidateValidationError,
    require_idle_behavior_candidates,
)
from .idle_behavior_decision_validation import (
    IdleBehaviorDecisionValidationError,
    idle_behavior_decision_sha256,
    require_idle_behavior_decision,
)
from .idle_behavior_inputs import (
    IdleBehaviorInputError,
    require_idle_behavior_inputs,
)
from .mesh_bundle_integrity import VerifiedMeshBundle
from .motion_retarget_bundle_integrity import VerifiedMotionRetargetBundle
from .reviewed_motion_bundle_contract import ReviewedMotionBundleContract


class BodySwayProbeInputError(ValueError):
    """Raised when probe inputs are stale, cross-wired, or not probeable."""


@dataclass(frozen=True, slots=True)
class BodySwayProbeInputs:
    """Frozen detached snapshots admitted for numeric/structural probing."""

    project_id: str
    clip_id: str
    _documents: tuple[tuple[str, str], ...] = field(repr=False)
    _source_json: str = field(repr=False)

    def _document(self, name: str) -> dict[str, Any]:
        return json.loads(dict(self._documents)[name])

    @property
    def manifest(self) -> dict[str, Any]:
        return self._document("layer-manifest")

    @property
    def rig(self) -> dict[str, Any]:
        return self._document("p3-rig")

    @property
    def target_profile(self) -> dict[str, Any]:
        return self._document("p5-target-profile")

    @property
    def motion_instance_v2(self) -> dict[str, Any]:
        return self._document("p9-motion-instance-v2")

    @property
    def candidates(self) -> dict[str, Any]:
        return self._document("idle-behavior-candidates")

    @property
    def decision(self) -> dict[str, Any]:
        return self._document("idle-behavior-decision")

    @property
    def timing(self) -> dict[str, Any]:
        return dict(self.motion_instance_v2["timing"])

    @property
    def selection(self) -> dict[str, Any]:
        row = self.decision["decisions"][0]
        return {
            "candidate_id": row["candidate_id"],
            "feature_id": row["feature_id"],
            "action": row["action"],
            "probe_status": row["probe_status"],
            "parameters": row["payload"],
        }

    @property
    def source(self) -> dict[str, Any]:
        return json.loads(self._source_json)


def require_body_sway_probe_inputs(
    layer_manifest: Mapping[str, Any],
    candidates: Mapping[str, Any],
    decision: Mapping[str, Any],
    mesh_bundle: VerifiedMeshBundle,
    retarget_bundle: VerifiedMotionRetargetBundle,
    reviewed_bundle: ReviewedMotionBundleContract,
) -> BodySwayProbeInputs:
    """Replay P3/P5/P9/P10 values and admit one pending human adjustment."""

    try:
        upstream = require_idle_behavior_inputs(
            layer_manifest, mesh_bundle, retarget_bundle, reviewed_bundle
        )
        candidate_document, candidate_bytes = _snapshot(candidates)
        require_idle_behavior_candidates(candidate_document)
        rebuilt = compile_idle_behavior_candidates(
            upstream.manifest, mesh_bundle, retarget_bundle, reviewed_bundle
        )
        if candidate_document != rebuilt.document \
                or candidate_bytes != rebuilt.canonical_bytes:
            raise BodySwayProbeInputError(
                "Idle behavior candidates differ from exact P3/P5/P9 replay"
            )
        decision_document, decision_bytes = _snapshot(decision)
        require_idle_behavior_decision(
            decision_document, candidates=rebuilt.document
        )
        selection = _require_selection(rebuilt.document, decision_document)
        source = {
            **upstream.source,
            "idle_behavior_candidates_sha256": rebuilt.sha256,
            "idle_behavior_decision_sha256":
                idle_behavior_decision_sha256(decision_document),
        }
        documents = (
            ("layer-manifest", _canonical(upstream.manifest)),
            ("p3-rig", _canonical(upstream.rig)),
            ("p5-target-profile", _canonical(upstream.target_profile)),
            ("p9-motion-instance-v2", _canonical(upstream.motion_instance_v2)),
            ("idle-behavior-candidates", candidate_bytes.decode("utf-8")),
            ("idle-behavior-decision", decision_bytes.decode("utf-8")),
        )
        value = BodySwayProbeInputs(
            project_id=upstream.project_id,
            clip_id=upstream.clip_id,
            _documents=documents,
            _source_json=_canonical(source),
        )
        if value.selection != selection:
            raise BodySwayProbeInputError(
                "Body-sway selection snapshot is inconsistent"
            )
        return value
    except BodySwayProbeInputError:
        raise
    except (
        IdleBehaviorCandidateError,
        IdleBehaviorCandidateValidationError,
        IdleBehaviorDecisionValidationError,
        IdleBehaviorInputError,
        AttributeError,
        KeyError,
        OverflowError,
        RecursionError,
        TypeError,
        UnicodeError,
        ValueError,
    ) as exc:
        raise BodySwayProbeInputError(
            f"Body-sway probe input admission failed: {exc}"
        ) from exc


def _require_selection(candidates, decision) -> dict[str, Any]:
    candidate_rows = [
        row for row in candidates["features"]
        if row["availability"] == "candidate"
    ]
    decision_rows = decision["decisions"]
    if len(candidate_rows) != 1 or len(decision_rows) != 1:
        raise BodySwayProbeInputError(
            "Body-sway probe requires exactly one candidate and decision"
        )
    candidate, selection = candidate_rows[0], decision_rows[0]
    if candidate["feature_id"] != "body_sway" \
            or selection["feature_id"] != "body_sway" \
            or selection["candidate_id"] != candidate["candidate_id"] \
            or selection["action"] != "adjust" \
            or selection["probe_status"] != "pending_probe" \
            or not isinstance(selection.get("payload"), Mapping):
        raise BodySwayProbeInputError(
            "Body-sway probe requires one adjusted pending_probe selection"
        )
    return json.loads(_canonical({
        "candidate_id": selection["candidate_id"],
        "feature_id": selection["feature_id"],
        "action": selection["action"],
        "probe_status": selection["probe_status"],
        "parameters": selection["payload"],
    }))


def _snapshot(value: Any) -> tuple[dict[str, Any], bytes]:
    encoded = _canonical(value).encode("utf-8")
    document = json.loads(encoded)
    if not isinstance(document, dict):
        raise BodySwayProbeInputError("Probe documents must be JSON objects")
    return document, encoded


def _canonical(value: Any) -> str:
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    )
