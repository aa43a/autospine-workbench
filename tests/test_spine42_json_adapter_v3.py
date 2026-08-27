"""P10.7a pure MotionInstance v3 to Spine 4.2 projection tests."""

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

from autospine_workbench.resolved_project import canonical_sha256  # noqa: E402
from autospine_workbench.reviewed_motion_bundle_upstream import (  # noqa: E402
    require_reviewed_motion_upstreams,
)
from autospine_workbench.spine42_contract import (  # noqa: E402
    spine42_json_sha256,
)
from autospine_workbench.spine42_contract_v3 import (  # noqa: E402
    Spine42ContractV3Error,
    spine42_target_profile_v3,
    spine42_target_profile_v3_sha256,
)
from autospine_workbench.spine42_contract_v3 import (  # noqa: E402
    Spine42V3InputBindings,
)
from autospine_workbench.spine42_draw_order_offsets import (  # noqa: E402
    apply_spine42_draw_order_offsets,
)
from autospine_workbench.spine42_json_adapter import (  # noqa: E402
    build_spine42_json,
)
from autospine_workbench.spine42_json_adapter_v3 import (  # noqa: E402
    build_spine42_json_bytes_v3,
    build_spine42_json_v3,
    spine42_skeleton_hash_v3,
)
from autospine_workbench.spine42_timeline_projection import (  # noqa: E402
    Spine42TimelineProjectionError,
)
from tests.body_sway_motion_consumer_helpers import (  # noqa: E402
    patched_probe_replay,
)
from tests.motion_instance_v3_bundle_helpers import (  # noqa: E402
    MotionInstanceV3StorageFixture,
)
from tests.test_spine42_json_adapter import rig_fixture  # noqa: E402


class Spine42JsonAdapterV3Tests(unittest.TestCase):
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

    def build(self, **changes) -> dict:
        values = {
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
            return build_spine42_json_v3(self.rig, **values)

    def test_setup_reuses_p6_and_v3_projects_all_admitted_channels(self) -> None:
        setup = build_spine42_json(self.rig)
        result = self.build()
        self.assertEqual(setup["bones"], result["bones"])
        self.assertEqual(setup["slots"], result["slots"])
        self.assertEqual(setup["skins"], result["skins"])

        instance = self.fixture.motion_instance_v3.document
        animation = result["animations"][instance["clip_id"]]
        self.assertEqual(
            -5.0,
            animation["bones"]["root-pelvis"]["rotate"][-1]["value"],
        )
        input_root = next(
            track for track in instance["tracks"]
            if track["property"] == "translation"
        )
        output_root = animation["bones"][input_root["bone_id"]]["translate"]
        self.assertEqual(input_root["keys"][-1]["value"][0], output_root[-1]["x"])
        self.assertEqual(-input_root["keys"][-1]["value"][1], output_root[-1]["y"])
        self.assertEqual(4, len(animation["events"]))
        self.assertEqual(set(result["events"]), {
            "contact.leg.left.start", "contact.leg.left.end",
            "contact.leg.right.start", "contact.leg.right.end",
        })

        draw_order = instance["draw_order"]
        setup_slots = tuple(draw_order["setup_slot_ids"])
        for frame, key in zip(
            animation["drawOrder"], draw_order["keys"], strict=True
        ):
            self.assertEqual(
                tuple(key["slot_ids"]),
                apply_spine42_draw_order_offsets(
                    setup_slots, frame.get("offsets", [])
                ),
            )

    def test_skeleton_hash_binds_all_v3_adapter_sources(self) -> None:
        result = self.build()
        instance = self.fixture.motion_instance_v3.document
        expected = canonical_sha256({
            "adapter_profile": spine42_target_profile_v3(),
            "adapter_profile_sha256": spine42_target_profile_v3_sha256(),
            "rig_sha256": canonical_sha256(self.rig),
            "motion_instance_v3_sha256": canonical_sha256(instance),
            "motion_instance_v3_bundle_sha256":
                self.fixture.contract.bundle_sha256,
            "motion_instance_v3_profile_sha256": instance["source"][
                "motion_instance_v3_profile_sha256"
            ],
            "target_profile_sha256": canonical_sha256(self.target),
        })
        self.assertEqual(expected, result["skeleton"]["hash"])

    def test_skeleton_hash_rejects_profile_identity_substitution(self) -> None:
        instance = self.fixture.motion_instance_v3.document
        bindings = Spine42V3InputBindings(
            adapter_profile_sha256="f" * 64,
            rig_sha256=canonical_sha256(self.rig),
            motion_instance_v3_sha256=canonical_sha256(instance),
            motion_instance_v3_bundle_sha256=self.fixture.contract.bundle_sha256,
            motion_instance_v3_profile_sha256=instance["source"][
                "motion_instance_v3_profile_sha256"
            ],
            target_profile_sha256=canonical_sha256(self.target),
        )
        with self.assertRaisesRegex(
            Spine42ContractV3Error, "profile identity differs"
        ):
            spine42_skeleton_hash_v3(bindings)

    def test_canonical_bytes_are_deterministic_and_inputs_stay_immutable(self) -> None:
        rig_before = deepcopy(self.rig)
        instance = self.fixture.motion_instance_v3.document
        admission = self.fixture.admission.document
        before_instance, before_admission = deepcopy(instance), deepcopy(admission)
        with patched_probe_replay(
            self.fixture.probe, self.fixture.identity
        ):
            first = build_spine42_json_bytes_v3(
                self.rig,
                motion_instance_v3=instance,
                admission=admission,
                reviewed_bundle=self.fixture.reviewed_bundle,
                motion_instance_v3_bundle_sha256=
                    self.fixture.contract.bundle_sha256,
                target_profile=self.target,
            )
            second = build_spine42_json_bytes_v3(
                {key: self.rig[key] for key in reversed(self.rig)},
                motion_instance_v3=deepcopy(instance),
                admission=deepcopy(admission),
                reviewed_bundle=self.fixture.reviewed_bundle,
                motion_instance_v3_bundle_sha256=
                    self.fixture.contract.bundle_sha256,
                target_profile=deepcopy(self.target),
            )
        self.assertEqual(first, second)
        self.assertEqual(self.rig, rig_before)
        self.assertEqual(instance, before_instance)
        self.assertEqual(admission, before_admission)

    def test_projection_errors_are_wrapped_and_never_silently_dropped(self) -> None:
        with patch(
            "autospine_workbench.spine42_json_adapter_v3."
            "project_spine42_motion",
            side_effect=Spine42TimelineProjectionError(
                "unsupported timeline"
            ),
        ), self.assertRaisesRegex(
            Spine42ContractV3Error, "unsupported timeline"
        ):
            self.build()

    def test_existing_p6_adapter_hash_sentinels_remain_unchanged(self) -> None:
        old_rig = rig_fixture()
        self.assertEqual(
            "06bbbb1ffa5633890b1a95d09a2f24a25611e03e78b7ffafeba6b65aac657d6b",
            spine42_json_sha256(build_spine42_json(old_rig)),
        )


if __name__ == "__main__":
    unittest.main()
