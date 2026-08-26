"""Pure five-file compilation for a temporary body-sway Spine preview."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from typing import Any

from .body_sway_preview_capture_plan import (
    BodySwayPreviewCapturePlanError,
    build_body_sway_preview_capture_plan,
)
from .body_sway_preview_inputs import BodySwayPreviewInputs
from .body_sway_preview_page import body_sway_preview_player_html
from .body_sway_preview_session import build_body_sway_preview_session
from .mesh_bundle_integrity import VerifiedMeshBundle
from .mesh_source_from_bundle import (
    VerifiedMeshBundleSourceError,
    verified_mesh_source_from_bundle,
)
from .resolved_project import canonical_sha256
from .spine42_atlas import Spine42Atlas, Spine42AtlasError, build_spine42_atlas
from .spine42_body_sway_preview_adapter import (
    Spine42BodySwayPreview,
    Spine42BodySwayPreviewAdapterError,
    compile_spine42_body_sway_preview,
)


ARTIFACT_PATHS = (
    "runtime/player.html",
    "runtime/session.json",
    "runtime/skeleton.atlas",
    "runtime/skeleton.json",
    "runtime/skeleton.png",
)
MAX_SKELETON_BYTES = 128 * 1024 * 1024
MAX_ATLAS_BYTES = 4 * 1024 * 1024
MAX_TEXTURE_BYTES = 128 * 1024 * 1024
MAX_SMALL_FILE_BYTES = 1024 * 1024
MAX_ARTIFACT_BYTES = 256 * 1024 * 1024


class TemporaryBodySwayPreviewArtifactError(ValueError):
    """Raised when exact P10 inputs cannot form the five-file snapshot."""


@dataclass(frozen=True, slots=True)
class TemporaryBodySwayPreviewArtifacts:
    """Frozen semantic values and immutable path-to-byte snapshots."""

    preview: Spine42BodySwayPreview
    atlas: Spine42Atlas
    _capture_plan_json: str = field(repr=False)
    _artifact_items: tuple[tuple[str, bytes], ...] = field(repr=False)

    @property
    def capture_plan(self) -> dict[str, Any]:
        return json.loads(self._capture_plan_json)

    @property
    def artifact_bytes(self) -> dict[str, bytes]:
        return dict(self._artifact_items)

    @property
    def artifact_sha256s(self) -> dict[str, str]:
        return {path: _sha(raw) for path, raw in self._artifact_items}


def compile_temporary_body_sway_preview_artifacts(
    inputs: BodySwayPreviewInputs,
    mesh_bundle: VerifiedMeshBundle,
) -> TemporaryBodySwayPreviewArtifacts:
    """Build exact bytes in memory; never call a store or release contract."""

    if type(inputs) is not BodySwayPreviewInputs \
            or type(mesh_bundle) is not VerifiedMeshBundle:
        raise TemporaryBodySwayPreviewArtifactError(
            "Temporary preview artifacts require exact admitted inputs"
        )
    try:
        _require_p3_identity(inputs, mesh_bundle)
        source = verified_mesh_source_from_bundle(mesh_bundle)
        preview = compile_spine42_body_sway_preview(inputs)
        atlas = build_spine42_atlas(
            source.png_by_attachment, page_name="skeleton.png"
        )
        plan = build_body_sway_preview_capture_plan(
            inputs, preview.projection
        )
        items = tuple(sorted({
            "runtime/player.html": body_sway_preview_player_html(),
            "runtime/session.json": build_body_sway_preview_session(
                preview, atlas, plan
            ),
            "runtime/skeleton.atlas": atlas.atlas_bytes,
            "runtime/skeleton.json": preview.skeleton_bytes,
            "runtime/skeleton.png": atlas.png_bytes,
        }.items()))
        _require_resource_bounds(items)
        return TemporaryBodySwayPreviewArtifacts(
            preview=preview,
            atlas=atlas,
            _capture_plan_json=_canonical(plan),
            _artifact_items=items,
        )
    except TemporaryBodySwayPreviewArtifactError:
        raise
    except (
        BodySwayPreviewCapturePlanError, Spine42AtlasError,
        Spine42BodySwayPreviewAdapterError, VerifiedMeshBundleSourceError,
        KeyError, OverflowError, TypeError, UnicodeError, ValueError,
    ) as exc:
        raise TemporaryBodySwayPreviewArtifactError(
            f"Temporary body-sway preview artifacts failed: {exc}"
        ) from exc


def _require_p3_identity(inputs, bundle) -> None:
    source = inputs.source["p3"]
    if bundle.project_id != inputs.project_id \
            or bundle.rig_sha256 != source["rig_sha256"] \
            or bundle.bundle_sha256 != source["bundle_sha256"] \
            or canonical_sha256(bundle.rig) != bundle.rig_sha256:
        raise TemporaryBodySwayPreviewArtifactError(
            "P3 image bundle differs from exact body-sway inputs"
        )


def _require_resource_bounds(items) -> None:
    values = dict(items)
    if tuple(sorted(values)) != ARTIFACT_PATHS:
        raise TemporaryBodySwayPreviewArtifactError(
            "Temporary preview artifact inventory is incomplete"
        )
    limits = {
        "runtime/player.html": MAX_SMALL_FILE_BYTES,
        "runtime/session.json": MAX_SMALL_FILE_BYTES,
        "runtime/skeleton.atlas": MAX_ATLAS_BYTES,
        "runtime/skeleton.json": MAX_SKELETON_BYTES,
        "runtime/skeleton.png": MAX_TEXTURE_BYTES,
    }
    if any(type(values[path]) is not bytes or not values[path]
           or len(values[path]) > limits[path] for path in ARTIFACT_PATHS) \
            or sum(map(len, values.values())) > MAX_ARTIFACT_BYTES:
        raise TemporaryBodySwayPreviewArtifactError(
            "Temporary preview artifact resource limit exceeded"
        )


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical(value: Any) -> str:
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    )
