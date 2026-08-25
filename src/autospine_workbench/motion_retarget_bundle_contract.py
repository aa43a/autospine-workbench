"""Pure immutable five-document contract for one P5 retarget result."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
import hashlib
import json
from typing import Any

from .manifest_artifacts import LayerManifestError, require_safe_token
from .motion_instance_validation import (
    MotionInstanceValidationError,
    instance_sha256,
    require_motion_instance,
)
from .motion_mesh_regression_validation import (
    MAX_REPORT_BYTES as MAX_MESH_REPORT_BYTES,
    MotionMeshRegressionShapeError,
    require_motion_mesh_regression_shape,
)
from .motion_retarget_report_validation import (
    MAX_REPORT_BYTES as MAX_RETARGET_REPORT_BYTES,
    MotionRetargetReportShapeError,
    require_motion_retarget_report_shape,
)
from .motion_retarget_run import (
    MAX_RUN_BYTES,
    RetargetRunValidationError,
    require_retarget_run,
    retarget_run_document_sha256,
)
from .motion_target_validation import (
    MotionTargetValidationError,
    require_motion_target_profile,
)


BUNDLE_ADDRESS_DOMAIN = b"autospine-motion-retarget-bundle-address/v1"
DOCUMENT_NAMES = (
    "target-profile.json", "instance.json", "run-manifest.json",
    "retarget-report.json", "mesh-regression.json",
)
MAX_TARGET_PROFILE_BYTES = 8 * 1024 * 1024
MAX_INSTANCE_BYTES = 16 * 1024 * 1024
_LIMITS = (
    MAX_TARGET_PROFILE_BYTES, MAX_INSTANCE_BYTES, MAX_RUN_BYTES,
    MAX_RETARGET_REPORT_BYTES, MAX_MESH_REPORT_BYTES,
)
MAX_TOTAL_DOCUMENT_BYTES = sum(_LIMITS)
_MOTION_FIELDS = (
    "motion_ir_sha256", "motion_bundle_sha256", "motion_run_sha256",
)


class MotionRetargetBundleContractError(ValueError):
    """Raised when retarget documents are unsafe, stale, or cross-wired."""


@dataclass(frozen=True, slots=True)
class MotionRetargetBundleContract:
    """Frozen canonical bytes and exact domain-separated retarget address."""

    project_id: str
    clip_id: str
    target_profile_sha256: str
    instance_sha256: str
    report_sha256: str
    mesh_report_sha256: str
    run_document_sha256: str
    bundle_sha256: str
    _documents: tuple[tuple[str, bytes], ...] = field(repr=False)

    @property
    def document_bytes(self) -> dict[str, bytes]:
        return dict(self._documents)

    @property
    def inventory(self) -> tuple[str, ...]:
        return tuple(name for name, _data in self._documents)


def build_motion_retarget_bundle_contract(
    project_id: str,
    target_profile: Mapping[str, Any],
    instance: Mapping[str, Any],
    run_manifest: Mapping[str, Any],
    retarget_report: Mapping[str, Any],
    mesh_regression: Mapping[str, Any],
) -> MotionRetargetBundleContract:
    """Validate, cross-bind, canonicalize, and address one retarget result."""

    try:
        project = require_safe_token(project_id, "Project id")
        require_motion_target_profile(target_profile)
        require_motion_instance(instance, target_profile=target_profile)
        require_retarget_run(run_manifest, instance=instance)
        require_motion_retarget_report_shape(retarget_report)
        require_motion_mesh_regression_shape(mesh_regression)
        if mesh_regression.get("status") != "passed":
            raise MotionRetargetBundleContractError(
                "Rejected mesh regression cannot enter a published bundle"
            )
        values = (
            target_profile, instance, run_manifest,
            retarget_report, mesh_regression,
        )
        items = tuple(
            (name, _document(value, name, _LIMITS[index]))
            for index, (name, value) in enumerate(zip(DOCUMENT_NAMES, values))
        )
        _require_items(items)
        digests = tuple(_sha(data) for _name, data in items)
        profile_sha, instance_sha, run_sha, report_sha, mesh_sha = digests
        _cross_bind(
            project, profile_sha, instance_sha, run_sha,
            target_profile, instance, run_manifest,
            retarget_report, mesh_regression,
        )
        clip = str(instance["clip_id"])
        return MotionRetargetBundleContract(
            project, clip, profile_sha, instance_sha, report_sha, mesh_sha,
            run_sha, retarget_bundle_address_sha256(project, clip, items), items,
        )
    except MotionRetargetBundleContractError:
        raise
    except (
        LayerManifestError,
        MotionInstanceValidationError,
        MotionMeshRegressionShapeError,
        MotionRetargetReportShapeError,
        MotionTargetValidationError,
        RetargetRunValidationError,
        KeyError,
        OverflowError,
        TypeError,
        ValueError,
    ) as exc:
        raise MotionRetargetBundleContractError(
            f"Motion retarget bundle contract failed: {exc}"
        ) from exc


def retarget_bundle_address_sha256(
    project_id: str,
    clip_id: str,
    document_items: tuple[tuple[str, bytes], ...],
) -> str:
    """Hash exact ordered canonical documents with explicit project/clip scope."""

    try:
        project = require_safe_token(project_id, "Project id")
        clip = require_safe_token(clip_id, "Clip id")
        items = _require_items(document_items)
        digest = hashlib.sha256()
        _feed(digest, BUNDLE_ADDRESS_DOMAIN)
        _feed(digest, project.encode("utf-8"))
        _feed(digest, clip.encode("utf-8"))
        digest.update(len(items).to_bytes(4, "big"))
        for name, data in items:
            _feed(digest, name.encode("utf-8"))
            _feed(digest, data)
        return digest.hexdigest()
    except MotionRetargetBundleContractError:
        raise
    except (LayerManifestError, TypeError, ValueError) as exc:
        raise MotionRetargetBundleContractError(
            "Motion retarget bundle address inputs are invalid"
        ) from exc


def _cross_bind(project, profile_sha, instance_sha, run_sha,
                target, instance, run, report, mesh) -> None:
    if target.get("project_id") != project or mesh.get("clip_id") != instance.get("clip_id"):
        raise MotionRetargetBundleContractError(
            "Retarget project or clip binding is invalid"
        )
    instance_source, inputs = instance["source"], run["inputs"]
    report_source, mesh_source = report["source"], mesh["source"]
    motion = {field: instance_source[field] for field in _MOTION_FIELDS}
    expected_report = {
        **motion,
        "target_profile_sha256": profile_sha,
        "instance_sha256": instance_sha,
        "retarget_run_identity_sha256": run["run_identity_sha256"],
        "retarget_run_document_sha256": run_sha,
    }
    expected_mesh = {
        "instance_sha256": instance_sha,
        "target_profile_sha256": profile_sha,
        "p3_rig_sha256": target["source"]["p3"]["rig_sha256"],
        "p3_bundle_sha256": target["source"]["p3"]["bundle_sha256"],
    }
    if inputs != {**motion, "target_profile_sha256": profile_sha} or \
            instance_source["target_profile_sha256"] != profile_sha or \
            instance_source["retarget_run_identity_sha256"] != run["run_identity_sha256"]:
        raise MotionRetargetBundleContractError("Retarget run input chain differs")
    if report_source != expected_report:
        raise MotionRetargetBundleContractError("Retarget report identity chain differs")
    if mesh_source != expected_mesh:
        raise MotionRetargetBundleContractError("Mesh report identity chain differs")
    if retarget_run_document_sha256(run) != run_sha or \
            instance_sha256(instance) != instance_sha:
        raise MotionRetargetBundleContractError("Retarget document SHA chain differs")


def _document(value: Mapping[str, Any], label: str, limit: int) -> bytes:
    if not isinstance(value, Mapping):
        raise MotionRetargetBundleContractError(f"{label} must be an object")
    data = _canonical(value)
    if len(data) > limit:
        raise MotionRetargetBundleContractError(f"{label} exceeds its byte limit")
    return data


def _require_items(value) -> tuple[tuple[str, bytes], ...]:
    if type(value) is not tuple or len(value) != len(DOCUMENT_NAMES):
        raise MotionRetargetBundleContractError("Retarget document inventory is invalid")
    result = []
    for index, item in enumerate(value):
        if type(item) is not tuple or len(item) != 2:
            raise MotionRetargetBundleContractError("Retarget document inventory is invalid")
        name, data = item
        if name != DOCUMENT_NAMES[index] or not isinstance(data, bytes) \
                or len(data) > _LIMITS[index]:
            raise MotionRetargetBundleContractError("Retarget document inventory is invalid")
        try:
            decoded = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise MotionRetargetBundleContractError(
                f"{name} is not canonical JSON"
            ) from exc
        if not isinstance(decoded, Mapping) or _canonical(decoded) != data:
            raise MotionRetargetBundleContractError(f"{name} is not canonical JSON")
        result.append((name, data))
    if sum(len(data) for _name, data in result) > MAX_TOTAL_DOCUMENT_BYTES:
        raise MotionRetargetBundleContractError("Retarget bundle byte limit exceeded")
    return tuple(result)


def _canonical(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        dict(value), ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")


def _feed(digest, value: bytes) -> None:
    digest.update(len(value).to_bytes(8, "big"))
    digest.update(value)


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()
