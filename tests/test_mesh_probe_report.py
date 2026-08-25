"""Project-level P3 mesh action probe report contracts."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import FrozenInstanceError
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.mesh_eligibility import HingeTarget  # noqa: E402
from autospine_workbench.mesh_probe_report import (  # noqa: E402
    MeshProbeReportError,
    build_mesh_probe_report,
    probe_config,
    require_mesh_probe_report,
)
from autospine_workbench.resolved_project import canonical_sha256  # noqa: E402
from tests.test_mesh_action_probe import (  # noqa: E402
    DISTAL,
    PROXIMAL,
    bones,
    early_failure_attachment,
    passing_attachment,
)
from tests.test_mesh_contract import mesh_run  # noqa: E402
from tests.test_mesh_rig import compile_a  # noqa: E402

try:
    from jsonschema import Draft202012Validator
    from jsonschema.exceptions import ValidationError
except ImportError:  # pragma: no cover - optional test extra
    Draft202012Validator = None
    ValidationError = Exception


def target(attachment_id: str = "leg-left") -> HingeTarget:
    return HingeTarget(
        attachment_id=attachment_id,
        source_layer_id=attachment_id,
        side="left",
        proximal_bone_id=PROXIMAL,
        distal_bone_id=DISTAL,
    )


def synthetic_inputs(attachment=None) -> tuple[dict, dict, tuple[HingeTarget, ...]]:
    run = mesh_run()
    attachment = deepcopy(
        attachment if attachment is not None else passing_attachment()
    )
    attachment.update(
        slot="leg-left",
        source_layer_ids=["leg-left"],
        pivot_xy=[110, 50],
        uvs=[[0, 0] for _ in attachment["vertices"]],
    )
    rig = {
        "source": {"run_manifest_sha256": canonical_sha256(run)},
        "capabilities": ["mesh_attachment", "setup_draw_order"],
        "bones": bones(),
        "slots": [{
            "id": "leg-left", "bone": PROXIMAL,
            "setup_attachment": "leg-left", "setup_draw_order": 0,
        }],
        "attachments": [attachment],
        "skins": {"default": {"leg-left": ["leg-left"]}},
        "animations": [],
    }
    return rig, run, (target(),)


def noop_inputs() -> tuple[dict, dict, tuple]:
    run = mesh_run()
    return (
        {
            "source": {"run_manifest_sha256": canonical_sha256(run)},
            "capabilities": [],
            "bones": [],
            "slots": [],
            "attachments": [],
            "skins": {"default": {}},
            "animations": [],
        },
        run,
        (),
    )


def reverse_keys(value):
    if isinstance(value, dict):
        return {
            key: reverse_keys(item)
            for key, item in reversed(list(value.items()))
        }
    if isinstance(value, list):
        return [reverse_keys(item) for item in value]
    return value


class MeshProbeReportSchemaTests(unittest.TestCase):
    def schema(self):
        return json.loads(
            (ROOT / "schemas" / "mesh-action-probes-v1.schema.json").read_text(
                encoding="utf-8"
            )
        )

    def test_schema_is_draft_2020_12_and_accepts_pass_reject_and_noop(self) -> None:
        schema = self.schema()
        self.assertEqual("https://json-schema.org/draft/2020-12/schema", schema["$schema"])
        self.assertTrue(schema["$id"].endswith("mesh-action-probes-v1.schema.json"))
        if Draft202012Validator is None:
            return
        Draft202012Validator.check_schema(schema)
        documents = (
            build_mesh_probe_report(*synthetic_inputs()).document,
            build_mesh_probe_report(*synthetic_inputs(early_failure_attachment())).document,
            build_mesh_probe_report(*noop_inputs()).document,
        )
        for document in documents:
            Draft202012Validator(schema).validate(document)

    @unittest.skipIf(Draft202012Validator is None, "install the test extra")
    def test_schema_rejects_unknown_fields_and_changed_pinned_config(self) -> None:
        validator = Draft202012Validator(self.schema())
        mutations = (
            lambda value: value.update(unexpected=True),
            lambda value: value["prober"]["config"].update(bend_step_degrees=10),
            lambda value: value["attachments"][0]["action_probe"].update(extra=True),
        )
        for mutate in mutations:
            document = build_mesh_probe_report(*synthetic_inputs()).document
            mutate(document)
            with self.subTest(document=document), self.assertRaises(ValidationError):
                validator.validate(document)


class MeshProbeReportBuildTests(unittest.TestCase):
    def test_a_like_report_is_bound_sorted_and_passes_minimum_gate(self) -> None:
        compiled = compile_a()
        report = build_mesh_probe_report(
            compiled.rig, compiled.run_manifest, tuple(reversed(compiled.targets))
        )
        document = report.document

        self.assertEqual("autospine-mesh-action-probes", document["format"])
        self.assertEqual("mesh-a", document["project_id"])
        self.assertEqual("passed", document["status"])
        self.assertEqual("converted=2", document["summary"])
        self.assertEqual(probe_config(), document["prober"]["config"])
        self.assertEqual(
            ["leg-left", "leg-right"],
            [item["attachment_id"] for item in document["attachments"]],
        )
        for item in document["attachments"]:
            self.assertEqual({"status": "passed"}, item["gate"])
            self.assertGreaterEqual(item["widest_safe_bend"]["magnitude_deg"], 30)
            self.assertEqual("either", item["widest_safe_bend"]["direction"])
            self.assertEqual("autospine-mesh-action-probe", item["action_probe"]["format"])
        source = document["source"]
        self.assertEqual(canonical_sha256(compiled.rig), source["rig_sha256"])
        self.assertEqual(canonical_sha256(compiled.run_manifest), source["run_manifest_sha256"])
        self.assertEqual(compiled.run_manifest["inputs"], {
            key: source[key] for key in compiled.run_manifest["inputs"]
        })
        require_mesh_probe_report(
            document, rig=compiled.rig, run=compiled.run_manifest,
            targets=compiled.targets,
        )

    def test_early_failure_is_reported_rejected_not_raised(self) -> None:
        rig, run, targets = synthetic_inputs(early_failure_attachment())
        document = build_mesh_probe_report(rig, run, targets).document
        item = document["attachments"][0]

        self.assertEqual("rejected", document["status"])
        self.assertEqual("converted=1", document["summary"])
        self.assertEqual({"direction": "either", "magnitude_deg": 0}, item["widest_safe_bend"])
        self.assertEqual({"status": "rejected"}, item["gate"])
        self.assertEqual(5, item["action_probe"]["distal_bend"]["positive"]["first_failure"]["angle_deg"])
        require_mesh_probe_report(document, rig=rig, run=run, targets=targets)

    def test_zero_target_requires_no_mesh_and_reports_reviewed_noop(self) -> None:
        rig, run, targets = noop_inputs()
        document = build_mesh_probe_report(rig, run, targets).document
        self.assertEqual("passed", document["status"])
        self.assertEqual("reviewed-noop", document["summary"])
        self.assertEqual([], document["attachments"])
        require_mesh_probe_report(document, rig=rig, run=run, targets=targets)

        mesh_rig, _mesh_run, _mesh_targets = synthetic_inputs()
        with self.assertRaisesRegex(MeshProbeReportError, "differs from probe targets"):
            build_mesh_probe_report(mesh_rig, run, targets)

    def test_mapping_and_target_order_are_deterministic_and_inputs_unchanged(self) -> None:
        compiled = compile_a()
        rig, run, targets = compiled.rig, compiled.run_manifest, compiled.targets
        before = deepcopy((rig, run, targets))
        first = build_mesh_probe_report(rig, run, targets)
        self.assertEqual(before, (rig, run, targets))

        reversed_rig, reversed_run = reverse_keys(rig), reverse_keys(run)
        reversed_targets = tuple(reversed(targets))
        reversed_before = deepcopy((reversed_rig, reversed_run, reversed_targets))
        second = build_mesh_probe_report(reversed_rig, reversed_run, reversed_targets)
        self.assertEqual(first, second)
        self.assertEqual(reversed_before, (reversed_rig, reversed_run, reversed_targets))

    def test_frozen_json_accessor_returns_isolated_documents(self) -> None:
        report = build_mesh_probe_report(*synthetic_inputs())
        changed = report.document
        changed["source"].clear()
        self.assertTrue(report.document["source"])
        self.assertEqual(report.to_json(), build_mesh_probe_report(*synthetic_inputs()).to_json())
        with self.assertRaises(FrozenInstanceError):
            report._json = "{}"  # type: ignore[misc]


class MeshProbeReportTamperTests(unittest.TestCase):
    def test_run_and_rig_source_identity_are_strict(self) -> None:
        rig, run, targets = synthetic_inputs()
        changed_run = deepcopy(run)
        changed_run["compiler"]["version"] = "latest"
        with self.assertRaises(MeshProbeReportError):
            build_mesh_probe_report(rig, changed_run, targets)

        changed_rig = deepcopy(rig)
        changed_rig["source"]["run_manifest_sha256"] = "0" * 64
        with self.assertRaisesRegex(MeshProbeReportError, "run manifest binding"):
            build_mesh_probe_report(changed_rig, run, targets)

    def test_duplicate_missing_and_extra_mesh_targets_fail(self) -> None:
        rig, run, targets = synthetic_inputs()
        with self.assertRaisesRegex(MeshProbeReportError, "targets must be unique"):
            build_mesh_probe_report(rig, run, (*targets, *targets))

        with self.assertRaisesRegex(MeshProbeReportError, "differs from probe targets"):
            build_mesh_probe_report(rig, run, (target("missing"),))

        changed = deepcopy(rig)
        extra = deepcopy(changed["attachments"][0])
        extra["id"] = "leg-right"
        extra["slot"] = "leg-right"
        extra["source_layer_ids"] = ["leg-right"]
        changed["attachments"].append(extra)
        changed["slots"].append({
            "id": "leg-right", "bone": PROXIMAL,
            "setup_attachment": "leg-right", "setup_draw_order": 1,
        })
        changed["skins"]["default"]["leg-right"] = ["leg-right"]
        with self.assertRaisesRegex(MeshProbeReportError, "differs from probe targets"):
            build_mesh_probe_report(changed, run, targets)

    def test_rig_target_source_slot_and_profile_semantics_are_bound(self) -> None:
        rig, run, targets = synthetic_inputs()
        changed = deepcopy(rig)
        changed["attachments"][0]["source_layer_ids"] = ["forged-source"]
        with self.assertRaisesRegex(MeshProbeReportError, "target binding"):
            build_mesh_probe_report(changed, run, targets)

        changed = deepcopy(rig)
        changed["attachments"][0]["slot"] = "slot-alias"
        changed["slots"][0]["id"] = "slot-alias"
        changed["skins"]["default"]["slot-alias"] = changed["skins"]["default"].pop(
            "leg-left"
        )
        with self.assertRaisesRegex(MeshProbeReportError, "target binding"):
            build_mesh_probe_report(changed, run, targets)

        forged = HingeTarget(
            attachment_id="leg-left", source_layer_id="leg-left", side="right",
            proximal_bone_id=PROXIMAL, distal_bone_id=DISTAL,
        )
        with self.assertRaisesRegex(MeshProbeReportError, "profile-v1"):
            build_mesh_probe_report(rig, run, (forged,))

        changed = deepcopy(rig)
        changed["slots"][0]["bone"] = "missing"
        with self.assertRaises(MeshProbeReportError):
            build_mesh_probe_report(changed, run, targets)

    def test_setup_failure_is_hard_but_distal_gate_failure_is_not(self) -> None:
        thin = passing_attachment()
        thin["vertices"] = [[0, 0], [1, 0], [1, 0.0001]]
        with self.assertRaisesRegex(MeshProbeReportError, "setup pose failed"):
            build_mesh_probe_report(*synthetic_inputs(thin))

    def test_source_target_metrics_and_gate_tamper_are_recomputed(self) -> None:
        rig, run, targets = synthetic_inputs()
        original = build_mesh_probe_report(rig, run, targets).document
        mutations = (
            lambda value: value["source"].update(rig_sha256="0" * 64),
            lambda value: value["attachments"][0].update(side="right"),
            lambda value: value["attachments"][0]["action_probe"]["setup"]["metrics"].update(flipped_count=9),
            lambda value: value["attachments"][0]["gate"].update(status="rejected"),
        )
        for mutate in mutations:
            changed = deepcopy(original)
            mutate(changed)
            with self.subTest(changed=changed), self.assertRaisesRegex(
                MeshProbeReportError, "differs from recomputed evidence"
            ):
                require_mesh_probe_report(changed, rig=rig, run=run, targets=targets)


if __name__ == "__main__":
    unittest.main()
