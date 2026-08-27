"""JSON Schema boundary tests for P10.6a consumer admission."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest


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
from autospine_workbench.body_sway_motion_consumer_admission import (  # noqa: E402
    compile_body_sway_motion_consumer_admission_core,
    seal_body_sway_motion_consumer_admission,
)
from tests.body_sway_dynamic_seam_analysis_helpers import (  # noqa: E402
    admitted_source,
    certified_proof,
    patched_pipeline,
)
from tests.body_sway_dynamic_seam_interval_helpers import (  # noqa: E402
    dynamic_seam_driver_fixture,
)
from tests.body_sway_motion_consumer_helpers import (  # noqa: E402
    consumer_fixture,
    head_observation,
    patched_probe_replay,
)


@unittest.skipIf(Draft202012Validator is None, "jsonschema is optional")
class BodySwayMotionConsumerSchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        _, cls.bundle, cls.probe, cls.identity = consumer_fixture(
            Path(cls.temporary.name)
        )
        with patched_probe_replay(cls.probe, cls.identity):
            core = compile_body_sway_motion_consumer_admission_core(
                cls.probe, cls.bundle
            )
            observation = head_observation(cls.identity)
            cls.document = seal_body_sway_motion_consumer_admission(
                core, observation, observation
            ).document
        cls.document["source"]["body_sway_dynamic_seam_probe"] = (
            cls._schema_shaped_dynamic_probe()
        )
        cls.schema = cls._schema(
            "body-sway-motion-consumer-admission-v1.schema.json"
        )
        Draft202012Validator.check_schema(cls.schema)
        cls.validator = Draft202012Validator(
            cls.schema, registry=cls._registry()
        )

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    @classmethod
    def _schema_shaped_dynamic_probe(cls):
        rig, context, locators = dynamic_seam_driver_fixture()
        source = admitted_source(rig, ticks=(0, 1))

        def certified(_locators, _context, left, right, *, budget):
            return certified_proof(
                locators, left.tick, right.tick,
                boxes=min(1, budget.max_boxes),
            )

        with patched_pipeline(
            source, context, locators, driver=certified
        ):
            value = compile_body_sway_dynamic_seam_probe(source).document
        value["source"].update({
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

    @classmethod
    def _schema(cls, name):
        return json.loads((ROOT / "schemas" / name).read_text(
            encoding="utf-8"
        ))

    @classmethod
    def _registry(cls):
        schemas = [
            cls._schema("body-sway-dynamic-seam-probe-v1.schema.json"),
            cls._schema("motion-instance-v2.schema.json"),
        ]
        for name in (
            "body-sway-continuous-preview-proof-v1.schema.json",
            "seam-anchor-candidates-v1.schema.json",
            "seam-anchor-review-decision-v1.schema.json",
            "reviewed-seam-anchor-set-v1.schema.json",
        ):
            uri = f"https://autospine.local/schemas/{name}"
            schemas.append({
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "$id": uri,
            })
        return Registry().with_resources(tuple(
            (schema["$id"], Resource.from_contents(schema))
            for schema in schemas
        ))

    def test_schema_accepts_exact_outer_contract_and_external_references(self):
        self.validator.validate(self.document)

    def test_schema_blocks_overclaims_emission_and_non_compile_time_heads(self):
        mutations = []
        overclaim = deepcopy(self.document)
        overclaim["claims"]["runtime_equivalence"] = True
        mutations.append(overclaim)
        emitted = deepcopy(self.document)
        emitted["motion_instance_v3"] = {}
        mutations.append(emitted)
        stale_scope = deepcopy(self.document)
        stale_scope["head_observations"]["scope"] = "permanent"
        mutations.append(stale_scope)
        nested_overclaim = deepcopy(self.document)
        nested_overclaim["source"]["body_sway_dynamic_seam_probe"][
            "claims"
        ]["visual_seam_quality"] = True
        mutations.append(nested_overclaim)
        wrong_mode = deepcopy(self.document)
        wrong_mode["motion_domain"]["base_channels"]["draw_order"][
            "mode"
        ] = "linear"
        mutations.append(wrong_mode)
        for index, value in enumerate(mutations):
            with self.subTest(index=index):
                self.assertFalse(self.validator.is_valid(value))


if __name__ == "__main__":
    unittest.main()
