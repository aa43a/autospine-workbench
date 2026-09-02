"""Compiler, replay, evidence, isolation, and schema tests for P10.5d v2."""

from __future__ import annotations

from contextlib import ExitStack, contextmanager
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for item in (ROOT, SRC):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

try:
    from jsonschema import Draft202012Validator
    from referencing import Registry, Resource
except ImportError:  # pragma: no cover - optional dependency
    Draft202012Validator = None
    Registry = Resource = None

from autospine_workbench.body_sway_dynamic_seam import (  # noqa: E402
    compile_body_sway_dynamic_seam_probe,
)
from autospine_workbench.body_sway_dynamic_seam_evidence_profile_v2 import (  # noqa: E402
    CERTIFIED_STATUS,
    SEGMENT_CERTIFIED_STATUS,
)
from autospine_workbench.body_sway_dynamic_seam_probe_validation_v2 import (  # noqa: E402
    BodySwayDynamicSeamProbeV2ValidationError,
    body_sway_dynamic_seam_probe_canonical_bytes_v2,
    body_sway_dynamic_seam_probe_sha256_v2,
    require_body_sway_dynamic_seam_probe_v2,
)
from autospine_workbench.body_sway_dynamic_seam_validation import (  # noqa: E402
    BodySwayDynamicSeamProbeValidationError,
    require_body_sway_dynamic_seam_probe,
)
from autospine_workbench.body_sway_dynamic_seam_validation_v2 import (  # noqa: E402
    BodySwayDynamicSeamSourceV2ValidationError,
)
from autospine_workbench.body_sway_dynamic_seam_v2 import (  # noqa: E402
    BodySwayDynamicSeamProbeV2Error,
    compile_body_sway_dynamic_seam_probe_v2,
)
from tests.body_sway_dynamic_seam_analysis_helpers import (  # noqa: E402
    FixedSampler,
    admitted_source,
    certified_proof,
    patched_pipeline,
)
from tests.body_sway_dynamic_seam_interval_helpers import (  # noqa: E402
    dynamic_seam_driver_fixture,
)
from tests.body_sway_dynamic_seam_locator_helpers import (  # noqa: E402
    reviewed_set,
)


ANALYSIS = "autospine_workbench.body_sway_dynamic_seam_analysis_v2."
COMPILER = "autospine_workbench.body_sway_dynamic_seam_v2."
VALIDATION = (
    "autospine_workbench.body_sway_dynamic_seam_probe_validation_v2."
)


def _source(rig, *, ticks=(0, 1), upstream_certified=True):
    return {
        "format": "autospine-body-sway-dynamic-seam-source",
        "format_version": 2,
        "project_id": "fixture-project",
        "clip_id": "idle",
        "source_set_sha256": "a" * 64,
        "body_sway_continuous_preview_proof_v2": {
            "project_id": "fixture-project",
            "clip_id": "idle",
            "status": "continuous_preview_model_structural_certified"
                if upstream_certified else "indeterminate",
            "source": {
                "amplitude_envelope_candidate_v2": {
                    "timing": {},
                    "reviewed_selection": {"parameters": {
                        "cycles": 1,
                        "per_bone_amplitude_deg": {},
                        "per_bone_phase_fraction": {},
                    }},
                },
                "motion_instance_v2": {"tracks": []},
                "preview_projection_v2": {"sample_ticks": list(ticks)},
                "rig_ir": deepcopy(rig),
                "target_profile": {},
                "reviewed_world_viewport": {
                    "x": 0.0, "y": 0.0,
                    "width": 1024.0, "height": 1024.0,
                },
            },
        },
        "reviewed_seam_anchor_set_v1": reviewed_set(rig),
    }


