"""Pure P10.7a Spine 4.2 v3 bundle, tamper, and schema tests."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.png_rgba import RgbaImage, encode_rgba_png  # noqa: E402
from autospine_workbench.resolved_project import canonical_sha256  # noqa: E402
from autospine_workbench.spine42_bundle_contract import (  # noqa: E402
    spine42_bundle_address_sha256,
)
from autospine_workbench.spine42_contract_v3 import (  # noqa: E402
    spine42_target_profile_v3,
    spine42_target_profile_v3_sha256,
)
from autospine_workbench.spine42_v3_bundle_contract import (  # noqa: E402
    DOCUMENT_NAMES,
    Spine42V3BundleContractError,
    build_spine42_v3_bundle_contract,
    spine42_v3_bundle_address_sha256,
)
from autospine_workbench.spine42_v3_export_evidence import (  # noqa: E402
    AUTHORITY,
    RELEASE_GATE,
)
from tests.spine42_bundle_helpers import bundle_inputs  # noqa: E402


def _inputs() -> dict:
    base = bundle_inputs(motion=True)
    p3 = deepcopy(base["p3_source"])
    motion = {
        "motion_instance_v3_sha256": "6" * 64,
        "bundle_sha256": "7" * 64,
        "admission_sha256": "8" * 64,
        "profile_sha256": "9" * 64,
        "target_profile_sha256": base["p5_source"][
            "target_profile_sha256"
        ],
    }
    skeleton = deepcopy(base["skeleton_json"])
    skeleton["animations"][base["p5_source"]["clip_id"]][
        "drawOrder"
    ] = [{"time": 0.0}]
    skeleton["skeleton"]["hash"] = canonical_sha256({
        "adapter_profile": spine42_target_profile_v3(),
        "adapter_profile_sha256": spine42_target_profile_v3_sha256(),
        "rig_sha256": p3["rig_sha256"],
        "motion_instance_v3_sha256": motion[
            "motion_instance_v3_sha256"
        ],
        "motion_instance_v3_bundle_sha256": motion["bundle_sha256"],
        "motion_instance_v3_profile_sha256": motion["profile_sha256"],
        "target_profile_sha256": motion["target_profile_sha256"],
    })
    return {
        "project_id": base["project_id"],
        "clip_id": base["p5_source"]["clip_id"],
        "p3_source": p3,
        "motion_instance_v3_source": motion,
        "skeleton_json": skeleton,
        "atlas_bytes": base["atlas_bytes"],
        "png_bytes": base["png_bytes"],
        "source_image_sha256s": deepcopy(base["source_image_sha256s"]),
    }


def _build(values: dict):
    return build_spine42_v3_bundle_contract(
        values["project_id"], values["clip_id"], values["p3_source"],
        values["motion_instance_v3_source"], values["skeleton_json"],
        values["atlas_bytes"], values["png_bytes"],
        values["source_image_sha256s"],
    )


class Spine42V3BundleContractTests(unittest.TestCase):
    def test_contract_is_deterministic_fixed_and_release_blocked(self):
        values = _inputs()
        first = _build(values)
        reordered = deepcopy(values)
        reordered["p3_source"] = dict(
            reversed(reordered["p3_source"].items())
        )
        reordered["motion_instance_v3_source"] = dict(
            reversed(reordered["motion_instance_v3_source"].items())
        )
        reordered["source_image_sha256s"] = dict(
            reversed(reordered["source_image_sha256s"].items())
        )
        second = _build(reordered)

        self.assertEqual(first, second)
        self.assertEqual(DOCUMENT_NAMES, first.inventory)
        self.assertEqual(15, len(first.identities))
        run = json.loads(first.document_bytes["run-manifest.json"])
        report = json.loads(first.document_bytes["export-report.json"])
        self.assertEqual(spine42_target_profile_v3(), run["adapter_profile"])
        self.assertEqual(
            spine42_target_profile_v3_sha256(),
            run["adapter_profile_sha256"],
        )
        self.assertEqual(values["p3_source"], run["inputs"]["p3"])
        self.assertEqual(
            values["motion_instance_v3_source"],
            run["inputs"]["motion_instance_v3"],
        )
        expected_authority = dict(AUTHORITY)
        expected_gate = {
            "status": RELEASE_GATE["status"],
            "reason_codes": list(RELEASE_GATE["reason_codes"]),
        }
        self.assertEqual(expected_authority, run["authority"])
        self.assertEqual(expected_authority, report["authority"])
        self.assertEqual(expected_gate, run["release_gate"])
        self.assertEqual(expected_gate, report["release_gate"])
        self.assertEqual(
            {"spine_adapter_emitted"},
            {name for name, granted in run["authority"].items() if granted},
        )

    def test_public_authority_constants_cannot_be_mutated(self):
        with self.assertRaises(TypeError):
            AUTHORITY["release_authority"] = True
        with self.assertRaises(TypeError):
            RELEASE_GATE["status"] = "passed"
        with self.assertRaises(TypeError):
            RELEASE_GATE["reason_codes"][0] = "released"
        run = json.loads(_build(_inputs()).document_bytes["run-manifest.json"])
        self.assertFalse(run["authority"]["release_authority"])
        self.assertEqual("blocked", run["release_gate"]["status"])

    def test_unsupported_spine_capabilities_fail_closed(self):
        mutations = []
        for family in ("slots", "deform", "ik", "transform", "path"):
            values = _inputs()
            values["skeleton_json"]["animations"][values["clip_id"]][
                family
            ] = {}
            mutations.append(values)
        constraints = _inputs()
        constraints["skeleton_json"]["ik"] = []
        mutations.append(constraints)
        slot_capability = _inputs()
        slot_capability["skeleton_json"]["slots"][0]["dark"] = "ffffffff"
        mutations.append(slot_capability)
        bone_capability = _inputs()
        bone_capability["skeleton_json"]["bones"][0]["inherit"] = "onlyTranslation"
        mutations.append(bone_capability)
        attachment_capability = _inputs()
        attachment_capability["skeleton_json"]["skins"][0]["attachments"][
            "face"
        ]["face-image"]["sequence"] = {"count": 2}
        mutations.append(attachment_capability)
        nonnumeric_uv = _inputs()
        nonnumeric_uv["skeleton_json"]["skins"][0]["attachments"]["leg"][
            "leg-mesh"
        ]["uvs"][0] = "not-a-number"
        mutations.append(nonnumeric_uv)
        missing_motion_bone = _inputs()
        missing_motion_bone["skeleton_json"]["bones"].pop()
        mutations.append(missing_motion_bone)
        scale = _inputs()
        scale["skeleton_json"]["animations"][scale["clip_id"]]["bones"][
            "root-pelvis"
        ]["scale"] = [{"time": 0.0, "x": 1.0, "y": 1.0}]
        mutations.append(scale)
        curve = _inputs()
        curve["skeleton_json"]["animations"][curve["clip_id"]]["bones"][
            "forearm.left"
        ]["rotate"][0]["curve"] = "stepped"
        mutations.append(curve)
        unknown_bone = _inputs()
        unknown_bone["skeleton_json"]["animations"][unknown_bone["clip_id"]][
            "bones"
        ]["missing"] = {"rotate": [{"time": 0.0, "value": 1.0}]}
        mutations.append(unknown_bone)
        for index, invalid in enumerate(mutations):
            with self.subTest(index=index), self.assertRaises(
                Spine42V3BundleContractError
            ):
                _build(invalid)

    def test_malformed_events_draw_order_and_times_fail_closed(self):
        cases = []
        bad_event = _inputs()
        bad_event["skeleton_json"]["animations"][bad_event["clip_id"]][
            "events"
        ][0]["name"] = "undeclared"
        cases.append(bad_event)
        extra_event = _inputs()
        extra_event["skeleton_json"]["animations"][extra_event["clip_id"]][
            "events"
        ][0]["string"] = "payload"
        cases.append(extra_event)
        arbitrary_event = _inputs()
        arbitrary_event["skeleton_json"]["events"] = {"audio.boom": {}}
        arbitrary_event["skeleton_json"]["animations"][
            arbitrary_event["clip_id"]
        ]["events"] = [{"time": 0.0, "name": "audio.boom"}]
        cases.append(arbitrary_event)
        unknown_limb = _inputs()
        unknown_limb["skeleton_json"]["events"] = {
            "contact.tail.left.start": {},
            "contact.tail.left.end": {},
        }
        unknown_limb["skeleton_json"]["animations"][unknown_limb["clip_id"]][
            "events"
        ] = [
            {"time": 0.0, "name": "contact.tail.left.start"},
            {"time": 1.0, "name": "contact.tail.left.end"},
        ]
        cases.append(unknown_limb)
        duplicate_time = _inputs()
        duplicate_time["skeleton_json"]["animations"][
            duplicate_time["clip_id"]
        ]["bones"]["forearm.left"]["rotate"][1]["time"] = 0.0
        cases.append(duplicate_time)
        non_root_translation = _inputs()
        non_root_translation["skeleton_json"]["animations"][
            non_root_translation["clip_id"]
        ]["bones"]["forearm.left"]["translate"] = [
            {"time": 0.0, "x": 0.0, "y": 0.0},
            {"time": 1.0, "x": 0.0, "y": 0.0},
        ]
        cases.append(non_root_translation)
        bad_draw_order = _inputs()
        bad_draw_order["skeleton_json"]["animations"][
            bad_draw_order["clip_id"]
        ]["drawOrder"] = [{
            "time": 0.0,
            "offsets": [{"slot": "missing", "offset": 0}],
        }]
        cases.append(bad_draw_order)
        changed_setup_order = _inputs()
        changed_setup_order["skeleton_json"]["animations"][
            changed_setup_order["clip_id"]
        ]["drawOrder"] = [{
            "time": 0.0,
            "offsets": [
                {"slot": "leg", "offset": 1},
                {"slot": "face", "offset": -1},
            ],
        }]
        cases.append(changed_setup_order)
        for index, invalid in enumerate(cases):
            with self.subTest(index=index), self.assertRaises(
                Spine42V3BundleContractError
            ):
                _build(invalid)

    def test_source_and_cross_file_drift_fail_closed(self):
        cases = []
        stale_rig = _inputs()
        stale_rig["p3_source"]["rig_sha256"] = "f" * 64
        cases.append(stale_rig)
        extra_source = _inputs()
        extra_source["motion_instance_v3_source"]["clip_id"] = "wave.left"
        cases.append(extra_source)
        wrong_clip = _inputs()
        wrong_clip["clip_id"] = "other"
        cases.append(wrong_clip)
        missing_image = _inputs()
        missing_image["source_image_sha256s"].pop("face-image")
        cases.append(missing_image)
        wrong_png = _inputs()
        wrong_png["png_bytes"] = encode_rgba_png(
            RgbaImage(1, 1, b"\0\0\0\0")
        )
        cases.append(wrong_png)
        for index, invalid in enumerate(cases):
            with self.subTest(index=index), self.assertRaises(
                Spine42V3BundleContractError
            ):
                _build(invalid)

    def test_non_projection_source_hashes_change_evidence_address(self):
        values = _inputs()
        first = _build(values)
        changed = deepcopy(values)
        changed["motion_instance_v3_source"]["admission_sha256"] = "a" * 64
        second = _build(changed)

        self.assertEqual(
            first.skeleton_json_sha256, second.skeleton_json_sha256
        )
        self.assertNotEqual(
            first.run_identity_sha256, second.run_identity_sha256
        )
        self.assertNotEqual(first.report_sha256, second.report_sha256)
        self.assertNotEqual(first.bundle_sha256, second.bundle_sha256)

    def test_exact_bytes_are_tamper_evident_and_domain_separated(self):
        contract = _build(_inputs())
        items = tuple(contract.document_bytes.items())
        self.assertEqual(
            contract.bundle_sha256,
            spine42_v3_bundle_address_sha256(
                contract.project_id, contract.skeleton_json_sha256, items
            ),
        )
        tampered = items[:-1] + ((items[-1][0], items[-1][1] + b" "),)
        self.assertNotEqual(
            contract.bundle_sha256,
            spine42_v3_bundle_address_sha256(
                contract.project_id, contract.skeleton_json_sha256, tampered
            ),
        )
        self.assertNotEqual(
            contract.bundle_sha256,
            spine42_bundle_address_sha256(
                contract.project_id, contract.skeleton_json_sha256, items
            ),
        )
        with self.assertRaises(Spine42V3BundleContractError):
            spine42_v3_bundle_address_sha256(
                contract.project_id,
                contract.skeleton_json_sha256,
                tuple(reversed(items)),
            )

    def test_run_and_report_schemas_reject_authority_escalation(self):
        try:
            from jsonschema import Draft202012Validator
            from referencing import Registry, Resource
        except ImportError:
            self.skipTest("jsonschema/referencing is optional")
        contract = _build(_inputs())
        run = json.loads(contract.document_bytes["run-manifest.json"])
        report = json.loads(contract.document_bytes["export-report.json"])
        run_schema = json.loads((
            ROOT / "schemas" / "spine42-v3-export-run-v1.schema.json"
        ).read_text(encoding="utf-8"))
        report_schema = json.loads((
            ROOT / "schemas" / "spine42-v3-export-report-v1.schema.json"
        ).read_text(encoding="utf-8"))
        registry = Registry().with_resources([
            (run_schema["$id"], Resource.from_contents(run_schema)),
            (report_schema["$id"], Resource.from_contents(report_schema)),
        ])
        run_validator = Draft202012Validator(run_schema, registry=registry)
        report_validator = Draft202012Validator(
            report_schema, registry=registry
        )
        run_validator.validate(run)
        report_validator.validate(report)

        escalated = deepcopy(run)
        escalated["authority"]["official_runtime_loaded"] = True
        self.assertTrue(list(run_validator.iter_errors(escalated)))
        released = deepcopy(report)
        released["release_gate"]["status"] = "passed"
        self.assertTrue(list(report_validator.iter_errors(released)))


if __name__ == "__main__":
    unittest.main()
