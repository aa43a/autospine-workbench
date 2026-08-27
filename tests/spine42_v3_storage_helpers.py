"""Integrated exact P3/P5/P9/MIv3 fixture for P10.7 tests."""

from __future__ import annotations

from contextlib import ExitStack, contextmanager
from pathlib import Path
from unittest.mock import patch

from autospine_workbench.body_sway_motion_consumer_admission import (
    compile_body_sway_motion_consumer_admission_core,
    seal_body_sway_motion_consumer_admission,
)
from autospine_workbench.motion_instance_v3_bundle_reader import (
    VerifiedMotionInstanceV3BundleReader,
)
from autospine_workbench.motion_instance_v3_bundle_store import (
    MotionInstanceV3BundleStore,
)
from autospine_workbench.motion_instance_v3_compiler import (
    compile_motion_instance_v3,
)
from tests.body_sway_motion_consumer_helpers import (
    certified_probe,
    head_identity,
    head_observation,
    patched_probe_replay,
)
from tests.p10_candidate_helpers import P10PersistedFixture


class Spine42V3StorageFixture:
    """Publish the full exact chain required by the pure P10.7 pipeline."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.p10 = P10PersistedFixture(self.root)
        self.state_root = self.p10.state
        self.reviewed = self.p10.reviewed
        self.project_id = self.reviewed.project_id
        self.probe = certified_probe(self.reviewed)
        self.identity = head_identity(self.project_id)
        self.observation = head_observation(self.identity)
        with self.replay_gate(), patch(
            "autospine_workbench.motion_instance_v3_bundle_store."
            "require_current_body_sway_dynamic_seam_heads",
            return_value=self.observation,
        ):
            core = compile_body_sway_motion_consumer_admission_core(
                self.probe, self.reviewed
            )
            self.admission = seal_body_sway_motion_consumer_admission(
                core, self.observation, self.observation
            )
            self.motion_instance_v3 = compile_motion_instance_v3(
                self.admission.document, self.reviewed
            )
            self.published_v3 = MotionInstanceV3BundleStore(
                self.state_root
            ).publish(
                self.project_id,
                self.admission.document,
                self.motion_instance_v3.document,
                self.reviewed,
            )
            self.verified_v3 = VerifiedMotionInstanceV3BundleReader(
                self.state_root
            ).load(
                self.project_id,
                self.published_v3.motion_instance_v3_sha256,
                self.published_v3.bundle_sha256,
            )

    @contextmanager
    def replay_gate(self):
        """Admit the compact certified dynamic probe at strict boundaries."""

        with patched_probe_replay(self.probe, self.identity):
            yield

    @contextmanager
    def compile_gate(self, *, observations=None):
        """Admit the probe and provide deterministic current-head snapshots."""

        values = observations
        with ExitStack() as stack:
            stack.enter_context(self.replay_gate())
            current = stack.enter_context(patch(
                "autospine_workbench.spine42_v3_current_heads."
                "require_current_body_sway_dynamic_seam_heads",
                side_effect=values,
                return_value=self.observation,
            ))
            yield current


__all__ = ["Spine42V3StorageFixture"]
