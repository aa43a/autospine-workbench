"""Pure, zero-write Python admission for the local P9 review UI."""

from __future__ import annotations

from collections.abc import Mapping
import re
from typing import Any

from .depth_order_candidate_validation import (
    FORMAT as DEPTH_FORMAT,
    depth_order_candidates_sha256,
    require_depth_order_candidates,
)
from .depth_pair_policy import (
    depth_pair_policy_sha256,
    require_depth_pair_policy,
)
from .foot_lock_candidate_validation import (
    FORMAT as FOOT_FORMAT,
    foot_lock_candidates_sha256,
    require_foot_lock_candidates,
)
from .motion_policy_candidate_inventory import (
    derive_motion_policy_candidates,
)
from .http_json_request import decode_json_object
from .exact_json_contract import exact_json_equal


REQUEST_FORMAT = "autospine-motion-policy-preflight-request"
RESULT_FORMAT = "autospine-motion-policy-preflight-result"
FORMAT_VERSION = 1
POLICY_IDENTITY = "policy_identity"
CANDIDATE_INVENTORY = "candidate_inventory"
_SHA = re.compile(r"^[0-9a-f]{64}$")
_BASE_FIELDS = {"format", "format_version", "operation"}
_IDENTITY_FIELDS = {
    "policy_sha256", "foot_candidates_sha256",
    "depth_candidates_sha256",
}
MAX_POLICY_JSON_BYTES = 1024 * 1024
MAX_CANDIDATE_JSON_BYTES = 16 * 1024 * 1024
_ENVELOPE_FIELDS = {
    "input_bundle_paths", "report_sha256", "report", "ok", "status",
}


class MotionPolicyPreflightError(ValueError):
    """Raised when supplied review evidence is incomplete or cross-wired."""