class BodySwayDynamicSeamProbeV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rig, cls.context, cls.locators = dynamic_seam_driver_fixture()
        cls.source = _source(cls.rig, ticks=(0, 1, 2))

        def certified(_locators, _context, left, right, *, budget):
            return certified_proof(
                cls.locators, left.tick, right.tick,
                boxes=min(1, budget.max_boxes), value=0.5,
            )

        cls.certified_driver = staticmethod(certified)
        with cls._pipeline(driver=certified):
            cls.probe = compile_body_sway_dynamic_seam_probe_v2(cls.source)
        old_source = admitted_source(cls.rig, ticks=(0, 1))
        with patched_pipeline(
            old_source, cls.context, cls.locators, driver=certified,
        ):
            cls.v1_probe = compile_body_sway_dynamic_seam_probe(old_source)

    @classmethod
    @contextmanager
    def _pipeline(cls, *, source=None, driver=None):
        expected = deepcopy(source or cls.source)

        def exact_admission(raw):
            if raw != expected:
                raise BodySwayDynamicSeamSourceV2ValidationError(
                    "test source crosswire"
                )
            return deepcopy(raw)

        with ExitStack() as stack:
            for target in (
                ANALYSIS + "require_body_sway_dynamic_seam_source_v2",
                COMPILER + "require_body_sway_dynamic_seam_source_v2",
                VALIDATION + "require_body_sway_dynamic_seam_source_v2",
            ):
                stack.enter_context(patch(target, side_effect=exact_admission))
            stack.enter_context(patch(
                ANALYSIS + "prepare_body_sway_sampler",
                return_value=FixedSampler(cls.context),
            ))
            stack.enter_context(patch(
                ANALYSIS + "prepare_body_sway_geometry_context_for_viewport",
                return_value=cls.context,
            ))
            stack.enter_context(patch(
                ANALYSIS + "prepare_body_sway_dynamic_seam_locators",
                return_value=cls.locators,
            ))
            if driver is not None:
                stack.enter_context(patch(
                    ANALYSIS
                    + "prove_body_sway_dynamic_seam_sampled_linear_segment",
                    side_effect=driver,
                ))
            yield

    def test_compiler_is_deterministic_and_emits_bounded_structural_rows(self):
        events = []
        with self._pipeline(driver=self.certified_driver):
            first = compile_body_sway_dynamic_seam_probe_v2(
                self.source, on_progress=lambda *row: events.append(row)
            )
            second = compile_body_sway_dynamic_seam_probe_v2(self.source)
        self.assertEqual(first.canonical_bytes, second.canonical_bytes)
        self.assertEqual(first.sha256, second.sha256)
        self.assertEqual(CERTIFIED_STATUS, first.document["status"])
        self.assertEqual([
            ("dynamic_seam_segments", 0, 2),
            ("dynamic_seam_segments", 1, 2),
            ("dynamic_seam_segments", 2, 2),
        ], events)
        for segment in first.document["segments"]:
            self.assertEqual(SEGMENT_CERTIFIED_STATUS, segment["status"])
            self.assertEqual(6, len(segment["relationships"]))
            for relationship in segment["relationships"]:
                self.assertEqual("finite_upper_bound", relationship["status"])
                self.assertIsInstance(
                    relationship["anchor_residual"][
                        "max_squared_upper_px2"
                    ], float,
                )
                self.assertFalse(
                    relationship["gap_proxy"]["raster_gap_claimed"]
                )
                self.assertEqual(
                    "not_evaluated", relationship["overlap"]["status"]
                )
                self.assertFalse(
                    relationship["overlap"]["raster_overlap_claimed"]
                )
        claims = first.document["claims"]
        for key in (
            "attachment_area_overlap_assessed", "dynamic_seam_safety",
            "official_runtime_equivalence", "raster_gap_safety",
            "raster_overlap_safety", "visual_seam_quality",
            "publishable_timeline", "release_authority",
        ):
            self.assertFalse(claims[key])
        self.assertEqual("blocked", first.document["release_gate"]["status"])

    def test_strict_replay_and_canonical_identity_reject_all_tampering(self):
        with self._pipeline(driver=self.certified_driver):
            require_body_sway_dynamic_seam_probe_v2(self.probe.document)
            canonical = body_sway_dynamic_seam_probe_canonical_bytes_v2(
                self.probe.document
            )
            digest = body_sway_dynamic_seam_probe_sha256_v2(
                self.probe.document
            )
        self.assertEqual(hashlib.sha256(canonical).hexdigest(), digest)
        attacks = []
        for path, value in (
            (("format_version",), 1),
            (("project_id",), "cross-project"),
            (("source", "source_set_sha256"), "b" * 64),
            (("problem", "problem_sha256"), "c" * 64),
            (("segments", 0, "segment_evidence_sha256"), "d" * 64),
            (("segments", 0, "relationships", 0, "overlap",
              "reason_code"), "forged"),
            (("analyzer", "version"), "9.9.9"),
            (("claims", "dynamic_seam_safety"), True),
            (("release_gate", "status"), "passed"),
            (("summary", "segment_count"), 99),
        ):
            attack = self.probe.document
            _assign(attack, path, value)
            attacks.append(attack)
        for index, attack in enumerate(attacks):
            with self.subTest(attack=index), self._pipeline(
                driver=self.certified_driver
            ), self.assertRaises(BodySwayDynamicSeamProbeV2ValidationError):
                require_body_sway_dynamic_seam_probe_v2(attack)

    def test_v1_and_v2_probe_validators_are_mutually_exclusive(self):
        with self.assertRaises(BodySwayDynamicSeamProbeValidationError):
            require_body_sway_dynamic_seam_probe(self.probe.document)
        with self.assertRaises(BodySwayDynamicSeamProbeV2ValidationError):
            require_body_sway_dynamic_seam_probe_v2(self.v1_probe.document)

    def test_backend_exception_and_global_budget_exhaustion_are_indeterminate(self):
        def broken(*_args, **_kwargs):
            raise RuntimeError("test backend failure")

        with self._pipeline(driver=broken):
            failed = compile_body_sway_dynamic_seam_probe_v2(
                self.source
            ).document
        self.assertEqual("indeterminate", failed["status"])
        self.assertIn(
            "interval_backend_error",
            failed["segments"][0]["reason_codes"],
        )
        for relationship in failed["segments"][0]["relationships"]:
            self.assertIsNone(
                relationship["anchor_residual"]["max_squared_upper_px2"]
            )
        source = _source(self.rig, ticks=(0, 1, 2, 3))

        def exhaust(_locators, _context, left, right, *, budget):
            boxes = 32767 if left.tick == 0 else 1
            return certified_proof(
                self.locators, left.tick, right.tick,
                boxes=boxes, value=0.5,
            )

        with self._pipeline(source=source, driver=exhaust):
            exhausted = compile_body_sway_dynamic_seam_probe_v2(
                source
            ).document
        self.assertEqual(32768, exhausted["summary"]["evaluated_box_count"])
        self.assertEqual("indeterminate", exhausted["segments"][2]["status"])
        self.assertEqual(
            ["global_subdivision_box_budget_exhausted"],
            exhausted["segments"][2]["reason_codes"],
        )

    def test_invalid_progress_and_nonfinite_values_fail_closed(self):
        with self._pipeline(driver=self.certified_driver), \
                self.assertRaises(BodySwayDynamicSeamProbeV2Error):
            compile_body_sway_dynamic_seam_probe_v2(
                self.source, on_progress="not-callable"
            )
        attack = self.probe.document
        attack["segments"][0]["relationships"][0]["anchor_residual"][
            "max_squared_upper_px2"
        ] = float("nan")
        with self.assertRaises(BodySwayDynamicSeamProbeV2ValidationError):
            require_body_sway_dynamic_seam_probe_v2(attack)

    @unittest.skipIf(Draft202012Validator is None, "jsonschema is optional")
    def test_schema_accepts_v2_and_rejects_v1_or_authority_escalation(self):
        schema = json.loads((
            ROOT / "schemas" / "body-sway-dynamic-seam-probe-v2.schema.json"
        ).read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        uri = (
            "https://autospine.local/schemas/"
            "body-sway-dynamic-seam-source-v2.schema.json"
        )
        registry = Registry().with_resource(uri, Resource.from_contents({
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": uri,
        }))
        validator = Draft202012Validator(schema, registry=registry)
        validator.validate(self.probe.document)
        self.assertFalse(validator.is_valid(self.v1_probe.document))
        overclaim = self.probe.document
        overclaim["claims"]["official_runtime_equivalence"] = True
        self.assertFalse(validator.is_valid(overclaim))
        overlap = self.probe.document
        overlap["segments"][0]["relationships"][0]["overlap"][
            "raster_overlap_claimed"
        ] = True
        self.assertFalse(validator.is_valid(overlap))


def _assign(document, path, value):
    target = document
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value


if __name__ == "__main__":
    unittest.main()
