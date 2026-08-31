"""Pure five-file compilation for a capture-framed Spine preview v2."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from typing import Any

from .body_sway_preview_capture_plan_v2 import (
    BodySwayPreviewCapturePlanV2Error,
    build_body_sway_preview_capture_plan_v2,
)
from .body_sway_preview_inputs_v2 import BodySwayPreviewInputsV2
from .body_sway_preview_page import body_sway_preview_player_html
from .body_sway_preview_session_v2 import build_body_sway_preview_session_v2
from .mesh_bundle_integrity import VerifiedMeshBundle
from .mesh_source_from_bundle import (
    VerifiedMeshBundleSourceError,
    verified_mesh_source_from_bundle,
)
from .resolved_project import canonical_sha256
from .spine42_atlas import Spine42Atlas, Spine42AtlasError, build_spine42_atlas
from .spine42_body_sway_preview_adapter_v2 import (
    Spine42BodySwayPreviewAdapterV2Error,
    Spine42BodySwayPreviewV2,
    compile_spine42_body_sway_preview_v2,
)
from .temporary_body_sway_preview_artifacts import (
    ARTIFACT_PATHS,
    MAX_ARTIFACT_BYTES,
    MAX_ATLAS_BYTES,
    MAX_SKELETON_BYTES,
    MAX_SMALL_FILE_BYTES,
    MAX_TEXTURE_BYTES,
)


class TemporaryBodySwayPreviewArtifactV2Error(ValueError):
    """Raised when exact P10.2b inputs cannot form five v2 artifacts."""


@dataclass(frozen=True, slots=True)
class TemporaryBodySwayPreviewArtifactsV2:
    preview: Spine42BodySwayPreviewV2
    atlas: Spine42Atlas
    _capture_plan_json: str = field(repr=False)
    _artifact_items: tuple[tuple[str, bytes], ...] = field(repr=False)

    @property
    def capture_plan(self) -> dict[str, Any]:
        return json.loads(self._capture_plan_json)

    @property
    def artifact_bytes(self) -> dict[str, bytes]:
        return dict(self._artifact_items)


def compile_temporary_body_sway_preview_artifacts_v2(
    inputs: BodySwayPreviewInputsV2,
    mesh_bundle: VerifiedMeshBundle,
) -> TemporaryBodySwayPreviewArtifactsV2:
    """Compile a deterministic package without running or publishing it."""

    if type(inputs) is not BodySwayPreviewInputsV2 \
            or type(mesh_bundle) is not VerifiedMeshBundle:
        raise TemporaryBodySwayPreviewArtifactV2Error(
            "Temporary preview v2 artifacts require exact admitted inputs"
        )
    try:
        _require_p3_identity(inputs, mesh_bundle)
        source = verified_mesh_source_from_bundle(mesh_bundle)
        preview = compile_spine42_body_sway_preview_v2(inputs)
        atlas = build_spine42_atlas(
            source.png_by_attachment, page_name="skeleton.png"
        )
        plan = build_body_sway_preview_capture_plan_v2(
            inputs, preview.projection
        )
        items = tuple(sorted({
            "runtime/player.html": body_sway_preview_player_html(),
            "runtime/session.json": build_body_sway_preview_session_v2(
                preview, atlas, plan, loop=inputs.timing["loop"]
            ),
            "runtime/skeleton.atlas": atlas.atlas_bytes,
            "runtime/skeleton.json": preview.skeleton_bytes,
            "runtime/skeleton.png": atlas.png_bytes,
        }.items()))
        _require_resource_bounds(items)
        return TemporaryBodySwayPreviewArtifactsV2(
            preview, atlas, _canonical(plan), items,
        )
    except TemporaryBodySwayPreviewArtifactV2Error:
        raise
    except (
        BodySwayPreviewCapturePlanV2Error, Spine42AtlasError,
        Spine42BodySwayPreviewAdapterV2Error,
        VerifiedMeshBundleSourceError, KeyError, OverflowError,
        TypeError, UnicodeError, ValueError,
    ) as exc:
        raise TemporaryBodySwayPreviewArtifactV2Error(
            f"Temporary body-sway preview v2 artifacts failed: {exc}"
        ) from exc


def _require_p3_identity(inputs, bundle) -> None:
    source = inputs.source["p3"]
    if bundle.project_id != inputs.project_id \
            or bundle.rig_sha256 != source["rig_sha256"] \
            or bundle.bundle_sha256 != source["bundle_sha256"] \
            or canonical_sha256(bundle.rig) != bundle.rig_sha256:
        raise TemporaryBodySwayPreviewArtifactV2Error(
            "P3 image bundle differs from capture-framed inputs"
        )


def _require_resource_bounds(items) -> None:
    values = dict(items)
    if tuple(sorted(values)) != ARTIFACT_PATHS:
        raise TemporaryBodySwayPreviewArtifactV2Error(
            "Temporary preview v2 artifact inventory is incomplete"
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
        raise TemporaryBodySwayPreviewArtifactV2Error(
            "Temporary preview v2 artifact resource limit exceeded"
        )


def _canonical(value: Any) -> str:
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    )