def compile_motion_policy_preflight(
    request: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate in memory and return only bounded identities/inventory seals."""

    try:
        root = _object(request, "Motion-policy preflight request")
        if root.get("format") != REQUEST_FORMAT \
                or type(root.get("format_version")) is not int \
                or root.get("format_version") != FORMAT_VERSION:
            raise MotionPolicyPreflightError(
                "Motion-policy preflight request format is unsupported"
            )
        operation = root.get("operation")
        if operation == POLICY_IDENTITY:
            _exact(root, _BASE_FIELDS | {"policy_json"})
            return _policy_identity(_inner_json(
                root.get("policy_json"), MAX_POLICY_JSON_BYTES, "policy_json"
            ))
        if operation == CANDIDATE_INVENTORY:
            _exact(root, _BASE_FIELDS | {
                "policy_json", "foot_candidates_json",
                "depth_candidates_json", "declared",
            })
            return _candidate_inventory(
                _inner_json(
                    root.get("policy_json"), MAX_POLICY_JSON_BYTES,
                    "policy_json",
                ),
                _candidate_json(root.get("foot_candidates_json"), "foot"),
                _candidate_json(root.get("depth_candidates_json"), "depth"),
                _object(root.get("declared"), "declared"),
            )
        raise MotionPolicyPreflightError(
            "Motion-policy preflight operation is unsupported"
        )
    except MotionPolicyPreflightError:
        raise
    except (KeyError, OverflowError, TypeError, ValueError) as exc:
        raise MotionPolicyPreflightError(
            f"Motion-policy preflight failed: {exc}"
        ) from exc


def _policy_identity(policy: Mapping[str, Any]) -> dict[str, Any]:
    require_depth_pair_policy(policy)
    policy_sha = depth_pair_policy_sha256(policy)
    return _result(
        POLICY_IDENTITY, policy,
        identities={"policy_sha256": policy_sha},
    )


def _candidate_inventory(policy, foot_value, depth_value, declared):
    _exact(declared, _IDENTITY_FIELDS)
    for field in _IDENTITY_FIELDS:
        _sha(declared.get(field), field)
    foot, foot_envelope_sha = foot_value
    depth, depth_envelope_sha = depth_value
    require_depth_pair_policy(policy)
    require_foot_lock_candidates(foot)
    require_depth_order_candidates(depth)
    identities = {
        "policy_sha256": depth_pair_policy_sha256(policy),
        "foot_candidates_sha256": foot_lock_candidates_sha256(foot),
        "depth_candidates_sha256": depth_order_candidates_sha256(depth),
    }
    if declared != identities:
        raise MotionPolicyPreflightError(
            "Declared motion-policy identities differ from canonical content"
        )
    if foot_envelope_sha not in {None, identities["foot_candidates_sha256"]} \
            or depth_envelope_sha not in {
                None, identities["depth_candidates_sha256"],
            }:
        raise MotionPolicyPreflightError(
            "CLI envelope identity differs from canonical report content"
        )
    inventory = derive_motion_policy_candidates(foot, depth)
    _cross_policy_depth(policy, depth, identities["policy_sha256"])
    foot_count = sum(
        candidate.kind == "foot_lock" for candidate in inventory.candidates
    )
    depth_count = sum(
        candidate.kind == "depth_order" for candidate in inventory.candidates
    )
    return _result(
        CANDIDATE_INVENTORY, policy, identities=identities,
        inventory={
            "total_count": len(inventory.candidates),
            "foot_count": foot_count,
            "depth_count": depth_count,
            "unconstrained_count": len(inventory.unconstrained_foot_ticks),
            "candidate_ids_sha256": inventory.candidate_ids_sha256,
        },
    )


def _cross_policy_depth(policy, depth, policy_sha: str) -> None:
    source = depth.get("source")
    if not isinstance(source, Mapping) \
            or policy.get("project_id") != depth.get("project_id") \
            or policy.get("clip_id") != depth.get("clip_id") \
            or source.get("depth_pair_policy_sha256") != policy_sha \
            or not exact_json_equal(policy.get("source"), {
                stage: source.get(stage) for stage in ("p8", "p5", "p3")
            }) \
            or not exact_json_equal(
                policy.get("hysteresis"), depth.get("hysteresis")
            ) \
            or not exact_json_equal(
                policy.get("pairs"), _depth_policy_pairs(depth.get("pairs"))
            ):
        raise MotionPolicyPreflightError(
            "Depth candidates differ from the reviewed depth-pair policy"
        )


def _depth_policy_pairs(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise MotionPolicyPreflightError("Depth candidate pairs are invalid")
    return [{
        "pair_id": row["pair_id"],
        "slots": row["slots"],
        "setup_front_slot": row["setup_front_slot"],
    } for row in value]


def _candidate_json(value: Any, kind: str):
    raw = _inner_json(
        value, MAX_CANDIDATE_JSON_BYTES, f"{kind}_candidates_json"
    )
    expected = FOOT_FORMAT if kind == "foot" else DEPTH_FORMAT
    if raw.get("format") == expected:
        return raw, None
    _exact(raw, _ENVELOPE_FIELDS)
    if raw.get("ok") is not True or raw.get("status") != "passed" \
            or not isinstance(raw.get("input_bundle_paths"), list) \
            or any(not isinstance(path, str)
                   for path in raw["input_bundle_paths"]):
        raise MotionPolicyPreflightError("Candidate CLI envelope is invalid")
    report = _object(raw.get("report"), "candidate report")
    if report.get("format") != expected:
        raise MotionPolicyPreflightError("Candidate report format is invalid")
    envelope_sha = raw.get("report_sha256")
    _sha(envelope_sha, "CLI envelope report_sha256")
    return report, envelope_sha


def _inner_json(value: Any, maximum: int, label: str) -> dict[str, Any]:
    if not isinstance(value, str):
        raise MotionPolicyPreflightError(f"{label} must be a JSON string")
    encoded = value.encode("utf-8")
    if len(encoded) > maximum:
        raise MotionPolicyPreflightError(f"{label} exceeds its byte limit")
    return decode_json_object(encoded)


def _result(operation, policy, *, identities, inventory=None):
    result = {
        "format": RESULT_FORMAT,
        "format_version": FORMAT_VERSION,
        "status": "passed",
        "operation": operation,
        "project_id": policy["project_id"],
        "clip_id": policy["clip_id"],
        "identities": identities,
    }
    if inventory is not None:
        result["inventory"] = inventory
    return result


def _object(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise MotionPolicyPreflightError(f"{label} must be an object")
    return value


def _exact(value: Mapping[str, Any], expected: set[str]) -> None:
    if set(value) != expected:
        raise MotionPolicyPreflightError(
            "Motion-policy preflight fields are unsupported"
        )


def _sha(value: Any, label: str) -> None:
    if not isinstance(value, str) or not _SHA.fullmatch(value):
        raise MotionPolicyPreflightError(f"{label} is not a SHA-256")
