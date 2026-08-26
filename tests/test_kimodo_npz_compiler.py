"""End-to-end in-memory compilation tests for formal Kimodo NPZ."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.kimodo_npz_compiler import (  # noqa: E402
    KimodoNpzCompilerError,
    compile_kimodo_npz_motion,
    kimodo_npz_compiler_config,
)
from autospine_workbench.motion_validation import require_motion_ir  # noqa: E402
from tests.fixtures.kimodo_npz_archive import (  # noqa: E402
    build_npz,
    motion_member_bytes,
)
from tests.kimodo_npz_helpers import map_document, source_document  # noqa: E402


def compile_fixture(*, inventory="complete-v1", **keywords):
    members = motion_member_bytes(inventory=inventory, **keywords)
    raw = build_npz(members)
    source = source_document(raw, inventory=inventory)
    mapping = map_document()
    return raw, source, mapping, compile_kimodo_npz_motion(raw, source, mapping)


def track(document, role, prop="rotation"):
    return next(item for item in document["tracks"]
                if item["target"] == role and item["property"] == prop)


class KimodoNpzCompilerTests(unittest.TestCase):
    def test_compiler_is_deterministic_valid_and_emits_setup_local_motion(self):
        raw, source, mapping, first = compile_fixture()
        second = compile_kimodo_npz_motion(
            raw, deepcopy(source), deepcopy(mapping)
        )
        self.assertEqual(first, second)
        require_motion_ir(first.document)
        self.assertEqual(first.sha256, second.sha256)
        self.assertEqual(15, len([
            item for item in first.document["tracks"]
            if item["property"] == "rotation"
        ]))
        self.assertEqual(0.0, track(first.document, "humanoid.root")["keys"][0]["value"])
        self.assertEqual([0.0, 0.0], track(
            first.document, "humanoid.root", "translation"
        )["keys"][0]["value"])
        self.assertEqual(2, len(first.document["markers"]))
        self.assertIn("skeleton_definition_sha256", kimodo_npz_compiler_config())

    def test_ancillary_arrays_change_source_identity_but_not_motion(self):
        core = compile_fixture(inventory="core-v1")
        complete = compile_fixture(inventory="complete-v1")
        self.assertNotEqual(core[0], complete[0])
        self.assertNotEqual(core[1], complete[1])
        self.assertEqual(core[3].canonical_bytes, complete[3].canonical_bytes)
        self.assertNotEqual(
            core[3].array_inventory_sha256,
            complete[3].array_inventory_sha256,
        )

    def test_explicit_fps_basis_reference_and_clip_change_output(self):
        raw, source, mapping, baseline = compile_fixture()
        cases = []
        fps = deepcopy(source)
        fps["raw_npz"]["frames_per_second"] = {
            "numerator": 24, "denominator": 1,
        }
        cases.append((fps, mapping))
        basis = deepcopy(mapping)
        basis["basis"] = {
            "screen_x": "-X", "screen_y": "-Y", "depth": "-Z",
            "rotation_convention": "validated_matrix_fk_projected_segment",
        }
        cases.append((source, basis))
        reference = deepcopy(mapping)
        reference["root"]["reference_length_meters"] = 2.0
        cases.append((source, reference))
        clip = deepcopy(mapping)
        clip["clip"]["clip_id"] = "kimodo.changed"
        cases.append((source, clip))
        for candidate_source, candidate_map in cases:
            with self.subTest(mapping=candidate_map):
                changed = compile_kimodo_npz_motion(
                    raw, candidate_source, candidate_map
                )
                self.assertNotEqual(baseline.sha256, changed.sha256)

    def test_bad_matrix_posed_or_projection_never_emits_motionir(self):
        cases = (
            {"local_overrides": {
                (1, "LeftArm"): (
                    (2.0, 0.0, 0.0),
                    (0.0, 1.0, 0.0),
                    (0.0, 0.0, 1.0),
                )
            }},
            {"posed_overrides": {(1, "LeftHand"): (9.0, 9.0, 9.0)}},
            {"offset_overrides": {"LeftForeArm": (0.0, 0.0, 0.2)}},
        )
        for keywords in cases:
            members = motion_member_bytes(**keywords)
            raw = build_npz(members)
            with self.subTest(keywords=keywords), self.assertRaises(
                KimodoNpzCompilerError
            ):
                compile_kimodo_npz_motion(
                    raw, source_document(raw), map_document()
                )


if __name__ == "__main__":
    unittest.main()
