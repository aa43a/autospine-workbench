"""MotionInstance and acyclic retarget-run v1 contract tests."""

from __future__ import annotations

from copy import deepcopy
import json
import math
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

try:
    from jsonschema import Draft202012Validator
except ImportError:  # pragma: no cover - optional test extra
    Draft202012Validator = None

from autospine_workbench.motion_instance_validation import (  # noqa: E402
    MotionInstanceValidationError,
    instance_sha256,
    require_motion_instance,
)
from autospine_workbench.motion_retarget_run import (  # noqa: E402
    RetargetRunValidationError,
    require_retarget_run,
    retarget_compiler,
    retarget_run_document_sha256,
    retarget_run_identity_sha256,
)
from autospine_workbench.motion_target_profile import (  # noqa: E402
    compile_motion_target_profile,
)
from autospine_workbench.resolved_project import canonical_sha256  # noqa: E402
from tests.test_motion_target_profile import pair  # noqa: E402


DURATION = 1_000_000


def target_fixture():
    return compile_motion_target_profile(*pair()).document


def input_fixture(target):
    return {
        "motion_ir_sha256": "1" * 64,
        "motion_bundle_sha256": "2" * 64,
        "motion_run_sha256": "3" * 64,
        "target_profile_sha256": canonical_sha256(target),
    }


