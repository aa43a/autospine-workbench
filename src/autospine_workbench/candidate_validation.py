"""Dependency-free semantic validation before candidate artifact publication."""

from __future__ import annotations

from dataclasses import dataclass
import math
import re
from typing import Any, Mapping

from .resolved_project import canonical_sha256


_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_METHODS = frozenset({"audit_bbox_heuristic", "pose", "medial_axis", "contact", "fusion"})
_FORBIDDEN_SCORE_FIELDS = frozenset({"confidence", "probability", "model_confidence"})
_OBSERVABILITY = frozenset({"visible", "occluded", "merged", "absent", "ambiguous"})
_EVIDENCE_KINDS = frozenset(
    {"audit_source", "layer_alpha", "pose_heatmap", "contact_geometry", "kinematic_residual"}
)


@dataclass(frozen=True, slots=True)
class CandidateValidationIssue:
    path: str
    code: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {"path": self.path, "code": self.code, "message": self.message}


class CandidateValidationError(ValueError):
    def __init__(self, issues: list[CandidateValidationIssue]):
        self.issues = tuple(issues)
        super().__init__("; ".join(f"{item.path}: {item.message}" for item in issues))


def require_valid_candidate_document(
    document: Any,
    *,
    joint_ids: set[str],
    layer_ids: set[str],
    canvas_width: int,
    canvas_height: int,
) -> None:
    issues = validate_candidate_document(
        document,
        joint_ids=joint_ids,
        layer_ids=layer_ids,
        canvas_width=canvas_width,
        canvas_height=canvas_height,
    )
    if issues:
        raise CandidateValidationError(issues)


def validate_candidate_document(
    document: Any,
    *,
    joint_ids: set[str],
    layer_ids: set[str],
    canvas_width: int,
    canvas_height: int,
) -> list[CandidateValidationIssue]:
    issues: list[CandidateValidationIssue] = []
    if not isinstance(document, Mapping):
        return [_issue("$", "type", "candidate document must be an object")]
    if document.get("format") != "autospine-joint-candidates" or document.get("format_version") != 1:
        issues.append(_issue("$", "version", "unsupported candidate document format"))
    project_id = document.get("project_id")
    if not isinstance(project_id, str) or not _SAFE_ID.fullmatch(project_id):
        issues.append(_issue("$.project_id", "id", "project id is invalid"))
    source = document.get("source")
    input_sha = _validate_source(source, issues)
    analysis = document.get("analysis")
    run_sha = None
    if not isinstance(analysis, Mapping):
        issues.append(_issue("$.analysis", "type", "analysis must be an object"))
    else:
        for field in ("config_sha256", "run_sha256"):
            if not isinstance(analysis.get(field), str) or not _SHA256.fullmatch(analysis[field]):
                issues.append(_issue(f"$.analysis.{field}", "hash", "must be a SHA-256"))
        provider = analysis.get("provider")
        version = analysis.get("provider_version")
        if not isinstance(provider, str) or not _SAFE_ID.fullmatch(provider):
            issues.append(_issue("$.analysis.provider", "id", "provider id is invalid"))
        if not isinstance(version, str) or not 1 <= len(version) <= 64:
            issues.append(_issue("$.analysis.provider_version", "version", "provider version is invalid"))
        if input_sha and isinstance(provider, str) and isinstance(version, str):
            run_sha = analysis.get("run_sha256")
            expected = canonical_sha256(
                {
                    "input_sha256": input_sha,
                    "provider": provider,
                    "provider_version": version,
                    "config_sha256": analysis.get("config_sha256"),
                }
            )
            if run_sha != expected:
                issues.append(_issue("$.analysis.run_sha256", "identity", "run identity is inconsistent"))
    _validate_coordinate_system(document.get("coordinate_system"), issues)
    raw_joints = document.get("joints")
    if not isinstance(raw_joints, Mapping):
        issues.append(_issue("$.joints", "type", "joints must be an object"))
        return issues
    actual_ids = {key for key in raw_joints if isinstance(key, str)}
    for joint_id in sorted(actual_ids - joint_ids):
        issues.append(_issue(f"$.joints.{joint_id}", "unknown_joint", "joint is not in project"))
    for joint_id in sorted(joint_ids - actual_ids):
        issues.append(_issue(f"$.joints.{joint_id}", "missing_joint", "project joint is missing"))
    seen_candidates: set[str] = set()
    for joint_id, evidence in raw_joints.items():
        if not isinstance(joint_id, str) or not isinstance(evidence, Mapping):
            issues.append(_issue("$.joints", "type", "joint evidence must be keyed objects"))
            continue
        if evidence.get("observability") not in _OBSERVABILITY:
            issues.append(
                _issue(f"$.joints.{joint_id}.observability", "enum", "observability is unsupported")
            )
        candidates = evidence.get("candidates")
        if not isinstance(candidates, list):
            issues.append(_issue(f"$.joints.{joint_id}.candidates", "type", "must be an array"))
            continue
        for index, candidate in enumerate(candidates):
            path = f"$.joints.{joint_id}.candidates[{index}]"
            _validate_candidate(
                candidate,
                path,
                layer_ids,
                canvas_width,
                canvas_height,
                seen_candidates,
                issues,
                run_sha,
            )
    _validate_qa(document.get("qa"), issues)
    return issues


