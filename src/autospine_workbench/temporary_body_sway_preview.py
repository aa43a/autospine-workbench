"""Pure compiler for the public TemporaryBodySwayPreview v1 contract."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from typing import Any

from .body_sway_preview_inputs import BodySwayPreviewInputs
from .body_sway_preview_profile import (
    PREVIEW_RELEASE_GATE,
    PREVIEW_SEMANTICS,
    body_sway_preview_compiler_profile,
    body_sway_preview_runtime_target,
)
from .mesh_bundle_integrity import VerifiedMeshBundle
from .temporary_body_sway_preview_artifacts import (
    TemporaryBodySwayPreviewArtifactError,
    compile_temporary_body_sway_preview_artifacts,
)
from .temporary_body_sway_preview_inventory import (
    TemporaryBodySwayPreviewInventoryError,
    build_temporary_body_sway_preview_inventory,
)
from .temporary_body_sway_preview_validation import (
    FORMAT,
    FORMAT_VERSION,
    TemporaryBodySwayPreviewValidationError,
    require_temporary_body_sway_preview,
)


class TemporaryBodySwayPreviewError(ValueError):
    """Raised when exact admitted evidence cannot form a temporary preview."""


@dataclass(frozen=True, slots=True)
class TemporaryBodySwayPreview:
    """Frozen canonical manifest and its exact five detached artifact bytes."""

    _canonical_json: str = field(repr=False)
    _artifact_items: tuple[tuple[str, bytes], ...] = field(repr=False)

    @property
    def document(self) -> dict[str, Any]:
        return json.loads(self._canonical_json)

    @property
    def canonical_bytes(self) -> bytes:
        return self._canonical_json.encode("utf-8")

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_bytes).hexdigest()

    @property
    def artifact_bytes(self) -> dict[str, bytes]:
        return dict(self._artifact_items)

    @property
    def artifact_set_sha256(self) -> str:
        return self.document["artifacts"]["artifact_set_sha256"]


def compile_temporary_body_sway_preview(
    inputs: BodySwayPreviewInputs,
    mesh_bundle: VerifiedMeshBundle,
) -> TemporaryBodySwayPreview:
    """Compile a read-only diagnostic package; never create release authority."""

    if type(inputs) is not BodySwayPreviewInputs \
            or type(mesh_bundle) is not VerifiedMeshBundle:
        raise TemporaryBodySwayPreviewError(
            "Temporary body-sway preview requires exact admitted inputs"
        )
    try:
        compiled = compile_temporary_body_sway_preview_artifacts(
            inputs, mesh_bundle
        )
        artifact_bytes = compiled.artifact_bytes
        inventory = build_temporary_body_sway_preview_inventory(artifact_bytes)
        rig = inputs.probe_inputs.rig
        attachments = rig["attachments"]
        projection = compiled.preview.projection.public_metadata
        document = {
            "format": FORMAT,
            "format_version": FORMAT_VERSION,
            "project_id": inputs.project_id,
            "clip_id": inputs.clip_id,
            "source": {
                "body_sway_probe_report_sha256": inputs.report_sha256,
                **inputs.source,
            },
            "timing": inputs.timing,
            "selection": inputs.selection,
            "compiler": body_sway_preview_compiler_profile(),
            "semantics": _copy(PREVIEW_SEMANTICS),
            "runtime_target": body_sway_preview_runtime_target(),
            "projection": projection,
            "capture_plan": compiled.capture_plan,
            "artifacts": inventory,
            "status": "ready_for_official_runtime_capture",
            "release_gate": _copy(PREVIEW_RELEASE_GATE),
            "summary": {
                "probe_sample_count": projection["sample_count"],
                "rotation_track_count": projection["rotation_track_count"],
                "rotation_key_count": projection["rotation_key_count"],
                "capture_case_count": len(compiled.capture_plan["cases"]),
                "artifact_file_count": len(inventory["files"]),
                "artifact_total_bytes": sum(map(len, artifact_bytes.values())),
                "bone_count": len(rig["bones"]),
                "slot_count": len(rig["slots"]),
                "attachment_count": len(attachments),
                "region_attachment_count": sum(
                    row["type"] == "region" for row in attachments
                ),
                "mesh_attachment_count": sum(
                    row["type"] == "mesh" for row in attachments
                ),
                "atlas_width": compiled.atlas.width,
                "atlas_height": compiled.atlas.height,
            },
        }
        require_temporary_body_sway_preview(document, artifact_bytes)
        return TemporaryBodySwayPreview(
            _canonical(document), tuple(sorted(artifact_bytes.items()))
        )
    except TemporaryBodySwayPreviewError:
        raise
    except (
        TemporaryBodySwayPreviewArtifactError,
        TemporaryBodySwayPreviewInventoryError,
        TemporaryBodySwayPreviewValidationError,
        KeyError, OverflowError, TypeError, UnicodeError, ValueError,
    ) as exc:
        raise TemporaryBodySwayPreviewError(
            f"Temporary body-sway preview compilation failed: {exc}"
        ) from exc


def require_exact_temporary_body_sway_preview(
    inputs: BodySwayPreviewInputs,
    mesh_bundle: VerifiedMeshBundle,
    document: dict[str, Any],
    artifact_bytes: dict[str, bytes],
) -> str:
    """Replay trusted inputs and require byte-identical manifest and assets."""

    try:
        require_temporary_body_sway_preview(document, artifact_bytes)
        expected = compile_temporary_body_sway_preview(inputs, mesh_bundle)
        supplied_manifest = _canonical(document).encode("utf-8")
        if supplied_manifest != expected.canonical_bytes \
                or artifact_bytes != expected.artifact_bytes:
            raise TemporaryBodySwayPreviewError(
                "Temporary preview differs from exact upstream replay"
            )
        return expected.sha256
    except TemporaryBodySwayPreviewError:
        raise
    except (
        TemporaryBodySwayPreviewValidationError, OverflowError,
        TypeError, UnicodeError, ValueError,
    ) as exc:
        raise TemporaryBodySwayPreviewError(
            f"Exact temporary preview replay failed: {exc}"
        ) from exc


def _copy(value: Any) -> Any:
    return json.loads(_canonical(value))


def _canonical(value: Any) -> str:
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    )
