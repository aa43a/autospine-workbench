"""Compile immutable P4 target profiles from exact verified P3 bundles."""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any

from .ik_target_geometry import (
    PROFILE_FORMAT,
    PROFILE_VERSION,
    SOLVER_ID,
    SOLVER_VERSION,
    SOURCE_IDENTITY_FIELDS,
    derive_ik_handles,
    solver_config,
)
from .ik_target_profile_validation import (
    IkTargetProfileValidationError,
    require_ik_target_profile,
)
from .mesh_bundle_integrity import VerifiedMeshBundle
from .resolved_project import canonical_sha256


class IkTargetProfileError(ValueError):
    """Raised when an exact P3 bundle cannot produce a valid P4 profile."""


@dataclass(frozen=True, slots=True)
class IkTargetProfile:
    """Frozen canonical JSON snapshot with isolated accessors."""

    _document_json: str

    @property
    def document(self) -> dict[str, Any]:
        return json.loads(self._document_json)

    @property
    def source(self) -> dict[str, str]:
        return self.document["source"]

    @property
    def handles(self) -> list[dict[str, Any]]:
        return self.document["handles"]

    @property
    def sha256(self) -> str:
        return canonical_sha256(self.document)


def compile_ik_target_profile(bundle: VerifiedMeshBundle) -> IkTargetProfile:
    """Bind four canonical rigid chains to one exact verified P3 address."""

    if not isinstance(bundle, VerifiedMeshBundle):
        raise IkTargetProfileError(
            "IK target profiles require a VerifiedMeshBundleReader result"
        )
    try:
        rig = bundle.rig
        canvas = rig.get("canvas")
        if not isinstance(canvas, dict):
            raise IkTargetProfileError("Verified P3 RigIR canvas is invalid")
        document = {
            "format": PROFILE_FORMAT,
            "format_version": PROFILE_VERSION,
            "project_id": bundle.project_id,
            "source": {
                field: getattr(bundle, field) for field in SOURCE_IDENTITY_FIELDS
            },
            "canvas": {
                "width": canvas.get("width"), "height": canvas.get("height"),
                "origin": canvas.get("origin"), "x_axis": canvas.get("x_axis"),
                "y_axis": canvas.get("y_axis"), "units": canvas.get("units"),
            },
            "solver": {
                "id": SOLVER_ID, "version": SOLVER_VERSION,
                "config": solver_config(),
            },
            "handles": derive_ik_handles(rig),
        }
        require_ik_target_profile(document, verified_bundle=bundle)
        encoded = json.dumps(
            document, ensure_ascii=False, allow_nan=False,
            sort_keys=True, separators=(",", ":"),
        )
        return IkTargetProfile(encoded)
    except IkTargetProfileError:
        raise
    except (IkTargetProfileValidationError, KeyError, TypeError, ValueError) as exc:
        raise IkTargetProfileError(f"IK target profile compilation failed: {exc}") from exc
