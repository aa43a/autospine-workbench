"""Bounded animation, actual weighted geometry and recoverable preview integration."""

from contextlib import contextmanager
from copy import deepcopy
import hashlib
from io import BytesIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from autospine_workbench.automation.animated_application import AnimatedApplication
from autospine_workbench.automation.animated_compile import prepare_mesh, compile_preview
from autospine_workbench.automation.animated_motion import build_motion
from autospine_workbench.automation.animated_package import package_preview
from autospine_workbench.automation.pipeline_run import PipelineRunError
from tests.test_mesh_candidate import fixture


def source_fixture():
    from PIL import Image
    from autospine_workbench.asset.joints.reviewed_skeleton import build_reviewed_skeleton
    from autospine_workbench.asset.joints.layer_binding import build_layer_bindings
    from autospine_workbench.benchmark.layer_binding_draft import build_layer_binding_draft
    from autospine_workbench.resolved_project import canonical_sha256
    candidate, assisted, _, _, _, images = fixture()
    for row in candidate["layers"]:
        if row["layer_id"] in images:
            continue
        x, y, r, b = row["bbox"]
        stream = BytesIO()
        Image.new("RGBA", (r-x, b-y), (150, 120, 90, 255)).save(stream, format="PNG")
        raw = stream.getvalue()
        images[row["layer_id"]] = raw
        row.update(image_sha256=hashlib.sha256(raw).hexdigest(),
                   image={"sha256": hashlib.sha256(raw).hexdigest(), "byte_size": len(raw)})
    assisted["candidate_sha256"] = assisted["draft"]["candidate_sha256"] = canonical_sha256(candidate)
    skeleton = build_reviewed_skeleton(candidate, assisted)
    bindings = build_layer_bindings(candidate, assisted, skeleton)
    draft = build_layer_binding_draft(bindings)
    return SimpleNamespace(candidate=candidate, assisted=assisted, skeleton=skeleton,
                           bindings=bindings, draft=draft, images=images, composite=b"",
                           source_addresses={"resolved_project_sha256": "a"*64,
                                             "input_identity_sha256": "b"*64}, assert_current=lambda: None)


