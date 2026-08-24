"""Materialize the effective authoring state from immutable inputs and decisions."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from typing import Any, Mapping


RESOLVED_SCHEMA_VERSION = "autospine.resolved-project/v1"


def canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class ResolvedProjectBuilder:
    """Apply a pinned override revision without mutating model evidence."""

    def build(
        self,
        project: Mapping[str, Any],
        overrides: Mapping[str, Any] | None = None,
        *,
        analysis_sha256: str | None = None,
    ) -> dict[str, Any]:
        decision = deepcopy(dict(overrides or project.get("overrides") or {}))
        layers = deepcopy(list(project.get("layers") or []))
        skeleton = deepcopy(dict(project.get("skeleton") or {}))
        joints = list(skeleton.get("joints") or [])
        revision = decision.get("revision", 0)

        layer_overrides = decision.get("layer_overrides") or {}
        for layer in layers:
            patch = layer_overrides.get(layer.get("id"))
            if not isinstance(patch, Mapping):
                layer["review_state"] = "unreviewed"
                continue
            for field in (
                "canonical_role",
                "side",
                "disposition",
                "visible",
                "pivot_xy",
                "notes",
            ):
                if field in patch and patch[field] is not None:
                    layer[field] = deepcopy(patch[field])
            layer["review_state"] = "manual_adjusted"
            layer["decision_revision"] = revision

        joint_overrides = decision.get("joint_overrides") or {}
        for joint in joints:
            joint["model_confidence"] = joint.get("confidence")
            patch = joint_overrides.get(joint.get("id"))
            if not isinstance(patch, Mapping):
                joint["review_state"] = "unreviewed"
                continue
            joint["x"] = patch["x"]
            joint["y"] = patch["y"]
            joint["review_state"] = "manual_adjusted"
            joint["decision_revision"] = revision
            if patch.get("reason"):
                joint["review_reason"] = patch["reason"]
            # Override v1 allowed this field. Keep it as historical decision
            # metadata; never replace the immutable model confidence with it.
            if "confidence" in patch:
                joint["legacy_review_confidence"] = patch["confidence"]

        review_layer_ids = [
            str(layer.get("id"))
            for layer in layers
            if layer.get("disposition") == "review"
            or (layer.get("empty") and layer.get("disposition") != "exclude")
        ]
        unresolved_joint_ids = [
            str(joint.get("id"))
            for joint in joints
            if _confidence(joint.get("model_confidence")) < 0.5
            and joint.get("review_state") == "unreviewed"
        ]
        qa_status = "ready" if not review_layer_ids and not unresolved_joint_ids else "needs_review"

        base_payload = {
            "source": project.get("source"),
            "canvas": project.get("canvas"),
            "layers": project.get("layers"),
            "skeleton": project.get("skeleton"),
        }
        inputs = {
            "base_project_sha256": canonical_sha256(base_payload),
            "override_sha256": canonical_sha256(decision),
        }
        if analysis_sha256 is not None:
            inputs["analysis_sha256"] = analysis_sha256

        snapshot: dict[str, Any] = {
            "schema_version": RESOLVED_SCHEMA_VERSION,
            "project_id": project.get("id"),
            "revision": revision,
            "inputs": inputs,
            "canvas": deepcopy(project.get("canvas")),
            "layers": layers,
            "skeleton": skeleton,
            "qa": {
                "status": qa_status,
                "review_layer_ids": review_layer_ids,
                "unresolved_joint_ids": unresolved_joint_ids,
            },
        }
        snapshot["sha256"] = canonical_sha256(snapshot)
        return snapshot


def _confidence(value: Any) -> float:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return 0.0
