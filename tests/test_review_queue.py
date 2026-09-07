"""Current-input review exceptions without decision writes or invented gates."""
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest

from tests.test_layer_manifest import project_fixture, write_png
from tests.resolved_snapshot_helpers import refresh_resolved_snapshot, resolved_joint
from autospine_workbench.automation.project_snapshot import observe_project
from autospine_workbench.automation.review_queue import (
    ReviewQueueError, build_review_queue, validate_review_queue,
)
from autospine_workbench.resolved_project import canonical_sha256

ROOT = Path(__file__).resolve().parents[1]


def reseal(queue):
    document = deepcopy(queue)
    document.pop("queue_sha256", None)
    document["queue_sha256"] = canonical_sha256(document)
    return document


class ReviewQueueTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.asset = self.directory / "arm.png"
        write_png(self.asset, 30, 40)
        self.project = project_fixture()
        self.layer = self.project["resolved"]["layers"][0]
        self.layer["candidate_bone"] = "root-tip"
        self.layer["reviewed_fields"].append("candidate_bone")
        owner = self

        class Store:
            def get_project(self, project_id):
                return deepcopy(owner.project)

            def resolve_asset(self, project_id, kind, layer_id):
                return owner.asset

        self.store = Store()

    def queue(self, profile="production_review"):
        self.project["resolved"] = refresh_resolved_snapshot(self.project["resolved"])
        with observe_project(self.store, self.project["id"]) as snapshot:
            return build_review_queue(snapshot, profile)

    def test_reviewed_setup_has_empty_clear_queue_and_no_side_effects(self):
        queue = self.queue()
        before = deepcopy(self.project)
        asset_before = self.asset.read_bytes()
        self.assertEqual(queue["status"], "clear")
        self.assertEqual(queue["items"], [])
        self.assertEqual(queue["authority"], "none")
        self.assertEqual(queue, self.queue())
        self.assertEqual(self.project, before)
        self.assertEqual(self.asset.read_bytes(), asset_before)
        self.assertEqual(list(self.directory.iterdir()), [self.asset])

    def test_semantic_pivot_and_binding_are_separate_layer_exceptions(self):
        self.layer["reviewed_fields"] = [value for value in self.layer["reviewed_fields"]
                                          if value not in {"canonical_role", "side", "pivot_xy", "candidate_bone"}]
        self.layer.pop("candidate_bone")
        self.layer["canonical_role"] = "unclassified.layer"
        self.project["resolved"]["skeleton"]["bones"][0]["id"] = "root-pelvis"
        queue = self.queue()
        reasons = {item["reason_code"]: item for item in queue["items"]}
        for kind in ("semantic", "pivot", "binding"):
            item = reasons[f"{kind}_review_required"]
            self.assertEqual(item["type"], kind)
            self.assertEqual(item["entity_id"], self.layer["id"])
            self.assertEqual(item["evidence"][0]["url"], "/api/projects/sample-a/layers/layer-001-arm-l/image")
            self.assertTrue(item["blocking"])
        self.assertEqual(queue["status"], "needs_review")
        self.assertFalse(any(item["reason_code"] == "layer_review_required" for item in queue["items"]))

    def test_draft_does_not_remove_adapter_preview_review_gate(self):
        self.layer["reviewed_fields"].remove("pivot_xy")
        queue = self.queue("draft_auto")
        self.assertEqual(queue["status"], "needs_review")
        self.assertTrue(queue["items"][0]["blocking"])

    def test_unresolved_joint_is_linked_to_composite(self):
        joint = self.project["resolved"]["skeleton"]["joints"][0]
        joint["review_state"] = "unreviewed"
        joint.pop("decision_kind")
        joint.pop("decision_revision")
        joint["confidence"] = joint["model_confidence"] = 0.2
        queue = self.queue()
        item = next(row for row in queue["items"] if row["type"] == "joint")
        self.assertEqual(item["entity_id"], joint["id"])
        self.assertEqual(item["reason_code"], "joint_review_required")
        self.assertEqual(item["evidence"], [{"kind": "composite_image", "url": "/api/projects/sample-a/composite"}])

    def set_joint_decision(self, action):
        joint = resolved_joint("root", side="center", x=50, y=180, revision=2,
                               review_state="candidate_accepted")
        joint["review_state"] = "unobservable" if action == "unobservable" else "candidate_rejected"
        joint["decision_kind"] = "candidate_unobservable" if action == "unobservable" else "candidate_reject"
        joint["decision"]["action"] = action
        joint["decision"].pop("final_xy")
        if action == "unobservable":
            joint["decision"].pop("candidate_id")
        joint["decision"]["reason"] = "C:/private/raw-notes"
        self.project["resolved"]["skeleton"]["joints"][0] = joint

    def test_rejected_candidate_requires_joint_review(self):
        self.set_joint_decision("reject")
        queue = self.queue()
        item = next(row for row in queue["items"] if row["type"] == "joint")
        self.assertEqual(item["reason_code"], "joint_candidate_rejected")
        self.assertTrue(item["blocking"])

    def test_human_unobservable_decision_remains_information_not_new_gate(self):
        self.set_joint_decision("unobservable")
        queue = self.queue()
        self.assertEqual(queue["status"], "clear")
        self.assertEqual(len(queue["items"]), 1)
        self.assertEqual(queue["items"][0]["reason_code"], "joint_unobservable")
        self.assertFalse(queue["items"][0]["blocking"])
        self.assertNotIn("private", json.dumps(queue))

    def test_split_children_link_to_existing_source_parent_asset(self):
        from tests.test_layer_split_materializer import project_fixture, source_image
        from autospine_workbench.png_rgba import write_rgba_png
        self.project = project_fixture()
        write_rgba_png(self.asset, source_image())
        queue = self.queue()
        split = [item for item in queue["items"] if item["type"] == "split"]
        self.assertTrue(split)
        self.assertEqual(split[0]["reason_code"], "split_review_required")
        children = [item for item in queue["items"] if "--" in item["entity_id"]]
        self.assertTrue(children)
        for item in children:
            self.assertEqual(item["evidence"][0]["url"], "/api/projects/sample-split/layers/layer-001-legs/image")

    def test_unsupported_geometry_is_blocked_not_disguised_as_review(self):
        self.layer["blend_mode"] = "multiply"
        queue = self.queue()
        self.assertEqual(queue["status"], "blocked")
        self.assertIn("region_geometry_unsupported", [row["reason_code"] for row in queue["items"]])

    def test_certification_exact_redirects_to_existing_entry(self):
        queue = self.queue("certification_exact")
        self.assertEqual(queue["status"], "blocked")
        self.assertEqual(queue["items"][0]["reason_code"], "certification_exact_entry_required")

    def test_source_mismatch_and_content_tamper_are_rejected(self):
        self.project["resolved"] = refresh_resolved_snapshot(self.project["resolved"])
        with observe_project(self.store, self.project["id"]) as snapshot:
            invalid = replace(snapshot, source_addresses={**snapshot.source_addresses,
                                                          "layer_manifest_sha256": "f" * 64})
            with self.assertRaises(ReviewQueueError):
                build_review_queue(invalid)
        queue = self.queue()
        queue["queue_sha256"] = "f" * 64
        with self.assertRaises(ReviewQueueError):
            validate_review_queue(queue)

    def test_schema_and_validator_agree_on_closed_fields_and_no_paths(self):
        try:
            from jsonschema import Draft202012Validator
        except ImportError:
            self.skipTest("jsonschema unavailable")
        schema = json.loads((ROOT / "schemas/review-queue-v1.schema.json").read_text())
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema)
        self.layer["reviewed_fields"].remove("pivot_xy")
        queue = self.queue()
        validator.validate(queue)
        mutations = [
            {"authority": "release"}, {"scope": "mesh_runtime"}, {"status": "clear"},
            {"source_addresses": {}}, {"local_path": "private"},
        ]
        for mutation in mutations:
            invalid = reseal({**queue, **mutation})
            self.assertTrue(list(validator.iter_errors(invalid)))
            with self.assertRaises(ReviewQueueError):
                validate_review_queue(invalid)
        for mutation in (
            {"type": "mesh"}, {"blocking": False}, {"risk": "low"},
            {"suggestion": "C:/private/source.psd"}, {"invalidation": ["runtime"]},
            {"evidence": [{"kind": "layer_image", "url": "file:///C:/private.png"}]},
            {"id": "review-unsafe"}, {"rollback": "auto_publish"},
        ):
            invalid = deepcopy(queue)
            invalid["items"][0].update(mutation)
            invalid = reseal(invalid)
            with self.subTest(mutation=mutation):
                self.assertTrue(list(validator.iter_errors(invalid)))
                with self.assertRaises(ReviewQueueError):
                    validate_review_queue(invalid)
        invalid = deepcopy(queue)
        invalid["items"][0]["evidence"][0]["url"] = "/api/projects/other/layers/layer-001-arm-l/image"
        with self.assertRaises(ReviewQueueError):
            validate_review_queue(reseal(invalid))

    def test_item_ids_stay_stable_while_source_bound_queue_hash_changes(self):
        self.layer["reviewed_fields"].remove("pivot_xy")
        before = self.queue()
        self.project["resolved"]["layers"][0]["notes"] = "source authoring change"
        after = self.queue()
        self.assertEqual([row["id"] for row in before["items"]], [row["id"] for row in after["items"]])
        self.assertNotEqual(before["queue_sha256"], after["queue_sha256"])


if __name__ == "__main__":
    unittest.main()