class AnimatedApplicationTests(unittest.TestCase):
    def setUp(self):
        self.inputs = source_fixture()
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.projects = SimpleNamespace(state_root=Path(temp.name))
        self.app = AnimatedApplication(self.projects)
        @contextmanager
        def load(*_):
            yield self.inputs
            self.inputs.assert_current()
        patcher = patch("autospine_workbench.automation.animated_application.load_inputs", load)
        patcher.start()
        self.addCleanup(patcher.stop)
        def current(store, project_id, addresses):
            if addresses != self.inputs.source_addresses:
                raise PipelineRunError("animated_input_changed")
            self.inputs.assert_current()
        guard = patch("autospine_workbench.automation.animated_application.assert_registered_current", current)
        guard.start()
        self.addCleanup(guard.stop)

    def preview(self, **kwargs):
        return self.app.preview("project", "a"*64, "limb-flex-15", **kwargs)

    def test_real_mesh_preview_preserves_pending_and_has_exact_loop(self):
        original = deepcopy(self.inputs.draft)
        stage = prepare_mesh(self.inputs)
        compiled = compile_preview(self.inputs, stage, "limb-flex-15")
        self.assertEqual(self.inputs.draft, original)
        self.assertEqual(stage["preview_hypothesis_layers"], ["layer-001"])
        self.assertGreater(compiled["summary"]["mesh_layers"], 0)
        self.assertLess(compiled["qa"]["setup_max_error_px"], 1e-7)
        self.assertTrue(all(r["passed"] for r in compiled["qa"]["geometry"]["regions"].values()))
        files = package_preview(self.inputs, compiled)
        frames = json.loads(files["playback.json"])["frames"]
        self.assertEqual(frames[0]["vertices"], frames[-1]["vertices"])
        self.assertNotEqual(frames[0]["vertices"], frames[15]["vertices"])
        self.assertEqual(files["images/layer-001.png"], self.inputs.images["layer-001"])
        self.assertEqual(compiled["qa"]["runtime_status"], "not_run")

    def test_resume_cached_stages_and_cancel_without_fake_revision(self):
        def cancel():
            return any(self.app.store.runs.glob("*/mesh.json"))
        run = self.preview(cancel_requested=cancel)
        self.assertEqual(run["status"], "canceled")
        with patch("autospine_workbench.automation.animated_application.prepare_mesh", side_effect=AssertionError("must reuse")):
            ready = self.preview()
        self.assertEqual(ready["status"], "needs_review")
        self.assertTrue(ready["preview_available"])
        self.assertEqual(run["run_id"], ready["run_id"])
        with patch("autospine_workbench.automation.animated_application.compile_preview", side_effect=AssertionError("must reuse")):
            self.assertEqual(self.preview(), ready)

    def test_download_tamper_stale_source_and_wrong_project_are_rejected(self):
        run = self.preview()
        files = self.app.verified_files("project", run)
        self.assertIn("editor/skeleton.json", files)
        self.assertEqual(self.app.verified_file("project", run, "skeleton.json"), files["skeleton.json"])
        with self.assertRaises(PipelineRunError):
            self.app.verified_files("other", run)
        self.inputs.source_addresses["input_identity_sha256"] = "c"*64
        with self.assertRaises(PipelineRunError):
            self.app.verified_files("project", run)
        with self.assertRaises(PipelineRunError):
            self.app.verified_file("project", run, "skeleton.json")
        self.inputs.source_addresses["input_identity_sha256"] = "b"*64
        digest = run["steps"][2]["outputs"]["bundle_sha256"]
        (self.app.store.root / digest / "skeleton.json").write_bytes(b"{}")
        with self.assertRaises(PipelineRunError):
            self.app.verified_files("project", run)

    def test_unknown_clip_and_stale_request_fail_before_compilation(self):
        with self.assertRaisesRegex(PipelineRunError, "animated_clip_unsupported"):
            build_motion("turn-around", [])
        with self.assertRaisesRegex(PipelineRunError, "project_snapshot_stale"):
            self.app.preview("project", "f"*64, "limb-flex-15")

    def test_engine_upgrade_keeps_readable_snapshot_but_cannot_resume_old_identity(self):
        from autospine_workbench.automation.animated_run import validate_run
        run = self.preview()
        original = self.app.verified_files('project', run)
        with patch('autospine_workbench.automation.animated_run.engine_identity', return_value='f'*64):
            with self.assertRaisesRegex(PipelineRunError, 'animated_run_invalid'):
                validate_run(run)
            self.assertEqual(self.app.verified_files('project', run), original)
            self.assertEqual(self.app.verified_file('project', run, 'skeleton.json'), original['skeleton.json'])
            changed = deepcopy(run); changed['engine_sha256'] = 'e'*64
            with self.assertRaises(PipelineRunError):
                self.app.verified_files('project', changed)
            fresh = self.preview()
            self.assertNotEqual(fresh['run_id'], run['run_id'])
            self.assertEqual(self.app.verified_files('project', run), original)

    def test_other_clip_checkpoint_cannot_be_reused(self):
        from autospine_workbench.automation.animated_run import create_run
        from autospine_workbench.automation.storage_io import publish_document
        first = self.preview()
        other = create_run("project", self.inputs.source_addresses, "limb-flex-30")
        folder = self.app.store.run_path(other["run_id"])
        # Point at a perfectly intact package generated for a different request.
        publish_document(folder / "preview.json", {"stage": "preview", "bundle_sha256":
            first["steps"][2]["outputs"]["bundle_sha256"]}, staging=folder / "staging")
        with self.assertRaisesRegex(PipelineRunError, "animated_stage_identity_mismatch"):
            self.app.preview("project", "a"*64, "limb-flex-30")

    def test_source_change_before_publication_keeps_preview_unavailable(self):
        def changed():
            if any(self.app.store.runs.glob("*/mesh.json")):
                raise PipelineRunError("animated_input_changed")
        self.inputs.assert_current = changed
        with self.assertRaisesRegex(PipelineRunError, "animated_input_changed"):
            self.preview()
        self.assertFalse(any(self.app.store.runs.glob("*/result.json")))

    def test_resealed_scope_and_qa_cannot_bypass_single_file_validation(self):
        from autospine_workbench.automation.storage_io import canonical_bytes
        original_run = self.preview()
        original_files = self.app.verified_files("project", original_run)
        for mutation in ("animation", "authority", "qa", "file_inventory"):
            files = dict(original_files)
            scope = json.loads(files["preview-manifest.json"])
            if mutation == "animation":
                scope["animation"] = "limb-flex-30"
            elif mutation == "authority":
                scope["production_authorized"] = True
            elif mutation == "qa":
                qa = json.loads(files["qa.json"])
                qa["runtime_status"] = "passed"
                files["qa.json"] = canonical_bytes(qa)
                scope["files"]["qa.json"] = hashlib.sha256(files["qa.json"]).hexdigest()
            else:
                scope["files"]["skeleton.json"] = "f" * 64
            files["preview-manifest.json"] = canonical_bytes(scope)
            digest = self.app.store.publish(files)
            run = deepcopy(original_run)
            run["steps"][2]["outputs"]["bundle_sha256"] = digest
            folder = self.app.store.run_path(run["run_id"])
            (folder / "preview.json").write_bytes(canonical_bytes({"stage": "preview", "bundle_sha256": digest}))
            (folder / "result.json").write_bytes(canonical_bytes(run))
            with self.subTest(mutation=mutation, reader="single"), self.assertRaises(PipelineRunError):
                self.app.verified_file("project", run, "skeleton.json")
            with self.subTest(mutation=mutation, reader="zip"), self.assertRaises(PipelineRunError):
                self.app.verified_files("project", run)


if __name__ == "__main__":
    unittest.main()
