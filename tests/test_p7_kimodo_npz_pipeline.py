"""P7 gate: formal Kimodo NPZ crosses three P5 rigs and the P6 adapter."""

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

from autospine_workbench.kimodo_npz_compile_run import (  # noqa: E402
    build_kimodo_npz_compile_run,
)
from autospine_workbench.kimodo_npz_compiler import (  # noqa: E402
    compile_kimodo_npz_motion,
)
from autospine_workbench.motion_bundle_contract import (  # noqa: E402
    KIMODO_DOCUMENT_NAMES,
)
from autospine_workbench.motion_bundle_reader import (  # noqa: E402
    VerifiedMotionBundleReader,
)
from autospine_workbench.motion_bundle_store import MotionBundleStore  # noqa: E402
from autospine_workbench.png_rgba import RgbaImage, encode_rgba_png  # noqa: E402
from autospine_workbench.spine42_atlas import build_spine42_atlas  # noqa: E402
from tests.fixtures.kimodo_npz_archive import (  # noqa: E402
    build_npz,
    motion_member_bytes,
)
from tests.kimodo_npz_helpers import (  # noqa: E402
    map_document,
    source_document,
)
from tests.p5_p6_pipeline_helpers import run_p5_p6_rig  # noqa: E402
from tests.test_motion_three_rig_gate import (  # noqa: E402
    ASYMMETRIC_SETUP,
    rig_from_setup,
    tall_asymmetric_rig,
)


CLIP_ID = "kimodo.soma77.synthetic"


def _track_values(instance: dict, bone_id: str, property_name: str):
    track = next(
        item for item in instance["tracks"]
        if item["bone_id"] == bone_id and item["property"] == property_name
    )
    return [key["value"] for key in track["keys"]]


class KimodoNpzPipelineGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.state = Path(self.temporary.name) / "state"
        self.raw = build_npz(motion_member_bytes())
        self.source = source_document(self.raw)
        self.mapping = map_document()

    def _verified_motion(self):
        compiled = compile_kimodo_npz_motion(
            self.raw, self.source, self.mapping
        )
        run = build_kimodo_npz_compile_run(
            self.raw, self.source, self.mapping, compiled.document
        )
        store = MotionBundleStore(self.state)
        first = store.publish(
            compiled.document, run.document,
            raw_npz=self.raw, kimodo_source=self.source,
            kimodo_map=self.mapping,
        )
        second = store.publish(
            compiled.document, run.document,
            raw_npz=self.raw, kimodo_source=self.source,
            kimodo_map=self.mapping,
        )
        self.assertFalse(first.reused)
        self.assertTrue(second.reused)
        motion = VerifiedMotionBundleReader(self.state).load(
            first.clip_sha256, first.bundle_sha256
        )
        self.assertEqual("kimodo_npz", motion.source_kind)
        self.assertEqual(KIMODO_DOCUMENT_NAMES, motion.inventory)
        self.assertEqual(self.raw, motion.raw_npz)
        self.assertEqual(self.source, motion.kimodo_source)
        self.assertEqual(self.mapping, motion.kimodo_map)
        return motion

    def test_formal_npz_retargets_three_rigs_and_publishes_spine42(self):
        motion = self._verified_motion()
        self.assertEqual(CLIP_ID, motion.motion["clip_id"])
        self.assertEqual(
            [("leg.left", 0, 66667), ("leg.right", 33333, 66667)],
            [
                (marker["limb"], marker["start_tick"], marker["end_tick"])
                for marker in motion.motion["markers"]
            ],
        )

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
        profile_shas, instance_shas = set(), set()
        p5_shas, export_shas = set(), set()

        for index, setup_rig in enumerate(setup_rigs):
            with self.subTest(rig=index):
                result = run_p5_p6_rig(
                    self.state, motion, setup_rig, image, atlas
                )
                instance = result.retargeted.instance
                verified = result.verified_export
                self.assertEqual("passed", result.report.document["status"])
                self.assertEqual(
                    "passed", result.mesh_report.document["status"]
                )
                self.assertTrue(all(
                    math.isfinite(float(value))
                    for track in instance["tracks"]
                    for key in track["keys"]
                    for value in (
                        key["value"]
                        if isinstance(key["value"], list)
                        else [key["value"]]
                    )
                ))
                self.assertEqual(
                    [0.0, -10.0, 5.0],
                    _track_values(instance, "root-pelvis", "rotation"),
                )
                root_translation = _track_values(
                    instance, "root-pelvis", "translation"
                )
                self.assertEqual([0.0, 0.0], root_translation[0])
                self.assertGreater(root_translation[1][0], 0.0)
                self.assertGreater(
                    root_translation[2][0], root_translation[1][0]
                )
                self.assertEqual(
                    [0.0, 0.0, 0.0],
                    [value[1] for value in root_translation],
                )
                self.assertEqual(
                    [0.0, -20.0, 10.0],
                    _track_values(instance, "upper-arm.left", "rotation"),
                )
                self.assertEqual(
                    [0.0, 15.0, 0.0],
                    _track_values(instance, "forearm.right", "rotation"),
                )
                self.assertEqual(
                    [("leg.left", 0, 66667),
                     ("leg.right", 33333, 66667)],
                    [
                        (marker["limb"], marker["start_tick"],
                         marker["end_tick"])
                        for marker in instance["markers"]
                    ],
                )
                self.assertEqual(
                    motion.bundle_sha256,
                    instance["source"]["motion_bundle_sha256"],
                )
                self.assertFalse(result.first_export.reused)
                self.assertTrue(result.second_export.reused)
                self.assertEqual("motion", verified.mode)
                self.assertEqual(CLIP_ID, verified.clip_id)
                self.assertEqual(17, len(verified.skeleton_json["bones"]))
                self.assertEqual(
                    {CLIP_ID}, set(verified.skeleton_json["animations"])
                )
                self.assertEqual("passed", verified.export_report["status"])

                profile_shas.add(result.target.sha256)
                instance_shas.add(result.retargeted.instance_sha256)
                p5_shas.add(result.p5_bundle.bundle_sha256)
                export_shas.add(result.first_export.bundle_sha256)

        self.assertEqual(3, len(profile_shas))
        self.assertEqual(3, len(instance_shas))
        self.assertEqual(3, len(p5_shas))
        self.assertEqual(3, len(export_shas))


if __name__ == "__main__":
    unittest.main()
