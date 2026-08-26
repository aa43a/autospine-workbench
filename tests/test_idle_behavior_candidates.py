"""Exact-chain and no-fabrication tests for P10.0 idle candidates."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

try:
    from jsonschema import Draft202012Validator
except ImportError:  # pragma: no cover
    Draft202012Validator = None

from autospine_workbench.idle_behavior_candidates import (  # noqa: E402
    IdleBehaviorCandidateError,
    compile_idle_behavior_candidates,
)
from autospine_workbench.idle_behavior_candidate_validation import (  # noqa: E402
    BODY_SWAY_PROPOSAL,
    GENERATOR,
)
from autospine_workbench.idle_behavior_candidate_identity import (  # noqa: E402
    body_sway_candidate_id,
)
from autospine_workbench.idle_behavior_inputs import (  # noqa: E402
    require_idle_behavior_inputs,
)
from autospine_workbench.idle_behavior_inventory import (  # noqa: E402
    derive_idle_behavior_inventory,
)
from autospine_workbench.idle_behavior_rules import (  # noqa: E402
    classify_idle_behavior_features,
)
from tests.idle_behavior_helpers import IdleBehaviorFixture  # noqa: E402


class IdleBehaviorCandidateCompilerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.fixture = IdleBehaviorFixture(Path(cls.temporary.name))

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def compile(self, *, manifest=None, mesh=None, retarget=None, reviewed=None):
        fixture = self.fixture
        return compile_idle_behavior_candidates(
            manifest or fixture.manifest,
            mesh or fixture.mesh,
            retarget or fixture.retarget,
            reviewed or fixture.reviewed,
        )

    def test_exact_chain_is_deterministic_frozen_and_non_mutating(self):
        before = deepcopy(self.fixture.manifest)
        first, second = self.compile(), self.compile()
        self.assertEqual(first, second)
        self.assertEqual(first.sha256, second.sha256)
        self.assertEqual(before, self.fixture.manifest)
        changed = first.document
        changed["features"][0]["reason_codes"].clear()
        self.assertTrue(first.document["features"][0]["reason_codes"])
        with self.assertRaises(FrozenInstanceError):
            first._canonical_json = "{}"  # type: ignore[misc]

    def test_four_features_report_only_supported_evidence_status(self):
        document = self.compile().document
        rows = {row["feature_id"]: row for row in document["features"]}
        self.assertEqual({
            "blink": "unobservable", "body_sway": "candidate",
            "hair_spring": "unsupported", "mouth": "unobservable",
        }, {name: row["availability"] for name, row in rows.items()})
        self.assertEqual({
            "status": "candidate_only", "feature_count": 4,
            "candidate_count": 1, "unobservable_count": 2,
            "unsupported_count": 1,
        }, document["summary"])
        self.assertEqual(["face-layer"], [
            row["layer_id"] for row in rows["blink"]["evidence"]["layers"]
        ])
        self.assertEqual(["hair-image"], [
            row["attachment_id"]
            for row in rows["hair_spring"]["evidence"]["bindings"]
        ])
        self.assertIn("hair_mesh_missing", rows["hair_spring"]["reason_codes"])
        self.assertIn(
            "additive_rotation_overlay_unimplemented",
            rows["body_sway"]["reason_codes"],
        )

    def test_single_setup_face_layers_never_become_runtime_states(self):
        document = self.compile().document
        for feature_id in ("blink", "mouth"):
            row = next(item for item in document["features"]
                       if item["feature_id"] == feature_id)
            self.assertIsNone(row["candidate_id"])
            self.assertIsNone(row["proposal"])
            self.assertEqual("unobservable", row["availability"])
        semantics = document["semantics"]
        self.assertFalse(semantics["decision_emitted"])
        self.assertFalse(semantics["runtime_timeline_emitted"])
        self.assertFalse(semantics["generated_raster_emitted"])
        self.assertFalse(semantics["synthetic_visual_state_emitted"])
        self.assertFalse(semantics["raster_truth_claimed"])
        self.assertFalse(any(key in document for key in (
            "decision", "timeline", "state_graph", "generated_images",
        )))

    def test_candidate_id_binds_p9_v2_and_target_profile_seal(self):
        fixture = self.fixture
        inputs = require_idle_behavior_inputs(
            fixture.manifest, fixture.mesh, fixture.retarget, fixture.reviewed
        )
        inventory = derive_idle_behavior_inventory(
            inputs.manifest, inputs.rig, inputs.target_profile,
            inputs.motion_instance_v2,
        )
        source_sha = inputs.source["p9"]["motion_instance_v2_sha256"]
        target_sha = inputs.source["p5"]["target_profile_sha256"]
        baseline = classify_idle_behavior_features(
            inventory, motion_instance_v2_sha256=source_sha,
            target_profile_sha256=target_sha,
        )[1]["candidate_id"]
        changed_sha = classify_idle_behavior_features(
            inventory, motion_instance_v2_sha256="0" * 64,
            target_profile_sha256=target_sha,
        )[1]["candidate_id"]
        changed_target = classify_idle_behavior_features(
            inventory, motion_instance_v2_sha256=source_sha,
            target_profile_sha256="0" * 64,
        )[1]["candidate_id"]
        self.assertEqual(3, len({baseline, changed_sha, changed_target}))

    def test_candidate_id_domain_and_generator_version_are_hash_inputs(self):
        inputs = require_idle_behavior_inputs(
            self.fixture.manifest, self.fixture.mesh,
            self.fixture.retarget, self.fixture.reviewed,
        )
        sha = inputs.source["p9"]["motion_instance_v2_sha256"]
        target_sha = inputs.source["p5"]["target_profile_sha256"]
        arguments = {
            "generator": GENERATOR,
            "motion_instance_v2_sha256": sha,
            "target_profile_sha256": target_sha,
            "feature_id": "body_sway",
            "target_bone_ids": BODY_SWAY_PROPOSAL["target_bone_ids"],
        }
        baseline = body_sway_candidate_id(**arguments)
        with patch.dict(GENERATOR, {"version": "1.0.1"}):
            changed_version = body_sway_candidate_id(**arguments)
        with patch.dict(GENERATOR, {
            "candidate_id_domain": "autospine-idle-behavior-candidate-id/v2",
        }):
            changed_domain = body_sway_candidate_id(**arguments)
        self.assertEqual(3, len({baseline, changed_version, changed_domain}))

    def test_missing_hair_evidence_degrades_only_hair_feature(self):
        fixture = self.fixture
        inputs = require_idle_behavior_inputs(
            fixture.manifest, fixture.mesh, fixture.retarget, fixture.reviewed
        )
        manifest = inputs.manifest
        next(row for row in manifest["layers"]
             if row["layer_id"] == "hair-layer")["semantic"][
                 "mapping_method"] = "alias"
        inventory = derive_idle_behavior_inventory(
            manifest, inputs.rig, inputs.target_profile,
            inputs.motion_instance_v2,
        )
        rows = classify_idle_behavior_features(
            inventory,
            motion_instance_v2_sha256=inputs.source["p9"][
                "motion_instance_v2_sha256"
            ],
            target_profile_sha256=inputs.source["p5"][
                "target_profile_sha256"
            ],
        )
        status = {row["feature_id"]: row["availability"] for row in rows}
        self.assertEqual("unobservable", status["hair_spring"])
        self.assertEqual("candidate", status["body_sway"])
        self.assertIn("hair_semantic_review_required", rows[2]["reason_codes"])

    def test_missing_face_layers_keep_runtime_capability_blocker(self):
        inputs = require_idle_behavior_inputs(
            self.fixture.manifest, self.fixture.mesh,
            self.fixture.retarget, self.fixture.reviewed,
        )
        manifest = inputs.manifest
        manifest["layers"] = [
            row for row in manifest["layers"]
            if row["semantic"]["canonical_role"] not in {
                "face.eyelash", "face.mouth",
            }
        ]
        inventory = derive_idle_behavior_inventory(
            manifest, inputs.rig, inputs.target_profile,
            inputs.motion_instance_v2,
        )
        rows = classify_idle_behavior_features(
            inventory,
            motion_instance_v2_sha256=inputs.source["p9"][
                "motion_instance_v2_sha256"
            ],
            target_profile_sha256=inputs.source["p5"][
                "target_profile_sha256"
            ],
        )
        by_id = {row["feature_id"]: row for row in rows}
        for feature_id in ("blink", "mouth"):
            self.assertEqual("unobservable", by_id[feature_id]["availability"])
            self.assertIn(
                "attachment_switching_unsupported",
                by_id[feature_id]["reason_codes"],
            )

    def test_manifest_p3_p5_and_p9_tampering_fail_closed(self):
        manifest = deepcopy(self.fixture.manifest)
        manifest["revision"] += 1
        cases = (
            {"manifest": manifest},
            {"mesh": replace(self.fixture.mesh, layer_manifest_sha256="0" * 64)},
            {"retarget": replace(self.fixture.retarget, bundle_sha256="0" * 64)},
            {"reviewed": replace(self.fixture.reviewed, bundle_sha256="0" * 64)},
        )
        for arguments in cases:
            with self.subTest(arguments=tuple(arguments)), \
                    self.assertRaises(IdleBehaviorCandidateError):
                self.compile(**arguments)

    @unittest.skipIf(Draft202012Validator is None, "jsonschema not installed")
    def test_compiler_output_matches_published_schema(self):
        schema = json.loads((
            ROOT / "schemas" / "idle-behavior-candidates-v1.schema.json"
        ).read_text(encoding="utf-8"))
        Draft202012Validator(schema).validate(self.compile().document)


if __name__ == "__main__":
    unittest.main()
