"""Dependency-free semantic validation before candidate artifact publication."""

from __future__ import annotations

from dataclasses import dataclass
import math
import re
from typing import Any, Mapping


_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_METHODS = frozenset({"audit_bbox_heuristic", "pose", "medial_axis", "contact", "fusion"})
_FORBIDDEN_SCORE_FIELDS = frozenset({"confidence", "probability", "model_confidence"})


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
    analysis = document.get("analysis")
    if not isinstance(analysis, Mapping):
        issues.append(_issue("$.analysis", "type", "analysis must be an object"))
    else:
        for field in ("config_sha256", "run_sha256"):
            if not isinstance(analysis.get(field), str) or not _SHA256.fullmatch(analysis[field]):
                issues.append(_issue(f"$.analysis.{field}", "hash", "must be a SHA-256"))
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
            )
    return issues


def _validate_candidate(
    candidate: Any,
    path: str,
    layer_ids: set[str],
    width: int,
    height: int,
    seen: set[str],
    issues: list[CandidateValidationIssue],
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
        for layer_id in sources:
            if layer_id not in layer_ids:
                issues.append(_issue(f"{path}.source_layer_ids", "unknown_layer", "layer is not in project"))


def _finite(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _issue(path: str, code: str, message: str) -> CandidateValidationIssue:
    return CandidateValidationIssue(path, code, message)
