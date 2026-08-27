"""Public semantic and JSON Schema tests for P10.5d seam probes."""

from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from dataclasses import FrozenInstanceError
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
from autospine_workbench.body_sway_dynamic_seam_source import (  # noqa: E402
    BodySwayDynamicSeamSourceError,
)
from autospine_workbench.body_sway_dynamic_seam_validation import (  # noqa: E402
    BodySwayDynamicSeamProbeValidationError,
    body_sway_dynamic_seam_probe_canonical_bytes,
    body_sway_dynamic_seam_probe_sha256,
    require_body_sway_dynamic_seam_probe,
)
from tests.body_sway_dynamic_seam_analysis_helpers import (  # noqa: E402
    admitted_source,
    certified_proof,
    patched_pipeline,
)
from tests.body_sway_dynamic_seam_interval_helpers import (  # noqa: E402
    dynamic_seam_driver_fixture,
)


VALIDATION = "autospine_workbench.body_sway_dynamic_seam_validation."


class BodySwayDynamicSeamValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rig, cls.context, cls.locators = dynamic_seam_driver_fixture()
        cls.source = admitted_source(cls.rig, ticks=(0, 1))

        def certified(_locators, _context, left, right, *, budget):
            return certified_proof(
                cls.locators, left.tick, right.tick,
                boxes=min(1, budget.max_boxes),
            )

        cls.certified_driver = staticmethod(certified)
        with patched_pipeline(
            cls.source, cls.context, cls.locators, driver=certified,
        ):
            cls.probe = compile_body_sway_dynamic_seam_probe(cls.source)

        def backend_error(*_args, **_kwargs):
            raise RuntimeError("test-only backend failure")

        with patched_pipeline(
            cls.source, cls.context, cls.locators, driver=backend_error,
        ):
            cls.indeterminate_document = (
                compile_body_sway_dynamic_seam_probe(cls.source).document
            )

    @contextmanager
    def _validation_pipeline(self, *, admission=None):
        expected = deepcopy(self.source)

        def exact_admission(raw):
            if raw != expected:
                raise BodySwayDynamicSeamSourceError("test source tamper")
            return deepcopy(raw)

        with patched_pipeline(
            self.source, self.context, self.locators,
            driver=self.certified_driver,
        ), patch(
            VALIDATION + "require_body_sway_dynamic_seam_source",
            side_effect=admission or exact_admission,
        ) as source_validator:
            yield source_validator

    def _assert_rejected(self, document):
        with self._validation_pipeline(), self.assertRaises(
            BodySwayDynamicSeamProbeValidationError
        ):
            require_body_sway_dynamic_seam_probe(document)

    def test_valid_probe_replays_and_canonical_identity_is_stable(self):
        document = self.probe.document
        with self._validation_pipeline() as source_validator:
            self.assertIsNone(require_body_sway_dynamic_seam_probe(document))
            first = body_sway_dynamic_seam_probe_canonical_bytes(document)
            second = body_sway_dynamic_seam_probe_canonical_bytes(document)
            digest = body_sway_dynamic_seam_probe_sha256(document)
        self.assertEqual(4, source_validator.call_count)
        self.assertEqual(first, second)
        self.assertEqual(self.probe.canonical_bytes, first)
        self.assertEqual(hashlib.sha256(first).hexdigest(), digest)
        self.assertEqual(self.probe.sha256, digest)

    def test_format_project_clip_and_every_semantic_section_are_replayed(self):
        attacks = []
        format_attack = self.probe.document
        format_attack["format_version"] = 2
        attacks.append(format_attack)
        project = self.probe.document
        project["project_id"] = "cross-project"
        attacks.append(project)
        clip = self.probe.document
        clip["clip_id"] = "wave"
        attacks.append(clip)
        source = self.probe.document
        source["source"]["source_set_sha256"] = "f" * 64
        attacks.append(source)
        problem = self.probe.document
        problem["problem"]["problem_sha256"] = "f" * 64
        attacks.append(problem)
        segment = self.probe.document
        segment["segments"][0]["pair_count"] -= 1
        attacks.append(segment)
        inventory = self.probe.document
        inventory["segments"][0]["relationships"].reverse()
        attacks.append(inventory)
        seal = self.probe.document
        seal["segments"][0]["segment_evidence_sha256"] = "f" * 64
        attacks.append(seal)
        summary = self.probe.document
        summary["summary"]["segment_count"] += 1
        attacks.append(summary)
        analyzer = self.probe.document
        analyzer["analyzer"]["version"] = "9.9.9"
        attacks.append(analyzer)
        claims = self.probe.document
        claims["claims"]["dynamic_seam_safety"] = True
        attacks.append(claims)
        release = self.probe.document
        release["release_gate"]["status"] = "passed"
        attacks.append(release)
        for index, attack in enumerate(attacks):
            with self.subTest(attack=index):
                self._assert_rejected(attack)

    def test_analyzer_and_problem_budgets_cannot_be_raised_or_retyped(self):
        attacks = []
        analyzer = self.probe.document
        analyzer["analyzer"]["config"]["budget"]["max_depth"] = 15
        attacks.append(analyzer)
        problem = self.probe.document
        problem["problem"]["budget"]["max_total_boxes"] = 32769
        attacks.append(problem)
        summary = self.probe.document
        summary["summary"]["evaluated_box_count"] = True
        attacks.append(summary)
        for attack in attacks:
            self._assert_rejected(attack)

    def test_nonfinite_non_json_and_byte_budget_fail_before_replay(self):
        for value in (float("nan"), float("inf"), object()):
            document = self.probe.document
            document["segments"][0]["max_squared_distance_upper_px2"] = value
            with self.subTest(value=type(value).__name__), patch(
                VALIDATION + "require_body_sway_dynamic_seam_source"
            ) as source_validator, self.assertRaises(
                BodySwayDynamicSeamProbeValidationError
            ):
                require_body_sway_dynamic_seam_probe(document)
            source_validator.assert_not_called()
        with patch(
            VALIDATION + "MAX_DOCUMENT_BYTES", 1
        ), patch(
            VALIDATION + "require_body_sway_dynamic_seam_source"
        ) as source_validator, self.assertRaisesRegex(
            BodySwayDynamicSeamProbeValidationError, "byte limit"
        ):
            require_body_sway_dynamic_seam_probe(self.probe.document)
        source_validator.assert_not_called()

    def test_validation_and_accessors_are_copy_isolated_and_probe_is_frozen(self):
        document = self.probe.document
        observed = []

        def observe(raw):
            observed.append(raw)
            return deepcopy(raw)

        with self._validation_pipeline(admission=observe):
            require_body_sway_dynamic_seam_probe(document)
        self.assertIsNot(observed[0], document["source"])
        observed[0]["source_set_sha256"] = "0" * 64
        self.assertEqual("a" * 64, document["source"]["source_set_sha256"])
        detached = self.probe.document
        detached["status"] = "forged"
        self.assertNotEqual("forged", self.probe.document["status"])
        with self.assertRaises(FrozenInstanceError):
            self.probe._canonical_json = "{}"

    @unittest.skipIf(Draft202012Validator is None, "jsonschema is optional")
    def test_schema_accepts_both_outcomes_and_blocks_overclaim_or_null_certified(self):
        schema = json.loads((
            ROOT / "schemas" / "body-sway-dynamic-seam-probe-v1.schema.json"
        ).read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        referenced = (
            "body-sway-continuous-preview-proof-v1.schema.json",
            "seam-anchor-candidates-v1.schema.json",
            "seam-anchor-review-decision-v1.schema.json",
            "reviewed-seam-anchor-set-v1.schema.json",
        )
        resources = []
        for name in referenced:
            uri = f"https://autospine.local/schemas/{name}"
            resources.append((uri, Resource.from_contents({
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "$id": uri,
            })))
        validator = Draft202012Validator(
            schema, registry=Registry().with_resources(resources)
        )
        certified = self._schema_document(self.probe.document)
        indeterminate = self._schema_document(self.indeterminate_document)
        validator.validate(certified)
        validator.validate(indeterminate)
        overclaim = deepcopy(certified)
        overclaim["claims"]["visual_seam_quality"] = True
        self.assertFalse(validator.is_valid(overclaim))
        null_certified = deepcopy(certified)
        null_certified["segments"][0]["relationships"][0]["pairs"][0][
            "max_squared_distance_upper_px2"
        ] = None
        self.assertFalse(validator.is_valid(null_certified))
        self.assertIsNone(indeterminate["segments"][0][
            "max_squared_distance_upper_px2"
        ])

    @staticmethod
    def _schema_document(document):
        value = deepcopy(document)
        source = value["source"]
        source.update({
            "body_sway_continuous_proof_sha256": "1" * 64,
            "seam_anchor_candidate_sha256": "2" * 64,
            "seam_anchor_candidates": {},
            "seam_anchor_review_decision_sha256": "3" * 64,
            "seam_anchor_review_decision": {},
            "review_revision": 1,
            "reviewed_seam_anchor_set_sha256": "4" * 64,
            "reviewed_seam_anchor_set_bundle_sha256": "5" * 64,
        })
        return value


if __name__ == "__main__":
    unittest.main()
