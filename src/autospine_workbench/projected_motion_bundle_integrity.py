"""Exact replay verification for snapshotted ProjectedMotionIR bundles."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any

from .camera_model_validation import CameraModelError
from .immutable_bundle_fs import ImmutableBundleSnapshot
from .kimodo_camera_projection import (
    KimodoCameraProjectionError,
    compile_verified_kimodo_projection,
)
from .motion_bundle_reader import (
    VerifiedMotionBundleReader,
    VerifiedMotionBundleReaderError,
)
from .projected_motion_bundle_contract import (
    DOCUMENT_NAMES,
    ProjectedMotionBundleContractError,
    build_projected_motion_bundle_contract,
)
from .projected_motion_compile_run import (
    ProjectedMotionCompileRunError,
    build_projected_motion_compile_run,
)
from .projected_motion_legacy import (
    ProjectedMotionLegacyError,
    compile_projected_motion_to_motion_ir,
)
from .safe_input_files import SafeInputFileError, strict_json_object


class ProjectedMotionBundleIntegrityError(ValueError):
    """Raised when stored projected evidence cannot be reproduced exactly."""


@dataclass(frozen=True, slots=True)
class VerifiedProjectedMotionBundle:
    """Frozen verified identities with isolated document accessors."""

    path: Path
    clip_id: str
    projected_motion_sha256: str
    camera_sha256: str
    run_sha256: str
    legacy_motion_sha256: str
    bundle_sha256: str
    p7_motion_sha256: str
    p7_bundle_sha256: str
    p7_run_sha256: str
    _documents: tuple[tuple[str, bytes], ...] = field(repr=False)

    def _document(self, name: str) -> dict[str, Any]:
        return json.loads(dict(self._documents)[name])

    @property
    def camera(self) -> dict[str, Any]:
        return self._document("camera.json")

    @property
    def projected_motion(self) -> dict[str, Any]:
        return self._document("projected-motion.json")

    @property
    def run_manifest(self) -> dict[str, Any]:
        return self._document("run-manifest.json")

    @property
    def legacy_motion(self) -> dict[str, Any]:
        return compile_projected_motion_to_motion_ir(self.projected_motion)

    @property
    def inventory(self) -> tuple[str, ...]:
        return tuple(name for name, _data in self._documents)


def verify_projected_motion_bundle_snapshot(
    snapshot: ImmutableBundleSnapshot,
    *,
    state_root: Path,
) -> VerifiedProjectedMotionBundle:
    """Rebuild P7 geometry, P8 evidence, run provenance, and all addresses."""

    try:
        if type(snapshot) is not ImmutableBundleSnapshot \
                or snapshot.ordered_names != DOCUMENT_NAMES:
            raise ProjectedMotionBundleIntegrityError(
                "Projected motion snapshot inventory is invalid"
            )
        raw = dict(zip(snapshot.ordered_names, snapshot.payloads))
        documents = {
            name: strict_json_object(raw[name], name) for name in DOCUMENT_NAMES
        }
        camera = documents["camera.json"]
        projected = documents["projected-motion.json"]
        stored_run = documents["run-manifest.json"]
        stored = build_projected_motion_bundle_contract(
            camera, projected, stored_run
        )
        if stored.projected_motion_sha256 != snapshot.primary_sha256 \
                or stored.bundle_sha256 != snapshot.bundle_sha256 \
                or stored.document_bytes != raw:
            raise ProjectedMotionBundleIntegrityError(
                "Projected motion bytes differ from their content address"
            )
        source = projected["source"]
        p7 = VerifiedMotionBundleReader(Path(state_root)).load(
            source["motion_ir_sha256"], source["motion_bundle_sha256"]
        )
        if p7.run_sha256 != source["motion_run_sha256"]:
            raise ProjectedMotionBundleIntegrityError(
                "Projected motion points to a different P7 compile run"
            )
        rebuilt = compile_verified_kimodo_projection(p7, camera)
        if rebuilt.canonical_bytes != raw["projected-motion.json"]:
            raise ProjectedMotionBundleIntegrityError(
                "Projected motion differs from rebuilt P7 geometry"
            )
        legacy = compile_projected_motion_to_motion_ir(rebuilt.document)
        rebuilt_run = build_projected_motion_compile_run(
            p7, camera, rebuilt, legacy
        )
        if rebuilt_run.canonical_bytes != raw["run-manifest.json"]:
            raise ProjectedMotionBundleIntegrityError(
                "Projected compile run differs from exact replay"
            )
        replayed = build_projected_motion_bundle_contract(
            camera, rebuilt.document, rebuilt_run.document
        )
        if replayed != stored or replayed.document_bytes != raw:
            raise ProjectedMotionBundleIntegrityError(
                "Projected bundle identity differs after exact replay"
            )
        return VerifiedProjectedMotionBundle(
            path=snapshot.path,
            clip_id=stored.clip_id,
            projected_motion_sha256=stored.projected_motion_sha256,
            camera_sha256=stored.camera_sha256,
            run_sha256=stored.run_sha256,
            legacy_motion_sha256=stored.legacy_motion_sha256,
            bundle_sha256=stored.bundle_sha256,
            p7_motion_sha256=p7.clip_sha256,
            p7_bundle_sha256=p7.bundle_sha256,
            p7_run_sha256=p7.run_sha256,
            _documents=tuple((name, raw[name]) for name in DOCUMENT_NAMES),
        )
    except ProjectedMotionBundleIntegrityError:
        raise
    except (
        CameraModelError,
        KimodoCameraProjectionError,
        ProjectedMotionBundleContractError,
        ProjectedMotionCompileRunError,
        ProjectedMotionLegacyError,
        SafeInputFileError,
        VerifiedMotionBundleReaderError,
        KeyError,
        OSError,
        OverflowError,
        TypeError,
        UnicodeError,
        ValueError,
    ) as exc:
        raise ProjectedMotionBundleIntegrityError(
            f"Projected motion bundle integrity failed: {exc}"
        ) from exc
