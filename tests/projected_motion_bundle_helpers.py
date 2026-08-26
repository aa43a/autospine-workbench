"""Shared end-to-end fixture for exact P7-to-P8 bundle tests."""

from __future__ import annotations

from pathlib import Path

from autospine_workbench.kimodo_camera_projection import (
    compile_verified_kimodo_projection,
)
from autospine_workbench.kimodo_npz_compile_run import (
    build_kimodo_npz_compile_run,
)
from autospine_workbench.kimodo_npz_compiler import compile_kimodo_npz_motion
from autospine_workbench.motion_bundle_reader import VerifiedMotionBundleReader
from autospine_workbench.motion_bundle_store import MotionBundleStore
from autospine_workbench.projected_motion_bundle_store import (
    ProjectedMotionBundleStore,
)
from autospine_workbench.projected_motion_compile_run import (
    build_projected_motion_compile_run,
)
from autospine_workbench.projected_motion_legacy import (
    compile_projected_motion_to_motion_ir,
)
from tests.fixtures.kimodo_npz_archive import build_npz, motion_member_bytes
from tests.kimodo_npz_helpers import map_document, source_document
from tests.test_kimodo_camera_projection import camera_document


class ProjectedBundleFixture:
    def __init__(
        self, root: Path, *, motion_kwargs: dict | None = None
    ):
        self.state = Path(root) / "state"
        self.raw = build_npz(motion_member_bytes(**dict(motion_kwargs or {})))
        self.source = source_document(self.raw)
        self.mapping = map_document()
        self.p7_compiled = compile_kimodo_npz_motion(
            self.raw, self.source, self.mapping
        )
        self.p7_run = build_kimodo_npz_compile_run(
            self.raw, self.source, self.mapping, self.p7_compiled.document
        )
        self.p7_published = MotionBundleStore(self.state).publish(
            self.p7_compiled.document,
            self.p7_run.document,
            raw_npz=self.raw,
            kimodo_source=self.source,
            kimodo_map=self.mapping,
        )
        self.p7 = VerifiedMotionBundleReader(self.state).load(
            self.p7_published.clip_sha256,
            self.p7_published.bundle_sha256,
        )
        self.camera = camera_document(self.mapping)
        self.projected = compile_verified_kimodo_projection(
            self.p7, self.camera
        )
        self.legacy = compile_projected_motion_to_motion_ir(
            self.projected.document
        )
        self.run = build_projected_motion_compile_run(
            self.p7, self.camera, self.projected, self.legacy
        )

    def publish(self):
        return ProjectedMotionBundleStore(self.state).publish(
            self.camera, self.projected.document, self.run.document
        )
