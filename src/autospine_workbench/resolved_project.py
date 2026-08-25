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
                layer["reviewed_fields"] = []
                continue
            reviewed_fields: list[str] = []
            for field in (
                "canonical_role",
                "side",
                "disposition",
                "visible",
                "pivot_xy",
                "candidate_bone",
                "notes",
            ):
                if field in patch and patch[field] is not None:
                    layer[field] = deepcopy(patch[field])
                    reviewed_fields.append(field)
            layer["review_state"] = "manual_adjusted"
            layer["reviewed_fields"] = reviewed_fields
            layer["decision_revision"] = revision

        joint_overrides = decision.get("joint_overrides") or {}
        joint_decisions = decision.get("joint_decisions") or {}
        for joint in joints:
            joint["model_confidence"] = joint.get("confidence")
            candidate_decision = joint_decisions.get(joint.get("id"))
            if isinstance(candidate_decision, Mapping):
                self._apply_candidate_decision(joint, candidate_decision, revision)
                continue
            patch = joint_overrides.get(joint.get("id"))
            if not isinstance(patch, Mapping):
                joint["review_state"] = "unreviewed"
                continue
            joint["x"] = patch["x"]
            joint["y"] = patch["y"]
            joint["review_state"] = "manual_adjusted"
            joint["decision_kind"] = "manual_absolute"
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
        requires_review = bool((skeleton.get("generation") or {}).get("requires_review"))
        unresolved_joint_ids = []
        for joint in joints:
            review_state = joint.get("review_state")
            unresolved = review_state == "candidate_rejected" or (
                review_state == "unreviewed"
                and (requires_review or _confidence(joint.get("model_confidence")) < 0.5)
            )
            if unresolved:
                unresolved_joint_ids.append(str(joint.get("id")))
        unobservable_joint_ids = [
            str(joint.get("id"))
            for joint in joints
            if joint.get("review_state") == "unobservable"
        ]
        rejected_joint_ids = [
            str(joint.get("id"))
            for joint in joints
            if joint.get("review_state") == "candidate_rejected"
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
            "candidate_analyses": _candidate_analyses(joint_decisions),
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
                "rejected_joint_ids": rejected_joint_ids,
                "unobservable_joint_ids": unobservable_joint_ids,
            },
        }
        snapshot["sha256"] = canonical_sha256(snapshot)
        return snapshot

    @staticmethod
    def _apply_candidate_decision(
        joint: dict[str, Any], patch: Mapping[str, Any], revision: Any
    ) -> None:
        action = patch.get("action")
        if action in {"accept", "adjust"}:
            final_xy = patch.get("final_xy") or []
            joint["x"], joint["y"] = final_xy
            joint["review_state"] = (
                "candidate_accepted" if action == "accept" else "manual_adjusted"
            )
        elif action == "reject":
            joint["review_state"] = "candidate_rejected"
        elif action == "unobservable":
            joint["review_state"] = "unobservable"
        joint["decision_kind"] = f"candidate_{action}"
        joint["decision_revision"] = revision
        joint["decision"] = deepcopy(dict(patch))


def _candidate_analyses(decisions: Mapping[str, Any]) -> list[dict[str, Any]]:
    by_artifact: dict[str, dict[str, Any]] = {}
    for value in decisions.values():
        if not isinstance(value, Mapping):
            continue
        digest = value.get("candidate_artifact_sha256")
        analysis = value.get("analysis")
        if isinstance(digest, str) and isinstance(analysis, Mapping):
            by_artifact[digest] = {
                "candidate_artifact_sha256": digest,
                **deepcopy(dict(analysis)),
            }
    return [by_artifact[key] for key in sorted(by_artifact)]


def _confidence(value: Any) -> float:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return 0.0
