"""Pure compiler and streaming-evidence tests for BodySwayProbeReport v1."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import FrozenInstanceError
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.body_sway_probe_geometry import (  # noqa: E402
    evaluate_prepared_body_sway_geometry_sample,
)
from autospine_workbench.body_sway_probe_geometry_context import (  # noqa: E402
    prepare_body_sway_geometry_context,
)
from autospine_workbench.body_sway_probe_inputs import (  # noqa: E402
    BodySwayProbeInputs,
    require_body_sway_probe_inputs,
)
from autospine_workbench.body_sway_probe_report import (  # noqa: E402
    BodySwayProbeReportError,
    compile_body_sway_probe_report,
    select_representative_indices,
)
from autospine_workbench.body_sway_probe_sampler import (  # noqa: E402
    prepare_body_sway_sampler,
)
from autospine_workbench.body_sway_probe_validation import (  # noqa: E402
    body_sway_probe_report_sha256,
    require_body_sway_probe_report,
)
from autospine_workbench.idle_behavior_candidates import (  # noqa: E402
    compile_idle_behavior_candidates,
)
from autospine_workbench.idle_behavior_decision import (  # noqa: E402
    build_idle_behavior_decision,
)
from tests.body_sway_probe_geometry_helpers import (  # noqa: E402
    exact_rig_and_target,
    sample,
)
from tests.idle_behavior_decision_helpers import (  # noqa: E402
    adjust_decision,
    completed_review,
)
from tests.idle_behavior_helpers import IdleBehaviorFixture  # noqa: E402


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False,
                      sort_keys=True, separators=(",", ":"))


class BodySwayProbeReportCompilerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.fixture = IdleBehaviorFixture(Path(cls.temporary.name))
        cls.candidates = compile_idle_behavior_candidates(
            cls.fixture.manifest, cls.fixture.mesh,
            cls.fixture.retarget, cls.fixture.reviewed,
        ).document
        cls.decision = build_idle_behavior_decision(
            cls.candidates, review=completed_review(),
            decisions=[adjust_decision(cls.candidates)],
        ).document
        cls.inputs = require_body_sway_probe_inputs(
            cls.fixture.manifest, cls.candidates, cls.decision,
            cls.fixture.mesh, cls.fixture.retarget, cls.fixture.reviewed,
        )

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def test_exact_no_mesh_input_compiles_with_real_geometry_per_tick(self):
        started = time.perf_counter()
        with patch(
            "autospine_workbench.body_sway_probe_report."
            "evaluate_prepared_body_sway_geometry_sample",
            wraps=evaluate_prepared_body_sway_geometry_sample,
        ) as evaluator, patch(
            "autospine_workbench.body_sway_probe_report."
            "prepare_body_sway_geometry_context",
            wraps=prepare_body_sway_geometry_context,
        ) as prepare_geometry, patch(
            "autospine_workbench.body_sway_probe_report."
            "prepare_body_sway_sampler",
            wraps=prepare_body_sway_sampler,
        ) as prepare_sampler:
            value = compile_body_sway_probe_report(self.inputs)
        elapsed = time.perf_counter() - started
        document = value.document
        count = document["summary"]["schedule_sample_count"]
        self.assertEqual(count, evaluator.call_count)
        self.assertEqual(1, prepare_geometry.call_count)
        self.assertEqual(1, prepare_sampler.call_count)
        self.assertLess(elapsed, 30.0)
        self.assertEqual("structural_rejected", document["status"])
        self.assertEqual(0, document["summary"]["mesh_attachment_count"])
        self.assertEqual(
            ["not_applicable", "passed", "not_applicable", "rejected",
             "not_applicable", "unobservable", "unobservable"],
            [row["status"] for row in document["checks"]],
        )
        self.assertEqual(82, document["checks"][3]["failure_count"])
        self.assertEqual(17, document["summary"]["rig_bone_count"])

    def test_deterministic_canonical_frozen_non_mutating_and_validated(self):
        before = deepcopy(self.inputs)
        first = compile_body_sway_probe_report(self.inputs)
        second = compile_body_sway_probe_report(self.inputs)
        self.assertEqual(first, second)
        self.assertEqual(before, self.inputs)
        require_body_sway_probe_report(first.document)
        self.assertEqual(first.sha256,
                         body_sway_probe_report_sha256(first.document))
        changed = first.document
        changed["summary"].clear()
        self.assertTrue(first.document["summary"])
        with self.assertRaises(FrozenInstanceError):
            first._canonical_json = "{}"  # type: ignore[misc]

    def test_every_visible_pose_has_full_rotation_inventory_and_own_hash(self):
        document = compile_body_sway_probe_report(self.inputs).document
        inventory = document["sample_stream"]["rotation_bone_ids"]
        overlay_ids = set(document["sample_stream"]["overlay_bone_ids"])
        for row in document["sample_stream"]["representative_samples"]:
            for field in (
                "base_rotation_deg", "overlay_rotation_deg",
                "combined_rotation_deg",
            ):
                self.assertEqual(inventory,
                                 [item["bone_id"] for item in row[field]])
            self.assertTrue(all(
                item["value"] == 0.0 for item in row["overlay_rotation_deg"]
                if item["bone_id"] not in overlay_ids
            ))

    def test_loop_failure_is_representable_and_check_bound_to_endpoints(self):
        inputs = _open_loop_inputs(self.inputs)
        document = compile_body_sway_probe_report(inputs).document
        loop = document["checks"][0]
        self.assertEqual("rejected", loop["status"])
        self.assertEqual(1, loop["failure_count"])
        self.assertEqual("structural_rejected", document["status"])
        samples = document["sample_stream"]["representative_samples"]
        self.assertNotEqual(samples[0]["root_translation_xy"],
                            samples[-1]["root_translation_xy"])

    def test_closed_loop_uses_pose_state_not_tick_bearing_sample_sha(self):
        document = compile_body_sway_probe_report(
            _closed_loop_inputs(self.inputs)
        ).document
        loop = document["checks"][0]
        self.assertEqual("passed", loop["status"])
        samples = document["sample_stream"]["representative_samples"]
        self.assertNotEqual(samples[0]["sample_sha256"],
                            samples[-1]["sample_sha256"])
        for field in (
            "base_rotation_deg", "overlay_rotation_deg",
            "combined_rotation_deg", "root_translation_xy",
        ):
            self.assertEqual(samples[0][field], samples[-1][field])
        require_body_sway_probe_report(document)

    def test_representative_selection_is_bounded_uniform_and_exact(self):
        for count in (2, 255, 256, 257, 65_536):
            with self.subTest(count=count):
                indices = select_representative_indices(count)
                self.assertEqual(0, indices[0])
                self.assertEqual(count - 1, indices[-1])
                self.assertEqual(tuple(sorted(set(indices))), indices)
                self.assertEqual(min(count, 256), len(indices))
        with self.assertRaises(BodySwayProbeReportError):
            select_representative_indices(65_537)

    def test_spoofed_input_type_fails_before_sampling(self):
        class Spoof:
            pass

        with self.assertRaisesRegex(BodySwayProbeReportError, "exact admitted"):
            compile_body_sway_probe_report(Spoof())  # type: ignore[arg-type]

    def test_production_files_remain_small_and_claim_scoped(self):
        for name in (
            "body_sway_probe_report.py",
            "body_sway_probe_report_evidence.py",
        ):
            path = SRC / "autospine_workbench" / name
            self.assertLess(len(path.read_text(encoding="utf-8").splitlines()), 300)
        document = compile_body_sway_probe_report(self.inputs).document
        self.assertFalse(document["semantics"]["motion_instance_v3_emitted"])
        self.assertFalse(document["semantics"]["runtime_timeline_emitted"])
        self.assertFalse(document["semantics"]["safe_range_claimed"])
        self.assertTrue(document["semantics"]["manual_runtime_preview_required"])


def _open_loop_inputs(inputs: BodySwayProbeInputs) -> BodySwayProbeInputs:
    documents = dict(inputs._documents)  # exact frozen JSON test fixture
    motion = json.loads(documents["p9-motion-instance-v2"])
    motion["timing"]["loop"] = True
    translation = next(
        row for row in motion["tracks"] if row["property"] == "translation"
    )
    translation["keys"][-1]["value"][0] += 3.0
    documents["p9-motion-instance-v2"] = _canonical(motion)
    return BodySwayProbeInputs(
        inputs.project_id, inputs.clip_id,
        tuple((name, documents[name]) for name, _value in inputs._documents),
        inputs._source_json,
    )


def _closed_loop_inputs(inputs: BodySwayProbeInputs) -> BodySwayProbeInputs:
    documents = dict(inputs._documents)
    motion = json.loads(documents["p9-motion-instance-v2"])
    motion["timing"]["loop"] = True
    for track in motion["tracks"]:
        track["keys"][-1]["value"] = deepcopy(track["keys"][0]["value"])
    documents["p9-motion-instance-v2"] = _canonical(motion)
    return BodySwayProbeInputs(
        inputs.project_id, inputs.clip_id,
        tuple((name, documents[name]) for name, _value in inputs._documents),
        inputs._source_json,
    )


if __name__ == "__main__":
    unittest.main()
