"""Pure adapter from an already verified P3 bundle to its source images."""

from __future__ import annotations

import json

from .mesh_bundle_integrity import VerifiedMeshBundle
from .mesh_source_images import (
    AttachmentImageBudget,
    VerifiedMeshSource,
    VerifiedMeshSourceReaderError,
    verified_attachment_images,
)
from .resolved_project import canonical_sha256


class VerifiedMeshBundleSourceError(ValueError):
    """Raised when an admitted P3 bundle cannot supply exact adapter images."""


def verified_mesh_source_from_bundle(
    bundle: VerifiedMeshBundle,
    *, image_budget: AttachmentImageBudget | None = None,
) -> VerifiedMeshSource:
    """Reuse one verified snapshot without loading its content address again."""

    try:
        if type(bundle) is not VerifiedMeshBundle:
            raise VerifiedMeshBundleSourceError(
                "An exact verified P3 mesh bundle is required"
            )
        rig = bundle.rig
        if canonical_sha256(rig) != bundle.rig_sha256:
            raise VerifiedMeshBundleSourceError(
                "Verified P3 RigIR identity differs from its snapshot"
            )
        images = verified_attachment_images(
            rig, bundle.source_pngs, budget=image_budget
        )
        return VerifiedMeshSource(
            path=bundle.path,
            project_id=bundle.project_id,
            p3_rig_sha256=bundle.rig_sha256,
            p3_bundle_sha256=bundle.bundle_sha256,
            base_rig_sha256=bundle.base_rig_sha256,
            base_bundle_sha256=bundle.base_bundle_sha256,
            _rig_json=_canonical(rig),
            _images=images,
        )
    except VerifiedMeshBundleSourceError:
        raise
    except (
        KeyError, OverflowError, TypeError, UnicodeError, ValueError,
        VerifiedMeshSourceReaderError,
    ) as exc:
        raise VerifiedMeshBundleSourceError(
            f"Verified P3 source snapshot is invalid: {exc}"
        ) from exc


def _canonical(value) -> str:
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    )
