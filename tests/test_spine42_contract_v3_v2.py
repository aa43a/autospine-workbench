from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
for item in (ROOT, ROOT / "src"):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

from autospine_workbench.spine42_contract_v3 import (  # noqa: E402
    Spine42V3InputBindings, spine42_target_profile_v3_sha256,
)
from autospine_workbench.spine42_contract_v3_v2 import (  # noqa: E402
    SOURCE_CONTRACT, Spine42ContractV3V2Error,
    Spine42V3InputBindingsV2, require_spine42_inputs_v3_v2,
    spine42_source_contract_v3_v2,
    spine42_source_contract_v3_v2_sha256,
    spine42_target_profile_v3_v2,
    spine42_target_profile_v3_v2_sha256,
)
import autospine_workbench.spine42_contract_v3_v2 as contract_v2  # noqa: E402
from autospine_workbench.resolved_project import canonical_sha256  # noqa: E402
from autospine_workbench.spine42_json_adapter import (  # noqa: E402
    build_spine42_json,
)
from autospine_workbench.spine42_json_adapter_v3 import (  # noqa: E402
    spine42_skeleton_hash_v3,
)
from autospine_workbench.spine42_json_adapter_v3_v2 import (  # noqa: E402
    build_spine42_json_v3_v2, spine42_skeleton_hash_v3_v2,
)
from tests.spine42_v3_v2_helpers import Spine42V3V2Fixture  # noqa: E402


class Spine42ContractV3V2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.fixture = Spine42V3V2Fixture(Path(cls.temporary.name))

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def require(self, **changes):
        values = {
            "rig": self.fixture.mesh.rig,
            "motion_bundle": self.fixture.motion_bundle,
            "reviewed_bundle": self.fixture.reviewed,
            "target_profile": self.fixture.target,
        }
        values.update(changes)
        return require_spine42_inputs_v3_v2(
            values.pop("rig"), **values,
        )

    def test_profiles_are_detached_immutable_and_v1_isolated(self):
        with self.assertRaises(TypeError):
            SOURCE_CONTRACT["version"] = 1
        source = spine42_source_contract_v3_v2()
        profile = spine42_target_profile_v3_v2()
        source["version"] = 99
        profile["source_contract"]["version"] = 99
        self.assertEqual(2, spine42_source_contract_v3_v2()["version"])
        self.assertEqual(2, spine42_target_profile_v3_v2()[
            "source_contract"
        ]["version"])
        self.assertNotEqual(spine42_target_profile_v3_sha256(),
                            spine42_target_profile_v3_v2_sha256())
        self.assertEqual(64, len(spine42_source_contract_v3_v2_sha256()))

    def test_reader_issued_v2_bundle_is_mandatory_and_cross_bound(self):
        bindings = self.require()
        self.assertIs(type(bindings), Spine42V3InputBindingsV2)
        self.assertEqual(self.fixture.motion_bundle.bundle_sha256,
                         bindings.motion_instance_v3_bundle_sha256)
        with self.assertRaises(Spine42ContractV3V2Error):
            self.require(motion_bundle=object())

    def test_projection_reuses_setup_and_emits_all_motion_channels(self):
        setup = build_spine42_json(self.fixture.mesh.rig)
        result = build_spine42_json_v3_v2(
            self.fixture.mesh.rig,
            motion_bundle=self.fixture.motion_bundle,
            reviewed_bundle=self.fixture.reviewed,
            target_profile=self.fixture.target,
        )
        self.assertEqual(setup["bones"], result["bones"])
        self.assertEqual(setup["slots"], result["slots"])
        self.assertEqual(setup["skins"], result["skins"])
        instance = self.fixture.motion_bundle.document(
            "motion-instance-v3.json"
        )
        animation = result["animations"][instance["clip_id"]]
        self.assertTrue(animation["bones"])
        self.assertEqual(2 * len(instance["markers"]),
                         len(animation["events"]))
        self.assertTrue(animation["drawOrder"])

    def test_v2_skeleton_identity_cannot_alias_frozen_v1(self):
        bindings = self.require()
        v2_hash = spine42_skeleton_hash_v3_v2(bindings)
        v1_hash = spine42_skeleton_hash_v3(Spine42V3InputBindings(
            spine42_target_profile_v3_sha256(), bindings.rig_sha256,
            bindings.motion_instance_v3_sha256,
            bindings.motion_instance_v3_bundle_sha256,
            bindings.motion_instance_v3_profile_sha256,
            bindings.target_profile_sha256,
        ))
        self.assertNotEqual(v1_hash, v2_hash)

    def test_admission_p3_bundle_crosswire_fails_closed(self):
        instance = self.fixture.motion_bundle.document(
            "motion-instance-v3.json"
        )
        admission = self.fixture.motion_bundle.document(
            "body-sway-motion-consumer-admission-v2.json"
        )
        run = self.fixture.motion_bundle.document("run-manifest-v2.json")
        admission["source"]["p3_bundle_sha256"] = "f" * 64
        with self.assertRaisesRegex(
            Spine42ContractV3V2Error, "P3 source",
        ):
            contract_v2._require_cross_bindings(
                self.fixture.mesh.rig, self.fixture.target,
                self.fixture.reviewed, self.fixture.motion_bundle,
                instance, admission, run,
                canonical_sha256(self.fixture.mesh.rig),
                canonical_sha256(self.fixture.target),
            )

    def test_admission_p9_identity_rejects_missing_extra_and_crosswire(self):
        instance = self.fixture.motion_bundle.document(
            "motion-instance-v3.json"
        )
        original = self.fixture.motion_bundle.document(
            "body-sway-motion-consumer-admission-v2.json"
        )
        run = self.fixture.motion_bundle.document("run-manifest-v2.json")
        cases = []
        missing = deepcopy(original)
        missing["source"]["p9"].pop(next(iter(self.fixture.reviewed.identities)))
        cases.append(missing)
        extra = deepcopy(original)
        extra["source"]["p9"]["unexpected_sha256"] = "e" * 64
        cases.append(extra)
        crossed = deepcopy(original)
        crossed["source"]["p9"]["bundle_sha256"] = "f" * 64
        cases.append(crossed)
        for admission in cases:
            with self.subTest(keys=set(admission["source"]["p9"])), \
                    self.assertRaisesRegex(
                        Spine42ContractV3V2Error, "P9 source",
                    ):
                contract_v2._require_cross_bindings(
                    self.fixture.mesh.rig, self.fixture.target,
                    self.fixture.reviewed, self.fixture.motion_bundle,
                    instance, admission, run,
                    canonical_sha256(self.fixture.mesh.rig),
                    canonical_sha256(self.fixture.target),
                )

    def test_v1_input_validator_is_never_called(self):
        with patch(
            "autospine_workbench.spine42_contract_v3."
            "require_spine42_inputs_v3",
            side_effect=AssertionError("frozen v1 called"),
        ):
            build_spine42_json_v3_v2(
                self.fixture.mesh.rig,
                motion_bundle=self.fixture.motion_bundle,
                reviewed_bundle=self.fixture.reviewed,
                target_profile=deepcopy(self.fixture.target),
            )


if __name__ == "__main__":
    unittest.main()
