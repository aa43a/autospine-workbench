"""Shared exact P10.6b MotionInstance v3 storage fixture."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from autospine_workbench.body_sway_motion_consumer_admission import (
    compile_body_sway_motion_consumer_admission_core,
    seal_body_sway_motion_consumer_admission,
)
from autospine_workbench.motion_instance_v3_bundle_contract import (
    build_motion_instance_v3_bundle_contract,
)
from autospine_workbench.motion_instance_v3_bundle_store import (
    MotionInstanceV3BundleStore,
)
from autospine_workbench.motion_instance_v3_compiler import (
    compile_motion_instance_v3,
)
from tests.body_sway_motion_consumer_helpers import (
    consumer_fixture,
    head_observation,
    patched_probe_replay,
)


class MotionInstanceV3StorageFixture:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.p9_fixture, self.reviewed_bundle, self.probe, self.identity = (
            consumer_fixture(self.root)
        )
        self.state_root = self.p9_fixture.state_root
        with patched_probe_replay(self.probe, self.identity):
            core = compile_body_sway_motion_consumer_admission_core(
                self.probe, self.reviewed_bundle
            )
            observation = head_observation(self.identity)
            self.admission = seal_body_sway_motion_consumer_admission(
                core, observation, observation
            )
            self.motion_instance_v3 = compile_motion_instance_v3(
                self.admission.document, self.reviewed_bundle
            )
            self.contract = build_motion_instance_v3_bundle_contract(
                self.reviewed_bundle.project_id,
                self.admission.document,
                self.motion_instance_v3.document,
                self.reviewed_bundle,
            )

    @contextmanager
    def publish_gate(self, *, observations=None):
        observation = head_observation(self.identity)
        values = observations or (observation, observation)
        with patched_probe_replay(
            self.probe, self.identity
        ), patch(
            "autospine_workbench.motion_instance_v3_bundle_store."
            "require_current_body_sway_dynamic_seam_heads",
            side_effect=values,
        ) as heads:
            yield heads

    def publish(self):
        with self.publish_gate():
            return MotionInstanceV3BundleStore(self.state_root).publish(
                self.reviewed_bundle.project_id,
                self.admission.document,
                self.motion_instance_v3.document,
                self.reviewed_bundle,
            )