def _validate_candidate(
    candidate: Any,
    path: str,
    layer_ids: set[str],
    width: int,
    height: int,
    seen: set[str],
    issues: list[CandidateValidationIssue],
    run_sha: Any,
) -> None:
    if not isinstance(candidate, Mapping):
        issues.append(_issue(path, "type", "candidate must be an object"))
        return
    candidate_id = candidate.get("candidate_id")
    if not isinstance(candidate_id, str) or not _SAFE_ID.fullmatch(candidate_id):
        issues.append(_issue(f"{path}.candidate_id", "id", "candidate id is invalid"))
    elif candidate_id in seen:
        issues.append(_issue(f"{path}.candidate_id", "duplicate", "candidate id is duplicated"))
    else:
        seen.add(candidate_id)
        if isinstance(run_sha, str) and run_sha[:12] not in candidate_id:
            issues.append(_issue(f"{path}.candidate_id", "identity", "candidate id is not bound to the run"))
    xy = candidate.get("xy")
    if not isinstance(xy, list) or len(xy) != 2 or not all(_finite(value) for value in xy):
        issues.append(_issue(f"{path}.xy", "coordinate", "xy must contain finite numbers"))
    elif not 0 <= float(xy[0]) <= width or not 0 <= float(xy[1]) <= height:
        issues.append(_issue(f"{path}.xy", "bounds", "xy lies outside the canvas"))
    if candidate.get("method") not in _METHODS:
        issues.append(_issue(f"{path}.method", "enum", "candidate method is unsupported"))
    score = candidate.get("heuristic_score")
    if candidate.get("score_kind") != "heuristic" or not _finite(score) or not 0 <= float(score) <= 1:
        issues.append(_issue(f"{path}.heuristic_score", "score", "score must be a finite heuristic"))
    for forbidden in sorted(_FORBIDDEN_SCORE_FIELDS & set(candidate)):
        issues.append(_issue(f"{path}.{forbidden}", "forbidden", "calibrated score is not supported"))
    sources = candidate.get("source_layer_ids")
    if not isinstance(sources, list):
        issues.append(_issue(f"{path}.source_layer_ids", "type", "must be an array"))
    else:
        if len(sources) != len(set(item for item in sources if isinstance(item, str))):
            issues.append(_issue(f"{path}.source_layer_ids", "duplicate", "layer ids must be unique"))
        for layer_id in sources:
            if layer_id not in layer_ids:
                issues.append(_issue(f"{path}.source_layer_ids", "unknown_layer", "layer is not in project"))
    radius = candidate.get("error_radius_px")
    if radius is not None and (not _finite(radius) or float(radius) < 0):
        issues.append(_issue(f"{path}.error_radius_px", "bounds", "error radius must be non-negative"))
    _validate_evidence(candidate.get("evidence"), f"{path}.evidence", issues)
    flags = candidate.get("qa_flags")
    if not isinstance(flags, list) or any(not isinstance(item, str) or not item for item in flags):
        issues.append(_issue(f"{path}.qa_flags", "type", "qa flags must be non-empty strings"))
    elif len(flags) != len(set(flags)):
        issues.append(_issue(f"{path}.qa_flags", "duplicate", "qa flags must be unique"))


def _validate_source(value: Any, issues: list[CandidateValidationIssue]) -> str | None:
    if not isinstance(value, Mapping):
        issues.append(_issue("$.source", "type", "source must be an object"))
        return None
    for field in ("base_project_sha256", "source_image_sha256"):
        item = value.get(field)
        if not isinstance(item, str) or not _SHA256.fullmatch(item):
            issues.append(_issue(f"$.source.{field}", "hash", "must be a SHA-256"))
    return value.get("base_project_sha256") if isinstance(value.get("base_project_sha256"), str) else None


def _validate_coordinate_system(value: Any, issues: list[CandidateValidationIssue]) -> None:
    expected = {
        "origin": "top_left",
        "x_axis": "right",
        "y_axis": "down",
        "units": "pixel",
        "side_naming": "character_side",
    }
    if not isinstance(value, Mapping) or any(value.get(key) != item for key, item in expected.items()):
        issues.append(_issue("$.coordinate_system", "coordinate_system", "coordinate system is unsupported"))


def _validate_evidence(value: Any, path: str, issues: list[CandidateValidationIssue]) -> None:
    if not isinstance(value, list):
        issues.append(_issue(path, "type", "evidence must be an array"))
        return
    for index, item in enumerate(value):
        item_path = f"{path}[{index}]"
        if not isinstance(item, Mapping):
            issues.append(_issue(item_path, "type", "evidence item must be an object"))
            continue
        if item.get("kind") not in _EVIDENCE_KINDS:
            issues.append(_issue(f"{item_path}.kind", "enum", "evidence kind is unsupported"))
        note = item.get("note")
        if not isinstance(note, str) or not note or len(note) > 512:
            issues.append(_issue(f"{item_path}.note", "length", "evidence note is invalid"))
        source_ref = item.get("source_ref")
        if source_ref is not None and (
            not isinstance(source_ref, str) or not source_ref or len(source_ref) > 256
        ):
            issues.append(_issue(f"{item_path}.source_ref", "length", "source reference is invalid"))


def _validate_qa(value: Any, issues: list[CandidateValidationIssue]) -> None:
    if not isinstance(value, Mapping) or value.get("status") not in {"passed", "manual_required", "rejected"}:
        issues.append(_issue("$.qa.status", "enum", "QA status is unsupported"))
        return
    flags = value.get("flags")
    if not isinstance(flags, list) or any(not isinstance(item, str) or not item for item in flags):
        issues.append(_issue("$.qa.flags", "type", "QA flags must be non-empty strings"))
    elif len(flags) != len(set(flags)):
        issues.append(_issue("$.qa.flags", "duplicate", "QA flags must be unique"))


def _finite(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _issue(path: str, code: str, message: str) -> CandidateValidationIssue:
    return CandidateValidationIssue(path, code, message)
