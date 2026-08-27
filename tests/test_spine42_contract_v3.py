"""P10.7a pure Spine 4.2 adapter v3 capability contract tests."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for item in (ROOT, SRC):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

import autospine_workbench.spine42_contract_v3 as contract_module  # noqa: E402
from autospine_workbench.motion_instance_v3_contract import (  # noqa: E402
    motion_instance_v3_profile_sha256,
)
from autospine_workbench.reviewed_motion_bundle_upstream import (  # noqa: E402
    require_reviewed_motion_upstreams,
)
from autospine_workbench.spine42_contract import (  # noqa: E402
    SPINE_RUNTIME_VERSION,
)
from autospine_workbench.spine42_contract_v3 import (  # noqa: E402
    Spine42ContractV3Error,
    require_spine42_inputs_v3,
    spine42_target_profile_v3,
    spine42_target_profile_v3_sha256,
)
from tests.body_sway_motion_consumer_helpers import (  # noqa: E402
    patched_probe_replay,
)
from tests.motion_instance_v3_bundle_helpers import (  # noqa: E402
    MotionInstanceV3StorageFixture,
)


class Spine42ContractV3Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory()
        cls.fixture = MotionInstanceV3StorageFixture(
            Path(cls.temporary.name)
        )
        cls.rig = cls.fixture.p9_fixture.mesh.rig
        _base, cls.target = require_reviewed_motion_upstreams(
            cls.fixture.p9_fixture.mesh,
            cls.fixture.p9_fixture.retarget,
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()

    def require(self, **changes):
        values = {
            "rig": self.rig,
            "motion_instance_v3":
                self.fixture.motion_instance_v3.document,
            "admission": self.fixture.admission.document,
            "reviewed_bundle": self.fixture.reviewed_bundle,
            "motion_instance_v3_bundle_sha256":
                self.fixture.contract.bundle_sha256,
            "target_profile": self.target,
        }
        values.update(changes)
        with patched_probe_replay(
            self.fixture.probe, self.fixture.identity
        ):
            return require_spine42_inputs_v3(
                values.pop("rig"), **values
            )

    def test_profile_is_versioned_explicit_isolated_and_hashed(self) -> None:
        profile = spine42_target_profile_v3()
        self.assertEqual("3.0.0", profile["adapter"]["version"])
        self.assertEqual("4.2", profile["spine_major_minor"])
        self.assertEqual(
            SPINE_RUNTIME_VERSION, profile["runtime"]["version"]
        )
        self.assertEqual("fail", profile["unsupported_feature_policy"])
        capabilities = profile["capabilities"]
        self.assertEqual(
            ["region", "weighted_mesh"],
            capabilities["rig_ir_attachments"],
        )
        self.assertEqual({
            "rotation": "setup-local-degree-linear",
            "root_translation": "setup-local-pixel-linear",
            "markers": "contact-boundary-events",
            "draw_order": "full-back-to-front-stepped",
        }, capabilities["motion_instance_v3"])
        profile["adapter"]["version"] = "changed"
        self.assertEqual(
            "3.0.0", spine42_target_profile_v3()["adapter"]["version"]
        )
        self.assertEqual(64, len(spine42_target_profile_v3_sha256()))

    def test_exact_chain_returns_all_hash_bindings_and_calls_v3_replay(self) -> None:
        real = contract_module.require_motion_instance_v3
        with patch.object(
            contract_module, "require_motion_instance_v3", wraps=real
        ) as strict:
            bindings = self.require()
        strict.assert_called_once()
        source = self.fixture.motion_instance_v3.document["source"]
        self.assertEqual(
            self.fixture.motion_instance_v3.sha256,
            bindings.motion_instance_v3_sha256,
        )
        self.assertEqual(
            self.fixture.contract.bundle_sha256,
            bindings.motion_instance_v3_bundle_sha256,
        )
        self.assertEqual(
            motion_instance_v3_profile_sha256(),
            bindings.motion_instance_v3_profile_sha256,
        )
        self.assertEqual(
            source["target_profile_sha256"],
            bindings.target_profile_sha256,
        )
        self.assertEqual(
            spine42_target_profile_v3_sha256(),
            bindings.adapter_profile_sha256,
        )

    def test_bundle_address_is_reconstructed_not_blindly_trusted(self) -> None:
        with self.assertRaisesRegex(
            Spine42ContractV3Error, "exact bundle address"
        ):
            self.require(motion_instance_v3_bundle_sha256="0" * 64)
        with self.assertRaisesRegex(
            Spine42ContractV3Error, "SHA-256 is invalid"
        ):
            self.require(motion_instance_v3_bundle_sha256="latest")

    def test_rig_target_profile_and_project_cross_bindings_fail_closed(self) -> None:
        rig = deepcopy(self.rig)
        rig["bones"][0]["setup"]["rotation_deg"] += 1.0
        with self.assertRaisesRegex(Spine42ContractV3Error, "RigIR differs"):
            self.require(rig=rig)

        target = deepcopy(self.target)
        target["project_id"] = "another-project"
        with self.assertRaisesRegex(
            Spine42ContractV3Error, "Target profile differs"
        ):
            self.require(target_profile=target)

    def test_unknown_adapter_timeline_and_attachment_capabilities_fail_loud(self) -> None:
        profile = spine42_target_profile_v3()
        profile["capabilities"]["motion_instance_v3"]["scale"] = "linear"
        with self.assertRaisesRegex(
            Spine42ContractV3Error, "unknown or unsupported"
        ):
            self.require(adapter_profile=profile)

        motion = self.fixture.motion_instance_v3.document
        motion["tracks"][0]["property"] = "scale"
        with self.assertRaises(Spine42ContractV3Error):
            self.require(motion_instance_v3=motion)

        rig = deepcopy(self.rig)
        rig["attachments"][0]["type"] = "boundingbox"
        with self.assertRaisesRegex(Spine42ContractV3Error, "unsupported"):
            self.require(rig=rig)


if __name__ == "__main__":
    unittest.main()
