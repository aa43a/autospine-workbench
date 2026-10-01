"""Project-level candidate mesh, motion, review and downloadable Spine orchestration."""

from copy import deepcopy
import json
from types import SimpleNamespace

from .animated_compile import compile_preview, prepare_mesh
from .animated_inputs import AnimatedSourceError, load_inputs, save_binding_review
from .animated_input_index import inspect_registration, assert_registered_current
from .animated_motion import CLIPS, build_motion
from .animated_package import package_preview
from .animated_run import create_run, validate_run
from .animated_store import AnimatedStore
from .pipeline_lease import execution_lease
from .pipeline_run import PipelineRunError
from .project_snapshot import _read
from .storage_io import canonical_bytes, publish_document, read_document


class AnimatedApplication:
    def __init__(self, project_store):
        self.projects = project_store
        self.store = AnimatedStore(project_store.state_root)

    def overview(self, project_id):
        _, _, key = _read(self.projects, project_id)
        result = {"schema": "autospine.animated-overview/v1", "project_id": project_id,
                  "resolved_project_sha256": key.resolved_project_sha256,
                  "authority": "none", "target_version": "4.3.26",
                  "clips": [{"id": r["id"], "label": r["label"]} for r in CLIPS],
                  "can_build": False, "reason_code": None, "review_items": []}
        try:
            info = inspect_registration(self.projects, project_id)
            names = {row["layer_id"]: row.get("name", "") for row in info["candidate"]["layers"]}
            review_bindings = [dict(row, name=names.get(row["layer_id"], ""))
                               for row in info["bindings"]["bindings"]]
            result.update(can_build=True, input_identity_sha256=info["source_addresses"]["input_identity_sha256"],
                          binding_review={"bindings": review_bindings, "records": info["draft"]["records"]},
                          verification="registration_only")
            from .animated_binding_safety import partition_hints
            result['binding_review']['partition_hints'] = partition_hints(self.projects, project_id, info)
            result["review_items"] = [{"id": r["layer_id"] + ":binding", "layer_id": r["layer_id"],
                                           "type": "binding", "reason_code": "binding_selection_required"}
                                      for r in info["draft"]["records"] if r["action"] == "pending"]
            if info.get('skeleton_status') != 'candidate_requires_review':
                result.update(can_build=False, reason_code='joint_review_required')
                result['review_items'].insert(0, dict(id='skeleton', type='joint', reason_code='joint_review_required'))
        except AnimatedSourceError as exc:
            result["reason_code"] = exc.reason_code
            if exc.reason_code == "animated_source_stale":
                from .animated_rebase import preview_rebase
                result["source_rebase"] = preview_rebase(self.projects, project_id)
        return result

    def rebase(self, project_id, expected_resolved_sha256, expected_registration_sha256):
        from .animated_rebase import rebase_inputs
        result = rebase_inputs(self.projects, project_id, expected_resolved_sha256,
                               expected_registration_sha256)
        return {**self.overview(project_id), "joint_review_result": result}

    def review(self, project_id, expected_resolved_sha256, expected_input_sha256, records):
        if _read(self.projects, project_id)[2].resolved_project_sha256 != expected_resolved_sha256:
            raise PipelineRunError("project_snapshot_stale")
        save_binding_review(self.projects, project_id, expected_input_sha256, records)
        return self.overview(project_id)

    def joints(self, project_id):
        from .animated_joint_review import get_joint_review
        return get_joint_review(self.projects, project_id)

    def rig_plan(self, project_id):
        from .project_rig_plan import read_plan
        return read_plan(self.projects, project_id)

    def prepare_rig_plan(self, project_id, expected_resolved_sha256, expected_input_sha256):
        from .project_rig_plan import prepare_plan
        return prepare_plan(self.projects, project_id, expected_resolved_sha256, expected_input_sha256)

    def complete_bindings(self, project_id, expected_resolved_sha256, expected_input_sha256):
        from .animated_binding_completion import complete_bindings
        result = complete_bindings(self.projects, project_id, expected_resolved_sha256, expected_input_sha256)
        return {**self.overview(project_id), 'binding_completion_result': result}

    def review_joints(self, project_id, expected_resolved_sha256, expected_input_sha256,
                      records, reviewed_joint_ids):
        from .animated_joint_review import save_joint_review
        if _read(self.projects, project_id)[2].resolved_project_sha256 != expected_resolved_sha256:
            raise PipelineRunError("project_snapshot_stale")
        result = save_joint_review(self.projects, project_id, expected_input_sha256, records, reviewed_joint_ids)
        from .binding_stage_continuation import continue_after_review
        return continue_after_review(self, project_id, result)

    def preview(self, project_id, expected_resolved_sha256, clip, resume=True,
                cancel_requested=lambda: False, progress=lambda steps: None):
        build_motion(clip, [])
        with load_inputs(self.projects, project_id) as inputs:
            if inputs.source_addresses["resolved_project_sha256"] != expected_resolved_sha256:
                raise PipelineRunError("project_snapshot_stale")
            run = create_run(project_id, inputs.source_addresses, clip)
            if inputs.skeleton.get("status") != "candidate_requires_review":
                run.update(status="needs_review", review_items=[{
                    "id": "skeleton", "type": "joint", "reason_code": "joint_review_required"}])
                run["steps"][0].update(status="needs_review", reason_code="joint_review_required")
                return run
            with execution_lease(self.projects.state_root, run["run_id"]):
                path = self.store.run_path(run["run_id"])
                if (path / "result.json").exists():
                    saved = read_document(path / "result.json")
                    self._verify_saved(saved, inputs)
                    return saved
                def step(index, status, **updates):
                    run["status"] = "running"
                    run["steps"][index].update(status=status, **updates)
                    progress(deepcopy(run["steps"]))
                def canceled():
                    inputs.assert_current()
                    if cancel_requested():
                        run.update(status="canceled", preview_available=False)
                        next(s for s in run["steps"] if s["status"] != "succeeded").update(
                            status="canceled", reason_code="pipeline_canceled")
                        return True
                    return False
                step(0, "succeeded", outputs=inputs.source_addresses)
                if canceled():
                    return run
                step(1, "running")
                mesh_sha = self.store.checkpoint(run["run_id"], "mesh")
                if mesh_sha is not None and not resume:
                    run.update(status="blocked")
                    run["steps"][1].update(status="blocked", reason_code="pipeline_resume_required")
                    return run
                if mesh_sha is None:
                    mesh = prepare_mesh(inputs)
                    mesh["stage_identity"] = self._stage_identity(run)
                    inputs.assert_current()
                    mesh_sha = self.store.publish({"mesh.json": canonical_bytes(mesh)})
                    self.store.checkpoint(run["run_id"], "mesh", mesh_sha)
                else:
                    mesh = json.loads(self.store.read(mesh_sha)["mesh.json"])
                if mesh.get("stage_identity") != self._stage_identity(run):
                    raise PipelineRunError("animated_stage_identity_mismatch")
                step(1, "succeeded", outputs={"mesh_bundle_sha256": mesh_sha})
                if canceled():
                    return run
                step(2, "running")
                preview_sha = self.store.checkpoint(run["run_id"], "preview")
                if preview_sha is None:
                    compiled = compile_preview(inputs, mesh, clip)
                    files = package_preview(inputs, compiled)
                    scope = json.loads(files["preview-manifest.json"])
                    scope["stage_identity"] = self._stage_identity(run)
                    files["preview-manifest.json"] = canonical_bytes(scope)
                    inputs.assert_current()
                    preview_sha = self.store.publish(files)
                    self.store.checkpoint(run["run_id"], "preview", preview_sha)
                else:
                    files = self.store.read(preview_sha)
                scope = json.loads(files["preview-manifest.json"])
                self._verify_scope(run, files, scope)
                step(2, "succeeded", outputs={"bundle_sha256": preview_sha})
                if canceled():
                    return run
                run.update(status="needs_review", preview_available=True,
                           summary=scope["summary"], review_items=scope["review_items"])
                run["steps"][3].update(status="needs_review", reason_code="animated_review_required")
                validate_run(run)
                inputs.assert_current()
                publish_document(path / "result.json", run, staging=path / "staging")
                self._verify_saved(run, inputs)
                progress(deepcopy(run["steps"]))
                return run

    def _verify_saved(self, run, inputs, *, historical=False):
        validate_run(run, historical=historical)
        expected = run if historical else create_run(run["project_id"], inputs.source_addresses, run["clip"])
        path = self.store.run_path(expected["run_id"])
        if run["run_id"] != expected["run_id"] or read_document(path / "result.json") != run:
            raise PipelineRunError("animated_input_changed")
        digest = run["steps"][2]["outputs"]["bundle_sha256"]
        if self.store.checkpoint(run["run_id"], "preview") != digest:
            raise PipelineRunError("pipeline_artifact_invalid")
        files = self.store.read(digest)
        scope = json.loads(files["preview-manifest.json"])
        self._verify_scope(run, files, scope)
        if scope["source_addresses"] != inputs.source_addresses or scope["summary"] != run["summary"] \
                or scope["review_items"] != run["review_items"]:
            raise PipelineRunError("pipeline_artifact_invalid")
        inputs.assert_current()
        return files

    def verified_files(self, project_id, run):
        if run.get("project_id") != project_id or not run.get("preview_available"):
            raise PipelineRunError("pipeline_preview_not_ready")
        def check():
            assert_registered_current(self.projects, project_id, run["source_addresses"])
        check()
        inputs = SimpleNamespace(source_addresses=run["source_addresses"], assert_current=check)
        return self._verify_saved(run, inputs, historical=True)

    def verified_file(self, project_id, run, name):
        import hashlib
        if run.get("project_id") != project_id or not run.get("preview_available"):
            raise PipelineRunError("pipeline_preview_not_ready")
        assert_registered_current(self.projects, project_id, run["source_addresses"])
        validate_run(run, historical=True)
        folder = self.store.run_path(run["run_id"])
        if read_document(folder / "result.json") != run:
            raise PipelineRunError("pipeline_artifact_invalid")
        digest = run["steps"][2]["outputs"]["bundle_sha256"]
        if read_document(folder / "preview.json") != {"stage": "preview", "bundle_sha256": digest}:
            raise PipelineRunError("pipeline_artifact_invalid")
        scope = json.loads(self.store.read_file(digest, "preview-manifest.json"))
        inventory = read_document(self.store.root / digest / "inventory.json")
        expected = {key: value for key, value in inventory.items() if key != "preview-manifest.json"}
        qa = json.loads(self.store.read_file(digest, "qa.json"))
        if scope.get("stage_identity") != self._stage_identity(run) \
                or scope.get("source_addresses") != run["source_addresses"] \
                or scope.get("animation") != run["clip"] or scope.get("authority") != "none" \
                or scope.get("production_authorized") is not False or scope.get("files") != expected \
                or qa.get("authority") != "none" or qa.get("runtime_status") != "not_run":
            raise PipelineRunError("animated_stage_identity_mismatch")
        raw = self.store.read_file(digest, name)
        if name != "preview-manifest.json" and hashlib.sha256(raw).hexdigest() != scope["files"].get(name):
            raise PipelineRunError("pipeline_artifact_invalid")
        assert_registered_current(self.projects, project_id, run["source_addresses"])
        return raw

    @staticmethod
    def _stage_identity(run):
        return {key: run[key] for key in ("run_id", "source_addresses", "clip", "engine_sha256", "target_version")}

    def _verify_scope(self, run, files, scope):
        import hashlib
        expected = {name: hashlib.sha256(raw).hexdigest() for name, raw in files.items()
                    if name != "preview-manifest.json"}
        qa = json.loads(files["qa.json"])
        if scope.get("stage_identity") != self._stage_identity(run) or scope.get("files") != expected \
                or scope.get("animation") != run["clip"] or scope.get("authority") != "none" \
                or scope.get("production_authorized") is not False or qa.get("authority") != "none" \
                or qa.get("runtime_status") != "not_run":
            raise PipelineRunError("animated_stage_identity_mismatch")
