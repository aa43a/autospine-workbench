"""Bounded author-input replay must not carry jobs or manufacture acceptance."""
from hashlib import sha256
import importlib.util
import json
import os
from pathlib import Path
from copy import deepcopy
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from zipfile import ZipFile


TOOL = Path(__file__).resolve().parents[1] / "tools/check-studio-continuous-production.py"
SPEC = importlib.util.spec_from_file_location("studio_continuous_fixture", TOOL)
fixture = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(fixture)


class FixtureBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.state = self.root / "original-state"
        self.state.mkdir()
        self.case = fixture.CASES["molisha"]
        self.project = "imported-" + self.case["psd_sha256"]
        self.registration = f"animation-inputs/{self.project}/000001.json"

    def tearDown(self):
        self.temporary.cleanup()

    def source(self, relative, raw=b'{"origin":"original-human-input"}'):
        path = self.state / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        return path

    def test_exact_case_namespaces_reject_old_jobs_acceptance_and_other_projects(self):
        valid = [self.registration,
                 f"benchmarks/{self.case['dataset']}/assisted-joint-drafts/{'a' * 64}.json",
                 f"input-preparation/source-bundles/{self.case['bundle']}/layers/layer-003.png"]
        for relative in valid:
            self.assertTrue(fixture.restore_target_allowed(relative, self.case), relative)
        invalid = ["jobs/character-web-v1/request.json", "builds/old/skeleton.json",
                   "jobs/motion-intake-v1/motion-old/stage-reviews/review-0001.json",
                   self.registration.replace(self.project, "imported-" + "b" * 64),
                   self.registration.replace("/000001", "//000001"),
                   "../" + self.registration, self.registration + "/",
                   self.registration.replace("/", "\\"), "C:/" + self.registration]
        for relative in invalid:
            self.assertFalse(fixture.restore_target_allowed(relative, self.case), relative)

    def test_wide_only_allows_fixed_annotation_and_mesh_namespaces(self):
        wide = fixture.CASES["paqiuli"]
        project = "imported-" + wide["psd_sha256"]
        revision = f"sleeve-onboarding-v1/{project}/revision-000000000005.json"
        mesh = f"benchmarks/project-component-partitions/weighted-mesh-candidates/{'c' * 64}.json"
        for relative in (revision, mesh):
            self.assertTrue(fixture.restore_target_allowed(relative, wide))
            self.assertFalse(fixture.restore_target_allowed(relative, self.case))
        self.assertFalse(fixture.restore_target_allowed(
            revision.replace("000000000005", "5"), wide))
        self.assertFalse(fixture.restore_target_allowed(
            f"jobs/sleeve-web-v1/{project}/accepted.json", wide))

    def test_digest_named_document_rejects_tampering_or_authority(self):
        document = dict(schema="test/v1", authority="none", production_authorized=False,
                        reviewed_joint_ids=["joint-from-original-review"])
        digest = fixture.canonical_sha256(document)
        relative = f"benchmarks/{self.case['dataset']}/assisted-joint-drafts/{digest}.json"
        path = self.source(relative, json.dumps(document).encode())
        plan = fixture.ClosurePlan(self.state, self.case)
        plan.add(relative, document_digest=True)
        path.write_text(json.dumps(dict(document, reviewed_joint_ids=[])), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "author_document_digest_mismatch"):
            plan.add(relative, document_digest=True)
        authorized = dict(document, production_authorized=True)
        bad = f"benchmarks/{self.case['dataset']}/assisted-joint-drafts/{fixture.canonical_sha256(authorized)}.json"
        self.source(bad, json.dumps(authorized).encode())
        with self.assertRaisesRegex(ValueError, "author_document_authorized"):
            plan.add(bad, document_digest=True)

    def test_copy_is_byte_exact_and_retains_original_provenance(self):
        raw = b'{ "origin": "manual", "independent_annotation": false, "reviewed_joint_ids": ["neck"] }\n'
        original = self.source(self.registration, raw)
        plan = fixture.ClosurePlan(self.state, self.case)
        plan.add(self.registration)
        destination = self.root / "own-state"
        destination.mkdir()
        fixture.copy_author_closure(plan, destination)
        self.assertEqual((destination / self.registration).read_bytes(), raw)
        self.assertEqual(original.read_bytes(), raw)
        self.assertEqual(plan.rows()[0]["sha256"], sha256(raw).hexdigest())
        self.assertFalse((destination / "jobs").exists())

    def test_source_change_before_copy_is_rejected_without_publishing(self):
        original = self.source(self.registration)
        plan = fixture.ClosurePlan(self.state, self.case)
        plan.add(self.registration)
        original.write_bytes(b'{"origin":"replacement"}')
        destination = self.root / "own-state"
        destination.mkdir()
        with self.assertRaisesRegex(ValueError, "source_inventory_changed"):
            fixture.copy_author_closure(plan, destination)
        self.assertEqual(list(destination.iterdir()), [])

    def test_destination_with_old_jobs_or_existing_input_is_rejected(self):
        self.source(self.registration)
        plan = fixture.ClosurePlan(self.state, self.case)
        plan.add(self.registration)
        destination = self.root / "own-state"
        (destination / "jobs").mkdir(parents=True)
        with self.assertRaisesRegex(ValueError, "old_jobs_present"):
            fixture.copy_author_closure(plan, destination)
        other = self.root / "other-state"
        (other / self.registration).parent.mkdir(parents=True)
        (other / self.registration).write_bytes(b"keep existing")
        with self.assertRaises(FileExistsError):
            fixture.copy_author_closure(plan, other)
        self.assertEqual((other / self.registration).read_bytes(), b"keep existing")

    def test_hardlinked_input_is_rejected(self):
        original = self.source(self.registration)
        alias = self.root / "alias.json"
        os.link(original, alias)
        with self.assertRaisesRegex(ValueError, "source_not_real_file"):
            fixture.fingerprint(original, self.state)

    def test_output_must_be_empty_and_not_source_owned(self):
        audit = self.root / "source-audit"
        audit.mkdir()
        for path in (self.state, self.state / "child", audit, audit / "child"):
            with self.assertRaisesRegex(ValueError, "output_overlaps_source"):
                fixture.reserve_output(path, self.state, audit)
        output = self.root / "output"
        output.mkdir()
        (output / "old-evidence.json").write_bytes(b"keep")
        with self.assertRaisesRegex(ValueError, "output_not_empty"):
            fixture.reserve_output(output, self.state, audit)
        self.assertEqual((output / "old-evidence.json").read_bytes(), b"keep")

    def test_context_restores_runtime_configuration_without_writing_settings(self):
        before = dict(AUTOSPINE_BLENDER="original-blender", AUTOSPINE_CAPTURE_NODE="original-node")
        with patch.dict(os.environ, before, clear=True):
            with fixture.runtime_environment(self.root / "blender.exe", self.root / "capture"):
                self.assertEqual(os.environ["AUTOSPINE_CAPTURE_NODE"], str(self.root / "capture/node/node.exe"))
                self.assertEqual(os.environ["PYTHONDONTWRITEBYTECODE"], "1")
            self.assertEqual(dict(os.environ), before)

    def test_closure_budget_is_bounded(self):
        self.source(self.registration)
        plan = fixture.ClosurePlan(self.state, self.case)
        with patch.object(fixture, "MAX_FILES", 0):
            with self.assertRaisesRegex(ValueError, "author_closure_limit"):
                plan.add(self.registration)

    def test_fixed_distribution_covers_empty_official_files_and_rejects_extra_payload(self):
        bundle = self.root / "runtime"
        bundle.mkdir()
        (bundle / "empty.py").write_bytes(b"")
        document = dict(schema="fixed-test/v1", profile="fixed", files=[
            dict(path="empty.py", bytes=0, sha256=sha256(b"").hexdigest())])
        raw = json.dumps(document).encode()
        (bundle / "distribution.json").write_bytes(raw)
        arguments = (bundle, "distribution.json", sha256(raw).hexdigest(), "fixed-test/v1", "profile", "fixed", 1)
        inventory = fixture.distribution_snapshot(*arguments)
        self.assertEqual(inventory["empty.py"]["bytes"], 0)
        (bundle / "foreign.dll").write_bytes(b"extra executable")
        with self.assertRaisesRegex(ValueError, "runtime_inventory_invalid|runtime_inventory_unlisted_file"):
            fixture.distribution_snapshot(*arguments)

    def test_fixed_distribution_rejects_mutated_payload_even_with_same_size(self):
        bundle = self.root / "runtime"
        bundle.mkdir()
        (bundle / "payload.exe").write_bytes(b"aaaa")
        document = dict(schema="fixed-test/v1", profile="fixed", files=[
            dict(path="payload.exe", bytes=4, sha256=sha256(b"aaaa").hexdigest())])
        raw = json.dumps(document).encode()
        (bundle / "distribution.json").write_bytes(raw)
        (bundle / "payload.exe").write_bytes(b"bbbb")
        with self.assertRaisesRegex(ValueError, "runtime_bundle_digest_mismatch"):
            fixture.distribution_snapshot(bundle, "distribution.json", sha256(raw).hexdigest(),
                                          "fixed-test/v1", "profile", "fixed", 1)

    def test_agent_rule_is_fixed_to_exact_region_and_original_texture(self):
        manifest = dict(source_addresses=dict(resolved_project_sha256="original-resolved"), layers=[
            dict(layer_id="layer-005", name="earwear", state="static_reference",
                 regions=[dict(region_id="layer-005", state="static_reference")], missing_region_ids=[])])
        files = {"character-manifest.json": json.dumps(manifest).encode(),
                 "skeleton.json": b'{"bones":[{"name":"head"}]}', "images/layer-005.png": b"changed"}
        with self.assertRaisesRegex(ValueError, "earwear_texture_changed"):
            fixture.earwear_context(files, "original-resolved")
        changed = deepcopy(manifest)
        changed["layers"][0]["regions"][0]["region_id"] = "different-region"
        files["character-manifest.json"] = json.dumps(changed).encode()
        with self.assertRaisesRegex(ValueError, "earwear_region_context_changed"):
            fixture.earwear_context(files, "original-resolved")
        with self.assertRaisesRegex(ValueError, "earwear_source_context_changed"):
            fixture.earwear_context(files, "different-resolved")

    def test_resume_gate_rejects_partial_or_human_accepted_runs(self):
        report = dict(ok=True, schema="autospine.studio-continuous-production-test/v1",
                      scope="existing-author-input-replay", status="new_candidates_exported_needs_review",
                      human_visual_acceptance=False, source_state_written=False,
                      frozen_engine_source_unchanged=True)
        fixture.require_completed_owned_report(report)
        for delta in (dict(status="planned_not_executed"), dict(ok=False),
                      dict(human_visual_acceptance=True), dict(source_state_written=True),
                      dict(frozen_engine_source_unchanged=False), dict(scope="user-production")):
            with self.assertRaisesRegex(ValueError, "only_completed_owned_run"):
                fixture.require_completed_owned_report(dict(report, **delta))

    def test_skirt_agent_strategy_rejects_changed_region_or_texture(self):
        manifest = dict(source_addresses=dict(resolved_project_sha256="original-resolved"), layers=[
            dict(layer_id="layer-006", name="bottomwear", state="static_reference",
                 regions=[dict(region_id="layer-006", state="static_reference")], missing_region_ids=[])])
        files = {"character-manifest.json": json.dumps(manifest).encode(),
                 "skeleton.json": b'{"bones":[{"name":"chest"},{"name":"pelvis"}]}',
                 "images/layer-006.png": b"changed"}
        with self.assertRaisesRegex(ValueError, "skirt_texture_changed"):
            fixture.skirt_context(files, "molisha", "original-resolved")
        manifest["layers"][0]["name"] = "objects"
        files["character-manifest.json"] = json.dumps(manifest).encode()
        with self.assertRaisesRegex(ValueError, "skirt_region_context_changed"):
            fixture.skirt_context(files, "molisha", "original-resolved")

    def test_frozen_release_pin_rejects_unknown_manifest_and_added_log(self):
        engine = self.root / "frozen/engine"
        engine.mkdir(parents=True)
        (engine / "fixed.py").write_bytes(b"fixed source")
        manifest = dict(engine_root="engine", source_commit="a" * 40,
            files=[dict(path="engine/fixed.py", bytes=12, sha256=sha256(b"fixed source").hexdigest())])
        path = engine.parent / "engine-distribution.json"
        path.write_text(json.dumps(manifest), encoding="utf-8")
        digest = sha256(path.read_bytes()).hexdigest()
        with patch.object(fixture, "ENGINE", engine), patch.dict(fixture.FROZEN_RELEASES,
                {digest: dict(source_commit_prefix="a" * 40, files=1)}):
            actual = fixture.engine_source_snapshot(digest)
            self.assertEqual(actual["files"], 1)
            with self.assertRaisesRegex(ValueError, "engine_not_explicit_fixed_release"):
                fixture.engine_source_snapshot("b" * 64)
            (engine / "debug.log").write_bytes(b"unlisted browser log")
            with self.assertRaisesRegex(ValueError, "engine_source_inventory_invalid"):
                fixture.engine_source_snapshot(digest)

    def test_first_production_omission_keeps_legacy_and_recipe_is_typed(self):
        original = fixture.production_request("project", "motion-new", {"yaw": 0}, {"face": True})
        self.assertIsNone(original["character_job_id"])
        self.assertNotIn("character_options", original)
        selected = fixture.production_request("project", "motion-new", {}, {}, "reviewed-torso-waist-v2")
        self.assertEqual(selected["character_options"], {"skirt_profile": "reviewed-torso-waist-v2"})
        self.assertNotIn("skirt_profile", selected["body_options"])
        with self.assertRaisesRegex(ValueError, "fixture_character_profile_invalid"):
            fixture.production_request("project", "motion-new", {}, {}, "unverified-recipe")

    def test_retained_residual_identity_rejects_other_missing_regions_and_changed_texture(self):
        addresses = {"resolved_project_sha256": "source-resolved"}
        residuals = dict(fixture.PAQIULI_RESIDUALS)
        raw = {region: region.encode() for region in residuals}
        pinned = {region: sha256(data).hexdigest() for region, data in raw.items()}
        layers = [dict(layer_id=region[:9], unresolved=True, missing_region_ids=[],
                       regions=[dict(region_id=region, state="static_reference"),
                                dict(region_id=region[:9] + "-component-0000", state="weighted_candidate")])
                  for region in residuals]
        manifest = dict(authority="none", production_authorized=False, source_addresses=addresses, layers=layers)
        files = {"character-manifest.json": json.dumps(manifest).encode(),
                 **{"images/" + key + ".png": value for key, value in raw.items()}}
        coverage = dict(layers=deepcopy(layers), unresolved_layer_count=2)
        with patch.object(fixture, "PAQIULI_RESIDUALS", pinned):
            evidence = fixture.residual_retention_evidence(files, files, files, addresses, coverage)
            self.assertTrue(evidence["verified"])
            self.assertFalse(evidence["complete_character_coverage"])
            self.assertEqual(evidence["other_unresolved_region_ids"], [])
            changed = dict(files, **{"images/layer-003-unbound-residual.png": b"changed"})
            with self.assertRaisesRegex(ValueError, "retained_residual_texture_changed"):
                fixture.residual_retention_evidence(files, files, changed, addresses, coverage)
            incomplete = deepcopy(coverage)
            incomplete["unresolved_layer_count"] = 3
            incomplete["layers"].append(dict(layer_id="layer-006", unresolved=True, missing_region_ids=[],
                regions=[dict(region_id="layer-006", state="static_reference")]))
            with self.assertRaisesRegex(ValueError, "other_unresolved_character_regions"):
                fixture.residual_retention_evidence(files, files, files, addresses, incomplete)
            with self.assertRaisesRegex(ValueError, "retained_residual_source_changed"):
                fixture.residual_retention_evidence(files, files, files,
                    {"resolved_project_sha256": "different-source"}, coverage)

    def test_technical_summary_keeps_geometry_failure_and_depth_missing_counts(self):
        archive = self.root / "candidate.zip"
        documents = {
            "deformation.json": dict(passed=False, records=[dict(passed=False, failing_frame_count=5,
                inversion_samples=0, sample_count=29)]),
            "motion-depth.json": dict(status="needs_review", ambiguous_pair_samples=12,
                target_overlap=dict(unmeasured_pair_samples=12, order_mismatch_pair_samples=0, visible_pair_samples=0)),
            "motion-review.json": dict(issues=["source limitation"]),
        }
        with ZipFile(archive, "w") as bundle:
            for name, value in documents.items():
                bundle.writestr(name, json.dumps(value))
        review = dict(readiness=dict(status="needs_changes", stages=[
            dict(stage="Runtime", status="sampled_pass", frames=29),
            dict(stage="遮挡", status="unmeasured"), dict(stage="几何", status="needs_changes")]))
        actual = fixture.technical_statistics(review, archive)
        self.assertEqual(actual["runtime"], [dict(status="sampled_pass", frames=29)])
        self.assertEqual(actual["geometry"]["failing_attachment_frame_samples"], 5)
        self.assertFalse(actual["geometry"]["passed"])
        self.assertEqual(actual["depth"]["unmeasured_pair_samples"], 12)
        self.assertEqual(actual["unmeasured_stages"], ["遮挡"])
        self.assertFalse(actual["human_visual_acceptance"])


if __name__ == "__main__":
    unittest.main()