def rotation_track(bone_id, middle):
    return {
        "bone_id": bone_id,
        "property": "rotation",
        "keys": [
            {"tick": 0, "value": 0.0},
            {"tick": DURATION // 2, "value": middle},
            {"tick": DURATION, "value": 0.0},
        ],
    }


def instance_fixture(target=None):
    target = target or target_fixture()
    inputs = input_fixture(target)
    identity = retarget_run_identity_sha256(inputs)
    return {
        "format": "autospine-motion-instance",
        "format_version": 1,
        "clip_id": "wave.left",
        "timing": {
            "ticks_per_second": 1_000_000,
            "duration_ticks": DURATION,
            "loop": True,
        },
        "source": {**inputs, "retarget_run_identity_sha256": identity},
        "target_space": {
            "translation": "setup-local-pixel",
            "rotation": "setup-local-degree",
            "positive_rotation": "clockwise",
            "interpolation": "linear",
        },
        "tracks": [
            rotation_track("forearm.left", -20.0),
            {
                "bone_id": "root-pelvis",
                "property": "translation",
                "keys": [
                    {"tick": 0, "value": [0.0, 0.0]},
                    {"tick": DURATION // 2, "value": [1.5, -2.0]},
                    {"tick": DURATION, "value": [0.0, 0.0]},
                ],
            },
            rotation_track("upper-arm.left", 15.0),
        ],
        "markers": [
            {
                "kind": "contact", "limb": "leg.left",
                "proximal_bone_id": "thigh.left",
                "distal_bone_id": "calf.left",
                "start_tick": 0, "end_tick": DURATION,
                "mode": "annotation_only",
            },
            {
                "kind": "contact", "limb": "leg.right",
                "proximal_bone_id": "thigh.right",
                "distal_bone_id": "calf.right",
                "start_tick": 0, "end_tick": DURATION,
                "mode": "annotation_only",
            },
        ],
    }


def run_fixture(instance):
    inputs = {
        field: instance["source"][field]
        for field in (
            "motion_ir_sha256", "motion_bundle_sha256",
            "motion_run_sha256", "target_profile_sha256",
        )
    }
    return {
        "format": "autospine-retarget-run",
        "format_version": 1,
        "run_identity_sha256": retarget_run_identity_sha256(inputs),
        "inputs": inputs,
        "compiler": retarget_compiler(),
        "output": {"instance_sha256": instance_sha256(instance)},
    }


class MotionInstanceContractTests(unittest.TestCase):
    def setUp(self):
        self.target = target_fixture()
        self.instance = instance_fixture(self.target)

    def test_deterministic_instance_binds_exact_target_and_baked_ik_bones(self):
        require_motion_instance(self.instance, target_profile=self.target)
        self.assertEqual(instance_sha256(self.instance), instance_sha256(deepcopy(self.instance)))
        self.assertEqual(
            ["forearm.left", "root-pelvis", "upper-arm.left"],
            [track["bone_id"] for track in self.instance["tracks"]],
        )
        self.assertNotIn("ik_handle", json.dumps(self.instance))

    def test_unknown_fields_and_target_profile_tamper_fail_closed(self):
        for path, value in (
            (("top",), 1),
            (("timing", "fps"), 30),
            (("source", "latest"), True),
            (("tracks", 0, "target_kind"), "ik_handle"),
            (("tracks", 0, "keys", 0, "ease"), "linear"),
            (("markers", 0, "confidence"), 1.0),
        ):
            changed = deepcopy(self.instance)
            cursor = changed
            for part in path[:-1]:
                cursor = cursor[part]
            cursor[path[-1]] = value
            with self.subTest(path=path), self.assertRaises(MotionInstanceValidationError):
                require_motion_instance(changed)

        stale = deepcopy(self.instance)
        stale["source"]["target_profile_sha256"] = "f" * 64
        with self.assertRaisesRegex(MotionInstanceValidationError, "stale"):
            require_motion_instance(stale, target_profile=self.target)

        bad_sha = deepcopy(self.instance)
        bad_sha["source"]["motion_ir_sha256"] = "A" * 64
        with self.assertRaisesRegex(MotionInstanceValidationError, "SHA-256"):
            require_motion_instance(bad_sha)

        bad_inventory = deepcopy(self.target)
        bad_inventory["bones"][0]["bone_id"] = "pelvis-root"
        with self.assertRaises(MotionInstanceValidationError):
            require_motion_instance(self.instance, target_profile=bad_inventory)

    def test_nonfinite_boolean_and_unbounded_numbers_fail(self):
        mutations = (
            lambda value: value["tracks"][0]["keys"][1].update(value=math.nan),
            lambda value: value["tracks"][0]["keys"][1].update(value=math.inf),
            lambda value: value["tracks"][1]["keys"][1]["value"].__setitem__(0, True),
            lambda value: value["tracks"][0]["keys"][1].update(value=1_000_001),
            lambda value: value["timing"].update(duration_ticks=True),
            lambda value: value["tracks"][0]["keys"][1].update(tick=True),
        )
        for mutate in mutations:
            changed = deepcopy(self.instance)
            mutate(changed)
            with self.assertRaises(MotionInstanceValidationError):
                require_motion_instance(changed)

    def test_track_order_loop_span_wrapping_and_ik_conflicts_fail(self):
        changed = deepcopy(self.instance)
        changed["tracks"].reverse()
        with self.assertRaisesRegex(MotionInstanceValidationError, "sorted"):
            require_motion_instance(changed)

        duplicate = deepcopy(self.instance)
        duplicate["tracks"].insert(1, deepcopy(duplicate["tracks"][0]))
        with self.assertRaisesRegex(MotionInstanceValidationError, "sorted"):
            require_motion_instance(duplicate)

        ik_target = deepcopy(self.instance)
        ik_target["tracks"][0].update(bone_id="arm.left", property="target")
        with self.assertRaises(MotionInstanceValidationError):
            require_motion_instance(ik_target)

        no_span = deepcopy(self.instance)
        no_span["tracks"][0]["keys"][0]["tick"] = 1
        with self.assertRaisesRegex(MotionInstanceValidationError, "span"):
            require_motion_instance(no_span)

        non_loop = deepcopy(self.instance)
        non_loop["timing"]["loop"] = False
        non_loop["tracks"][0]["keys"][-1]["value"] = 10.0
        require_motion_instance(non_loop)
        with self.assertRaisesRegex(MotionInstanceValidationError, "match"):
            require_motion_instance({
                **non_loop, "timing": {**non_loop["timing"], "loop": True}
            })

        wrapped = deepcopy(self.instance)
        wrapped["tracks"][0]["keys"][1]["value"] = 181.0
        with self.assertRaisesRegex(MotionInstanceValidationError, "wrapped"):
            require_motion_instance(wrapped)

    def test_contacts_are_half_open_sorted_nonoverlapping_and_handle_bound(self):
        adjacent = deepcopy(self.instance)
        adjacent["markers"] = [
            {**adjacent["markers"][0], "end_tick": DURATION // 2},
            {**adjacent["markers"][0], "start_tick": DURATION // 2},
        ]
        require_motion_instance(adjacent, target_profile=self.target)

        overlap = deepcopy(adjacent)
        overlap["markers"][1]["start_tick"] -= 1
        with self.assertRaisesRegex(MotionInstanceValidationError, "interval"):
            require_motion_instance(overlap)

        wrong_bones = deepcopy(self.instance)
        wrong_bones["markers"][0]["proximal_bone_id"] = "thigh.right"
        with self.assertRaisesRegex(MotionInstanceValidationError, "binding"):
            require_motion_instance(wrong_bones)

        unsorted = deepcopy(self.instance)
        unsorted["markers"].reverse()
        with self.assertRaisesRegex(MotionInstanceValidationError, "sorted"):
            require_motion_instance(unsorted)

    @unittest.skipIf(Draft202012Validator is None, "install the test extra")
    def test_instance_schema_is_valid_and_accepts_fixture(self):
        schema = json.loads(
            (ROOT / "schemas" / "motion-instance-v1.schema.json").read_text("utf-8")
        )
        Draft202012Validator.check_schema(schema)
        self.assertEqual([], list(Draft202012Validator(schema).iter_errors(self.instance)))


class RetargetRunContractTests(unittest.TestCase):
    def setUp(self):
        self.instance = instance_fixture()
        self.run = run_fixture(self.instance)

    def test_run_identity_is_acyclic_and_full_cross_binding_passes(self):
        require_retarget_run(self.run, instance=self.instance)
        expected = retarget_run_identity_sha256(
            self.run["inputs"], self.run["compiler"]
        )
        self.assertEqual(expected, self.run["run_identity_sha256"])

    def test_output_changes_full_document_sha_but_not_run_identity(self):
        changed = deepcopy(self.run)
        changed["output"]["instance_sha256"] = "f" * 64
        require_retarget_run(changed)
        self.assertEqual(
            self.run["run_identity_sha256"], changed["run_identity_sha256"]
        )
        self.assertNotEqual(
            retarget_run_document_sha256(self.run),
            retarget_run_document_sha256(changed),
        )

    def test_inputs_and_compiler_change_identity(self):
        inputs = deepcopy(self.run["inputs"])
        inputs["motion_ir_sha256"] = "a" * 64
        self.assertNotEqual(
            self.run["run_identity_sha256"],
            retarget_run_identity_sha256(inputs, self.run["compiler"]),
        )
        compiler = deepcopy(self.run["compiler"])
        compiler["config"]["numeric_precision_decimals"] = 11
        self.assertNotEqual(
            self.run["run_identity_sha256"],
            retarget_run_identity_sha256(self.run["inputs"], compiler),
        )
        changed = deepcopy(self.run)
        changed["compiler"] = compiler
        changed["run_identity_sha256"] = retarget_run_identity_sha256(
            changed["inputs"], compiler
        )
        with self.assertRaisesRegex(RetargetRunValidationError, "unsupported"):
            require_retarget_run(changed)

    def test_identity_output_and_instance_chain_tamper_fail(self):
        mutations = (
            lambda value: value.update(run_identity_sha256="0" * 64),
            lambda value: value["inputs"].update(motion_bundle_sha256="a" * 64),
            lambda value: value["output"].update(instance_sha256="b" * 64),
        )
        for mutate in mutations:
            changed = deepcopy(self.run)
            mutate(changed)
            with self.assertRaises(RetargetRunValidationError):
                require_retarget_run(changed, instance=self.instance)

        unknown = deepcopy(self.run)
        unknown["output"]["latest"] = True
        with self.assertRaises(RetargetRunValidationError):
            require_retarget_run(unknown)

    @unittest.skipIf(Draft202012Validator is None, "install the test extra")
    def test_retarget_run_schema_is_valid_and_accepts_fixture(self):
        schema = json.loads(
            (ROOT / "schemas" / "retarget-run-v1.schema.json").read_text("utf-8")
        )
        Draft202012Validator.check_schema(schema)
        self.assertEqual([], list(Draft202012Validator(schema).iter_errors(self.run)))


if __name__ == "__main__":
    unittest.main()
