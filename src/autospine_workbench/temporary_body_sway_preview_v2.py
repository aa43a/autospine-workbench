"""Pure compiler for the public TemporaryBodySwayPreview v2 contract."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from typing import Any

from .body_sway_preview_inputs_v2 import BodySwayPreviewInputsV2
from .body_sway_preview_profile_v2 import (
    PREVIEW_RELEASE_GATE,
    PREVIEW_SEMANTICS,
    body_sway_preview_compiler_profile_v2,
    body_sway_preview_runtime_target_v2,
)
from .mesh_bundle_integrity import VerifiedMeshBundle
from .temporary_body_sway_preview_artifacts_v2 import (
    TemporaryBodySwayPreviewArtifactV2Error,
    compile_temporary_body_sway_preview_artifacts_v2,
)
from .temporary_body_sway_preview_inventory_v2 import (
    TemporaryBodySwayPreviewInventoryV2Error,
    build_temporary_body_sway_preview_inventory_v2,
)
from .temporary_body_sway_preview_validation_v2 import (
    FORMAT,
    FORMAT_VERSION,
    TemporaryBodySwayPreviewValidationV2Error,
    require_temporary_body_sway_preview_v2,
)


class TemporaryBodySwayPreviewV2Error(ValueError):
    """Raised when exact capture-framed evidence cannot form preview v2."""


@dataclass(frozen=True, slots=True)
class TemporaryBodySwayPreviewV2:
    """Frozen canonical v2 manifest and exact five artifact bytes."""

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


def compile_temporary_body_sway_preview_v2(
    inputs: BodySwayPreviewInputsV2,
    mesh_bundle: VerifiedMeshBundle,
) -> TemporaryBodySwayPreviewV2:
    """Compile a capture-framed diagnostic package with no release authority."""

    if type(inputs) is not BodySwayPreviewInputsV2 \
            or type(mesh_bundle) is not VerifiedMeshBundle:
        raise TemporaryBodySwayPreviewV2Error(
            "Temporary preview v2 requires exact admitted inputs"
        )
    try:
        compiled = compile_temporary_body_sway_preview_artifacts_v2(
            inputs, mesh_bundle
        )
        artifacts = compiled.artifact_bytes
        inventory = build_temporary_body_sway_preview_inventory_v2(artifacts)
        rig = inputs.probe_inputs.rig
        attachments = rig["attachments"]
        projection = compiled.preview.projection.public_metadata
        source = {
            "body_sway_probe_report_sha256": inputs.report_sha256,
            "capture_framing_candidate_sha256":
                inputs.framing_candidate_sha256,
            "capture_framing_decision_sha256":
                inputs.framing_decision_sha256,
            "capture_framing_revision": inputs.framing_revision,
            "current_p10_1_head": inputs.framing_candidate[
                "source"
            ]["current_p10_1_head"],
            **inputs.source,
        }
        document = {
            "format": FORMAT,
            "format_version": FORMAT_VERSION,
            "project_id": inputs.project_id,
            "clip_id": inputs.clip_id,
            "source": source,
            "timing": inputs.timing,
            "selection": inputs.selection,
            "compiler": body_sway_preview_compiler_profile_v2(),
            "semantics": _copy(PREVIEW_SEMANTICS),
            "runtime_target": body_sway_preview_runtime_target_v2(),
            "projection": projection,
            "capture_plan": compiled.capture_plan,
            "artifacts": inventory,
            "status": "ready_for_official_runtime_capture_v2",
            "release_gate": _copy(PREVIEW_RELEASE_GATE),
            "summary": {
                "probe_sample_count": projection["sample_count"],
                "rotation_track_count": projection["rotation_track_count"],
                "rotation_key_count": projection["rotation_key_count"],
                "capture_case_count": len(compiled.capture_plan["cases"]),
                "artifact_file_count": len(inventory["files"]),
                "artifact_total_bytes": sum(map(len, artifacts.values())),
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
        require_temporary_body_sway_preview_v2(document, artifacts)
        return TemporaryBodySwayPreviewV2(
            _canonical(document), tuple(sorted(artifacts.items()))
        )
    except TemporaryBodySwayPreviewV2Error:
        raise
    except (
        TemporaryBodySwayPreviewArtifactV2Error,
        TemporaryBodySwayPreviewInventoryV2Error,
        TemporaryBodySwayPreviewValidationV2Error,
        KeyError, OverflowError, TypeError, UnicodeError, ValueError,
    ) as exc:
        raise TemporaryBodySwayPreviewV2Error(
            f"Temporary body-sway preview v2 compilation failed: {exc}"
        ) from exc


def require_exact_temporary_body_sway_preview_v2(
    inputs: BodySwayPreviewInputsV2, mesh_bundle: VerifiedMeshBundle,
    document: dict[str, Any], artifact_bytes: dict[str, bytes],
) -> str:
    """Replay trusted inputs and require byte-identical v2 output."""

    try:
        require_temporary_body_sway_preview_v2(document, artifact_bytes)
        expected = compile_temporary_body_sway_preview_v2(inputs, mesh_bundle)
        if _canonical(document).encode("utf-8") != expected.canonical_bytes \
                or artifact_bytes != expected.artifact_bytes:
            raise TemporaryBodySwayPreviewV2Error(
                "Temporary preview v2 differs from exact upstream replay"
            )
        return expected.sha256
    except TemporaryBodySwayPreviewV2Error:
        raise
    except (
        TemporaryBodySwayPreviewValidationV2Error,
        OverflowError, TypeError, UnicodeError, ValueError,
    ) as exc:
        raise TemporaryBodySwayPreviewV2Error(
            f"Exact temporary preview v2 replay failed: {exc}"
        ) from exc


def _copy(value: Any) -> Any:
    return json.loads(_canonical(value))


def _canonical(value: Any) -> str:
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    )
