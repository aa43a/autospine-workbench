"""P7a gate: a Kimodo-style SOMA77 BVH crosses the existing P5/P6 chain."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import hashlib
import json
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
from autospine_workbench.motion_mesh_regression import (  # noqa: E402
    build_motion_mesh_regression,
)
from autospine_workbench.motion_retarget_bundle_store import (  # noqa: E402
    MotionRetargetBundleStore,
)
from autospine_workbench.motion_retarget_compiler import (  # noqa: E402
    compile_motion_instance,
)
from autospine_workbench.motion_retarget_report import (  # noqa: E402
    build_motion_retarget_report,
)
from autospine_workbench.motion_roles import (  # noqa: E402
    CANONICAL_BONE_ROLE_ITEMS,
)
from autospine_workbench.motion_target_profile import (  # noqa: E402
    compile_motion_target_profile,
)
from autospine_workbench.png_rgba import RgbaImage, encode_rgba_png  # noqa: E402
from autospine_workbench.resolved_project import canonical_sha256  # noqa: E402
from autospine_workbench.spine42_atlas import build_spine42_atlas  # noqa: E402
from autospine_workbench.spine42_bundle_integrity import (  # noqa: E402
    VerifiedSpine42BundleReader,
)
from autospine_workbench.spine42_bundle_store import Spine42BundleStore  # noqa: E402
from autospine_workbench.spine42_json_adapter import build_spine42_json  # noqa: E402
from tests.fixtures.kimodo_soma77_fixture import (  # noqa: E402
    build_soma77_bvh,
    load_soma77_map,
)
from tests.test_motion_target_profile import ik_fixture, mesh_fixture  # noqa: E402
from tests.test_motion_three_rig_gate import (  # noqa: E402
    ASYMMETRIC_SETUP,
    rig_from_setup,
    tall_asymmetric_rig,
)
from tests.test_spine42_json_adapter import rig_fixture  # noqa: E402


CLIP_ID = "kimodo.soma77.smoke.front"


def _region_rig(setup_rig: dict, image_sha256: str) -> dict:
    rig = rig_fixture()
    setup_by_id = {
        bone["id"]: deepcopy(bone["setup"])
        for bone in setup_rig["bones"]
    }
    for bone in rig["bones"]:
        bone["setup"] = setup_by_id[bone["id"]]
    face = deepcopy(rig["attachments"][0])
    face["image_sha256"] = image_sha256
    rig["capabilities"] = ["region_attachment", "setup_draw_order"]
    rig["slots"] = [deepcopy(rig["slots"][0])]
    rig["attachments"] = [face]
    rig["skins"] = {"default": {"face": ["face-image"]}}
    return rig


def _exact_target(rig: dict):
    provisional = mesh_fixture(rig, converted=False)
    documents = dict(provisional._document_json_items)
    mesh = replace(
        provisional,
        rig_sha256=canonical_sha256(rig),
        run_sha256=canonical_sha256(json.loads(documents["run-manifest.json"])),
        probes_sha256=canonical_sha256(json.loads(documents["probes.json"])),
        visuals_sha256=canonical_sha256(json.loads(documents["visuals.json"])),
    )
    return mesh, compile_motion_target_profile(ik_fixture(mesh), mesh)


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
        image_sha = hashlib.sha256(image).hexdigest()
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
                rig = _region_rig(setup_rig, image_sha)
                mesh, target = _exact_target(rig)
                retargeted = compile_motion_instance(motion, target)
                report = build_motion_retarget_report(
                    motion, target, retargeted
                )
                mesh_report = build_motion_mesh_regression(
                    retargeted.instance, target.document, mesh
                )
                p5 = MotionRetargetBundleStore(self.state).publish(
                    target.document["project_id"], target.document,
                    retargeted.instance, retargeted.run,
                    report.document, mesh_report.document,
                )
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

                skeleton = build_spine42_json(
                    rig, motion_instance=retargeted.instance,
                    target_profile=target.document,
                )
                p3_source = {
                    "rig_sha256": target.document["source"]["p3"]["rig_sha256"],
                    "bundle_sha256": target.document["source"]["p3"]["bundle_sha256"],
                }
                p5_source = {
                    "target_profile_sha256": target.sha256,
                    "motion_instance_sha256": retargeted.instance_sha256,
                    "bundle_sha256": p5.bundle_sha256,
                    "clip_id": CLIP_ID,
                }
                store = Spine42BundleStore(self.state)
                first = store.publish(
                    target.document["project_id"], p3_source, skeleton,
                    atlas.atlas_bytes, atlas.png_bytes,
                    {"face-image": image_sha}, p5_source=p5_source,
                )
                second = store.publish(
                    target.document["project_id"], p3_source, skeleton,
                    atlas.atlas_bytes, atlas.png_bytes,
                    {"face-image": image_sha}, p5_source=p5_source,
                )
                self.assertFalse(first.reused)
                self.assertTrue(second.reused)
                verified = VerifiedSpine42BundleReader(self.state).load(
                    first.project_id, first.skeleton_json_sha256,
                    first.bundle_sha256,
                )
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
