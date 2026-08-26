"""P7a gate: a Kimodo-style SOMA77 BVH crosses the existing P5/P6 chain."""

from __future__ import annotations

import math
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.bvh_motion_compile_run import (  # noqa: E402
    build_bvh_motion_compile_run,
)
from autospine_workbench.bvh_motion_compiler import compile_bvh_motion  # noqa: E402
from autospine_workbench.bvh_parser import parse_bvh  # noqa: E402
from autospine_workbench.motion_bundle_reader import (  # noqa: E402
    VerifiedMotionBundleReader,
)
from autospine_workbench.motion_bundle_store import MotionBundleStore  # noqa: E402
from autospine_workbench.motion_roles import (  # noqa: E402
    CANONICAL_BONE_ROLE_ITEMS,
)
from autospine_workbench.png_rgba import RgbaImage, encode_rgba_png  # noqa: E402
from autospine_workbench.spine42_atlas import build_spine42_atlas  # noqa: E402
from tests.p5_p6_pipeline_helpers import run_p5_p6_rig  # noqa: E402
from tests.fixtures.kimodo_soma77_fixture import (  # noqa: E402
    build_soma77_bvh,
    load_soma77_map,
)
from tests.test_motion_three_rig_gate import (  # noqa: E402
    ASYMMETRIC_SETUP,
    rig_from_setup,
    tall_asymmetric_rig,
)


CLIP_ID = "kimodo.soma77.smoke.front"

class KimodoSoma77PipelineGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.state = Path(self.temporary.name) / "state"
        self.raw = build_soma77_bvh()
        self.mapping = load_soma77_map()

    def _verified_motion(self):
        compiled = compile_bvh_motion(self.raw, self.mapping)
        run = build_bvh_motion_compile_run(
            self.raw, self.mapping, compiled.document
        )
        store = MotionBundleStore(self.state)
        first = store.publish(
            compiled.document, run.document,
            raw_bvh=self.raw, bvh_map=self.mapping,
        )
        second = store.publish(
            compiled.document, run.document,
            raw_bvh=self.raw, bvh_map=self.mapping,
        )
        self.assertFalse(first.reused)
        self.assertTrue(second.reused)
        return VerifiedMotionBundleReader(self.state).load(
            first.clip_sha256, first.bundle_sha256
        )

    def test_fixture_preserves_official_double_root_soma77_shape(self):
        document = parse_bvh(self.raw)
        names = tuple(joint.name for joint in document.joints)
        self.assertEqual(78, len(names))
        self.assertEqual(("Root", "Hips"), names[:2])
        self.assertEqual(0, document.joints[1].parent_index)
        self.assertEqual(6, len(document.joints[0].channels))
        self.assertEqual(6, len(document.joints[1].channels))
        self.assertEqual((0.0,) * 6, document.frames[1][:6])
        self.assertAlmostEqual(1.0 / 30.0, document.frame_time_seconds)
        self.assertGreaterEqual(document.frame_count, 2)
        self.assertEqual(CLIP_ID, self.mapping["clip"]["clip_id"])
        self.assertEqual("Hips", self.mapping["root"]["joint_name"])
        mapped = {row["role"] for row in self.mapping["bones"]}
        canonical = {role for role, _bone in CANONICAL_BONE_ROLE_ITEMS}
        self.assertEqual(
            {"humanoid.hip.left", "humanoid.hip.right"},
            canonical - mapped,
        )
        self.assertEqual(set(), mapped - canonical)

    def test_one_source_retargets_three_rigs_and_publishes_spine42(self):
        motion = self._verified_motion()
        self.assertEqual("bvh", motion.source_kind)
        self.assertEqual(CLIP_ID, motion.motion["clip_id"])
        self.assertEqual(self.raw, motion.raw_bvh)
        self.assertEqual(self.mapping, motion.bvh_map)

        image = encode_rgba_png(RgbaImage(
            20, 30, bytes((40, 80, 120, 255)) * (20 * 30)
        ))
        atlas = build_spine42_atlas(
            {"face-image": image}, page_name="skeleton.png"
        )
        setup_rigs = (
            rig_from_setup(ASYMMETRIC_SETUP),
            rig_from_setup(ASYMMETRIC_SETUP, x_offset=37),
            tall_asymmetric_rig(),
        )
        profile_shas, instance_shas, export_shas = set(), set(), set()
        for index, setup_rig in enumerate(setup_rigs):
            with self.subTest(rig=index):
                result = run_p5_p6_rig(
                    self.state, motion, setup_rig, image, atlas
                )
                target = result.target
                retargeted = result.retargeted
                report = result.report
                mesh_report = result.mesh_report
                self.assertEqual("passed", report.document["status"])
                self.assertEqual("passed", mesh_report.document["status"])
                self.assertTrue(all(
                    math.isfinite(float(key["value"]))
                    if not isinstance(key["value"], list)
                    else all(math.isfinite(float(value)) for value in key["value"])
                    for track in retargeted.instance["tracks"]
                    for key in track["keys"]
                ))
                rotation_keys = {
                    track["bone_id"]: [key["value"] for key in track["keys"]]
                    for track in retargeted.instance["tracks"]
                    if track["property"] == "rotation"
                }
                self.assertEqual([0.0, -10.0], rotation_keys["root-pelvis"])
                self.assertEqual([0.0, 0.0], rotation_keys["thigh.left"])
                self.assertEqual([0.0, 0.0], rotation_keys["thigh.right"])

                first = result.first_export
                self.assertFalse(first.reused)
                self.assertTrue(result.second_export.reused)
                verified = result.verified_export
                self.assertEqual("motion", verified.mode)
                self.assertEqual(CLIP_ID, verified.clip_id)
                self.assertEqual(17, len(verified.skeleton_json["bones"]))
                self.assertEqual(
                    {CLIP_ID}, set(verified.skeleton_json["animations"])
                )
                self.assertEqual("passed", verified.export_report["status"])
                self.assertEqual(
                    motion.bundle_sha256,
                    retargeted.instance["source"]["motion_bundle_sha256"],
                )
                profile_shas.add(target.sha256)
                instance_shas.add(retargeted.instance_sha256)
                export_shas.add(first.bundle_sha256)

        self.assertEqual(3, len(profile_shas))
        self.assertEqual(3, len(instance_shas))
        self.assertEqual(3, len(export_shas))


if __name__ == "__main__":
    unittest.main()
