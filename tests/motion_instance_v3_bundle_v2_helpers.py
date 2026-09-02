"""Shared exact P10.6b v2 storage fixture."""

from __future__ import annotations

from contextlib import ExitStack, contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from autospine_workbench.motion_instance_v3_bundle_contract_v2 import (
    build_motion_instance_v3_bundle_contract_v2,
)
from autospine_workbench.motion_instance_v3_bundle_store_v2 import (
    MotionInstanceV3BundleStoreV2,
)
from autospine_workbench.motion_instance_v3_compiler_v2 import (
    compile_motion_instance_v3_v2,
)
from autospine_workbench.motion_instance_v3_prepared_v2 import (
    compile_motion_instance_v3_prepared_core_v2,
    seal_motion_instance_v3_prepared_v2,
)
from autospine_workbench.project_store import ProjectStore
from tests.body_sway_motion_consumer_v2_helpers import (
    consumer_v2_fixture,
    head_observation_v2,
    patched_dynamic_bundle_replay,
    validated_dynamic_documents,
)


STORE_MODULE = "autospine_workbench.motion_instance_v3_bundle_store_v2."


class MotionInstanceV3BundleV2Fixture:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        (
            self.p9_fixture, self.reviewed, self.dynamic,
            self.dynamic_contract,
        ) = consumer_v2_fixture(self.root)
        self.state_root = self.p9_fixture.state_root
        self.project_store = ProjectStore(
            self.root / "workspace", state_root=self.state_root,
            measure_composite_quality=False,
        )
        self.capture = SimpleNamespace(get=lambda _job_id: {})
        with patched_dynamic_bundle_replay(
            self.dynamic, self.dynamic_contract,
        ):
            core = compile_motion_instance_v3_prepared_core_v2(
                self.dynamic, self.reviewed,
            )
        self.observation = head_observation_v2(core._consumer_core)
        self.prepared = seal_motion_instance_v3_prepared_v2(
            core, self.observation, self.observation,
        )
        self.motion = compile_motion_instance_v3_v2(self.prepared)
        self.contract = build_motion_instance_v3_bundle_contract_v2(
            self.prepared, self.motion.document, self.dynamic, self.reviewed,
        )

    @contextmanager
    def publish_gate(self, *, observations=None):
        values = observations or (self.observation, self.observation)
        with patch(
            STORE_MODULE + "require_current_body_sway_dynamic_seam_heads_v2",
            side_effect=values,
        ) as heads:
            yield heads

    @contextmanager
    def historical_replay(self):
        with ExitStack() as stack:
            stack.enter_context(validated_dynamic_documents(
                self.dynamic.source, self.dynamic.probe,
            ))
            stack.enter_context(patched_dynamic_bundle_replay(
                self.dynamic, self.dynamic_contract,
            ))
            yield

    def publish(self):
        with self.publish_gate():
            return MotionInstanceV3BundleStoreV2(
                self.capture, self.project_store,
            ).publish(
                self.prepared, self.motion.document,
                self.dynamic, self.reviewed,
            )


__all__ = ["MotionInstanceV3BundleV2Fixture"]
