"""Pure immutable three-document contract for ProjectedMotionIR bundles."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
import hashlib
import json
from typing import Any

from .camera_model_validation import (
    MAX_DOCUMENT_BYTES as MAX_CAMERA_BYTES,
    CameraModelError,
    camera_model_sha256,
    require_camera_model,
)
from .immutable_bundle_fs import (
    ImmutableBundleFSError,
    framed_bundle_sha256,
)
from .projected_motion_compile_run import (
    MAX_RUN_BYTES,
    ProjectedMotionCompileRunError,
    require_projected_motion_compile_run,
)
from .projected_motion_legacy import (
    ProjectedMotionLegacyError,
    compile_projected_motion_to_motion_ir,
)
from .projected_motion_validation import (
    MAX_DOCUMENT_BYTES as MAX_PROJECTED_BYTES,
    ProjectedMotionValidationError,
    projected_motion_ir_sha256,
    require_projected_motion_ir,
)


BUNDLE_ADDRESS_DOMAIN = "autospine-projected-motion-bundle-address/v1"
DOCUMENT_NAMES = ("camera.json", "projected-motion.json", "run-manifest.json")
DOCUMENT_LIMITS = (MAX_CAMERA_BYTES, MAX_PROJECTED_BYTES, MAX_RUN_BYTES)
MAX_TOTAL_BYTES = sum(DOCUMENT_LIMITS)


class ProjectedMotionBundleContractError(ValueError):
    """Raised when projected bundle documents are invalid or cross-wired."""


@dataclass(frozen=True, slots=True)
class ProjectedMotionBundleContract:
    """Frozen canonical documents and exact content address."""

    clip_id: str
    projected_motion_sha256: str
    camera_sha256: str
    run_sha256: str
    legacy_motion_sha256: str
    bundle_sha256: str
    _documents: tuple[tuple[str, bytes], ...] = field(repr=False)

    @property
    def document_bytes(self) -> dict[str, bytes]:
        return dict(self._documents)

    @property
    def inventory(self) -> tuple[str, ...]:
        return tuple(name for name, _data in self._documents)

    @property
    def camera(self) -> dict[str, Any]:
        return json.loads(dict(self._documents)["camera.json"])

    @property
    def projected_motion(self) -> dict[str, Any]:
        return json.loads(dict(self._documents)["projected-motion.json"])

    @property
    def run_manifest(self) -> dict[str, Any]:
        return json.loads(dict(self._documents)["run-manifest.json"])


def build_projected_motion_bundle_contract(
    camera: Mapping[str, Any],
    projected_motion: Mapping[str, Any],
    run_manifest: Mapping[str, Any],
) -> ProjectedMotionBundleContract:
    """Validate, cross-bind, canonicalize, and address three documents."""

    try:
        require_camera_model(camera)
        require_projected_motion_ir(projected_motion)
        legacy = compile_projected_motion_to_motion_ir(projected_motion)
        require_projected_motion_compile_run(
            run_manifest,
            camera=camera,
            projected_motion=projected_motion,
            legacy_motion=legacy,
        )
        values = (camera, projected_motion, run_manifest)
        items = tuple(
            (name, _document(value, name, DOCUMENT_LIMITS[index]))
            for index, (name, value) in enumerate(zip(DOCUMENT_NAMES, values))
        )
        if sum(len(data) for _name, data in items) > MAX_TOTAL_BYTES:
            raise ProjectedMotionBundleContractError(
                "Projected motion bundle exceeds its total byte limit"
            )
        projected_sha = projected_motion_ir_sha256(projected_motion)
        camera_sha = camera_model_sha256(camera)
        run_sha = hashlib.sha256(items[2][1]).hexdigest()
        legacy_sha = run_manifest["output"]["legacy_motion_ir_sha256"]
        return ProjectedMotionBundleContract(
            clip_id=str(projected_motion["clip_id"]),
            projected_motion_sha256=projected_sha,
            camera_sha256=camera_sha,
            run_sha256=run_sha,
            legacy_motion_sha256=str(legacy_sha),
            bundle_sha256=framed_bundle_sha256(
                BUNDLE_ADDRESS_DOMAIN, DOCUMENT_NAMES, dict(items)
            ),
            _documents=items,
        )
    except ProjectedMotionBundleContractError:
        raise
    except (
        CameraModelError,
        ImmutableBundleFSError,
        ProjectedMotionCompileRunError,
        ProjectedMotionLegacyError,
        ProjectedMotionValidationError,
        KeyError,
        OverflowError,
        TypeError,
        ValueError,
    ) as exc:
        raise ProjectedMotionBundleContractError(
            f"Projected motion bundle contract failed: {exc}"
        ) from exc


def _document(value: Mapping[str, Any], label: str, maximum: int) -> bytes:
    if not isinstance(value, Mapping):
        raise ProjectedMotionBundleContractError(f"{label} must be an object")
    try:
        data = json.dumps(
            dict(value), ensure_ascii=False, allow_nan=False,
            sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")
    except (OverflowError, TypeError, ValueError) as exc:
        raise ProjectedMotionBundleContractError(
            f"{label} is not canonical JSON"
        ) from exc
    if len(data) > maximum:
        raise ProjectedMotionBundleContractError(
            f"{label} exceeds its byte limit"
        )
    return data
