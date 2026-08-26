"""In-memory P3/P5/P9 replay boundary for idle-behavior candidates."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
import json
from typing import Any

from .ik_target_geometry import SOURCE_IDENTITY_FIELDS
from .manifest_artifacts import LayerManifestError, require_safe_token
from .mesh_bundle_admission import MeshBundleAdmissionError
from .mesh_bundle_integrity import VerifiedMeshBundle
from .motion_instance_v2_validation import (
    MotionInstanceV2ValidationError,
    require_motion_instance_v2,
)
from .motion_retarget_bundle_integrity import VerifiedMotionRetargetBundle
from .resolved_project import canonical_sha256
from .reviewed_motion_bundle_contract import (
    DOCUMENT_NAMES,
    ReviewedMotionBundleContract,
    ReviewedMotionBundleContractError,
    build_reviewed_motion_bundle_contract,
)
from .reviewed_motion_bundle_upstream import (
    ReviewedMotionBundleUpstreamError,
    require_reviewed_motion_upstreams,
)
from .safe_input_files import SafeInputFileError, strict_json_object


_MANIFEST_TOP = {
    "format", "format_version", "project_id", "revision", "source",
    "layers", "qa",
}
_AXES = {
    "origin": "top_left", "x_axis": "right", "y_axis": "down",
    "units": "pixel", "side_naming": "character_side",
}


class IdleBehaviorInputError(ValueError):
    """Raised when candidate inputs are nominal, stale, or cross-wired."""


@dataclass(frozen=True, slots=True)
class IdleBehaviorInputs:
    """Frozen replayed documents and exact stage identity inventory."""

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
    def base_motion_instance(self) -> dict[str, Any]:
        return self._document("p5-motion-instance")

    @property
    def motion_instance_v2(self) -> dict[str, Any]:
        return self._document("p9-motion-instance-v2")

    @property
    def source(self) -> dict[str, Any]:
        return json.loads(self._source_json)

    @property
    def timing(self) -> dict[str, Any]:
        return dict(self.motion_instance_v2["timing"])


def require_idle_behavior_inputs(
    layer_manifest: Mapping[str, Any],
    mesh_bundle: VerifiedMeshBundle,
    retarget_bundle: VerifiedMotionRetargetBundle,
    reviewed_bundle: ReviewedMotionBundleContract,
) -> IdleBehaviorInputs:
    """Replay explicit in-memory stage values and return isolated snapshots."""

    try:
        manifest = _require_manifest(layer_manifest)
        base, target = require_reviewed_motion_upstreams(
            mesh_bundle, retarget_bundle
        )
        documents = _reviewed_documents(reviewed_bundle)
        rebuilt = build_reviewed_motion_bundle_contract(
            mesh_bundle.project_id,
            *(documents[name] for name in DOCUMENT_NAMES[:5]),
            mesh_bundle, base, target,
        )
        if rebuilt != reviewed_bundle \
                or rebuilt.document_bytes != reviewed_bundle.document_bytes:
            raise IdleBehaviorInputError(
                "Reviewed P9 bundle differs from its six-document replay"
            )
        v2, policy = documents[DOCUMENT_NAMES[4]], documents[DOCUMENT_NAMES[3]]
        require_motion_instance_v2(
            v2, target_profile=target, base_motion_instance=base,
            reviewed_motion_policy=policy,
        )
        _cross_bind(manifest, mesh_bundle, retarget_bundle, reviewed_bundle,
                    target, base, v2)
        source = _source_inventory(mesh_bundle, retarget_bundle, reviewed_bundle)
        frozen = tuple((name, _json(value)) for name, value in (
            ("layer-manifest", manifest), ("p3-rig", mesh_bundle.rig),
            ("p5-target-profile", target), ("p5-motion-instance", base),
            ("p9-motion-instance-v2", v2),
        ))
        return IdleBehaviorInputs(
            mesh_bundle.project_id, reviewed_bundle.clip_id,
            frozen, _json(source),
        )
    except IdleBehaviorInputError:
        raise
    except (
        LayerManifestError, MeshBundleAdmissionError,
        MotionInstanceV2ValidationError, ReviewedMotionBundleContractError,
        ReviewedMotionBundleUpstreamError, SafeInputFileError,
        AttributeError, KeyError, OverflowError, TypeError, UnicodeError,
        ValueError,
    ) as exc:
        raise IdleBehaviorInputError(
            f"Idle behavior input admission failed: {exc}"
        ) from exc


def _require_manifest(value: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _MANIFEST_TOP:
        raise IdleBehaviorInputError("Layer Manifest fields are unsupported")
    manifest = json.loads(_json(value))
    if manifest.get("format") != "autospine-layer-manifest" \
            or type(manifest.get("format_version")) is not int \
            or manifest["format_version"] != 1:
        raise IdleBehaviorInputError("Layer Manifest format is unsupported")
    require_safe_token(manifest.get("project_id"), "Layer Manifest project id")
    if type(manifest.get("revision")) is not int or manifest["revision"] < 0:
        raise IdleBehaviorInputError("Layer Manifest revision is invalid")
    if not isinstance(manifest.get("layers"), list) \
            or len(manifest["layers"]) > 4096:
        raise IdleBehaviorInputError("Layer Manifest layer inventory is invalid")
    source, qa = manifest.get("source"), manifest.get("qa")
    if not isinstance(source, Mapping) or not isinstance(qa, Mapping) \
            or qa.get("status") not in {"passed", "manual_required"}:
        raise IdleBehaviorInputError("Layer Manifest source or QA is invalid")
    canvas, axes = source.get("canvas"), source.get("coordinate_system")
    if not isinstance(canvas, list) or len(canvas) != 2 \
            or any(type(item) is not int or item < 1 for item in canvas) \
            or not isinstance(axes, Mapping) \
            or any(axes.get(key) != expected for key, expected in _AXES.items()):
        raise IdleBehaviorInputError("Layer Manifest coordinate space is invalid")
    return manifest


def _reviewed_documents(bundle: ReviewedMotionBundleContract) -> dict[str, dict]:
    if type(bundle) is not ReviewedMotionBundleContract:
        raise IdleBehaviorInputError(
            "P9 admission requires an exact ReviewedMotionBundleContract"
        )
    raw = bundle.document_bytes
    if tuple(raw) != DOCUMENT_NAMES:
        raise IdleBehaviorInputError("Reviewed P9 document inventory is invalid")
    return {name: strict_json_object(raw[name], name) for name in DOCUMENT_NAMES}


def _cross_bind(manifest, mesh, retarget, reviewed, target, base, v2) -> None:
    projects = {
        manifest["project_id"], mesh.project_id, retarget.project_id,
        reviewed.project_id, target["project_id"],
    }
    if len(projects) != 1:
        raise IdleBehaviorInputError("P3/P5/P9 projects differ")
    if canonical_sha256(manifest) != mesh.layer_manifest_sha256:
        raise IdleBehaviorInputError("Layer Manifest SHA binding is stale")
    canvas = manifest["source"]["canvas"]
    if mesh.rig.get("canvas") != {
        "width": canvas[0], "height": canvas[1], **{
            key: _AXES[key] for key in ("origin", "x_axis", "y_axis", "units")
        },
    }:
        raise IdleBehaviorInputError("Layer Manifest and P3 canvases differ")
    if target["source"]["p3"] != _p3_inventory(mesh):
        raise IdleBehaviorInputError("P5 target P3 inventory is stale")
    if base["clip_id"] != reviewed.clip_id or v2["clip_id"] != reviewed.clip_id \
            or base["timing"] != v2["timing"]:
        raise IdleBehaviorInputError("P5/P9 clip timing differs")


def _source_inventory(mesh, retarget, reviewed) -> dict[str, Any]:
    return {
        "layer_manifest_sha256": mesh.layer_manifest_sha256,
        "p3": _p3_inventory(mesh),
        "p5": {
            "target_profile_sha256": retarget.target_profile_sha256,
            "instance_sha256": retarget.instance_sha256,
            "run_sha256": retarget.run_document_sha256,
            "retarget_report_sha256": retarget.retarget_report_sha256,
            "mesh_regression_sha256": retarget.mesh_regression_sha256,
            "bundle_sha256": retarget.bundle_sha256,
        },
        "p9": reviewed.identities,
    }


def _p3_inventory(mesh) -> dict[str, str]:
    return {field: getattr(mesh, field) for field in SOURCE_IDENTITY_FIELDS}


def _json(value: Any) -> str:
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    )
