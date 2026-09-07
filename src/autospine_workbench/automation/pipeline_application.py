"""Project-centric region preview orchestration over the frozen compilation core."""

from pathlib import Path

from ..layer_manifest import LayerManifestBundleStore
from ..manifest_bundle import LayerManifestBundleReader
from ..region_rig import compile_region_rig
from ..region_rig_contract import review_issues
from ..resolved_project import canonical_sha256
from ..rig_bundle import RigBundleStore
from ..rig_bundle_integrity import verify_rig_bundle_directory
from ..rig_setup_probes import run_setup_probes
from .capability_resolver import resolve_capabilities
from .pipeline_lease import execution_lease
from .pipeline_run import OUTPUTS, PipelineRunError, create_run
from .pipeline_run_store import PipelineConflict, PipelineRunStore
from .project_snapshot import observe_project
from .region_preview import build_region_preview, verify_region_preview
from .target_version import DEFAULT_TARGET_VERSION, require_target_version, target_from_run


class PipelineApplication:
    def __init__(self, project_store):
        self.projects = project_store
        self.state_root = Path(project_store.state_root)
        self.runs = PipelineRunStore(self.state_root)

    def capabilities(self, project_id, profile="production_review"):
        with observe_project(self.projects, project_id) as snapshot:
            return resolve_capabilities(snapshot, profile)

    def preview(self, project_id, profile="production_review", *, resume=False,
                expected_resolved_sha256=None, cancel_requested=lambda: False,
                target_version=DEFAULT_TARGET_VERSION):
        require_target_version(target_version)
        with observe_project(self.projects, project_id) as snapshot:
            if expected_resolved_sha256 is not None and snapshot.source_addresses[
                "resolved_project_sha256"
            ] != expected_resolved_sha256:
                raise PipelineRunError("project_changed_during_snapshot")
            initial = create_run(project_id, profile, snapshot.source_addresses, target_version=target_version)
            with execution_lease(self.state_root, initial["run_id"]):
                run = self.runs.create(project_id, profile, snapshot.source_addresses, target_version=target_version)
                if cancel_requested() and run["status"] not in {"succeeded", "canceled"}:
                    return self._append(run, "cancel")
                if run["status"] == "succeeded":
                    self._verify_completed(snapshot, run)
                    snapshot.assert_current()
                    return run
                if run["status"] == "canceled":
                    return run
                if run["status"] != "pending":
                    if not resume:
                        return run
                    run = self._append(run, "resume")
                try:
                    self._verify_completed(snapshot, run)
                    capabilities = resolve_capabilities(snapshot, profile)
                    while run["status"] == "pending":
                        if cancel_requested():
                            return self._append(run, "cancel")
                        index = next(i for i, row in enumerate(run["steps"]) if row["status"] != "succeeded")
                        reason, review = _gate(capabilities, profile, index)
                        if reason:
                            return self._append(run, "review" if review else "block", reason_code=reason)
                        snapshot.assert_current()
                        run = self._append(run, "start")
                        outputs = self._execute_step(index, snapshot, run)
                        if cancel_requested():
                            return self._append(run, "cancel")
                        snapshot.assert_current()
                        run = self._append(run, "succeed", outputs=outputs)
                    return run
                except PipelineConflict:
                    # A concurrent cancellation owns the new journal revision.
                    return self.runs.load(run["run_id"])
                except (OSError, RuntimeError, TypeError, ValueError) as exc:
                    return self._record_failure(run, exc)

    def cancel(self, run_id, expected_sha256):
        return self.runs.append(run_id, expected_sha256, "cancel")

    def _append(self, run, action, **kwargs):
        return self.runs.append(run["run_id"], run["state_sha256"], action, **kwargs)

    def _record_failure(self, run, exc):
        known = {
            "project_changed_during_snapshot", "project_asset_unavailable",
            "pipeline_storage_invalid", "pipeline_revision_conflict",
            "pipeline_artifact_invalid", "pipeline_setup_rejected",
        }
        reason = getattr(exc, "reason_code", None)
        reason = reason if reason in known else "pipeline_step_failed"
        try:
            return self._append(run, "block" if reason == "project_changed_during_snapshot" else "fail",
                                reason_code=reason)
        except PipelineConflict:
            return self.runs.load(run["run_id"])

    def _execute_step(self, index, snapshot, run):
        if index == 0:
            _path, digest = LayerManifestBundleStore(self.state_root).publish(
                snapshot.project_id, snapshot.manifest, snapshot.materialized_assets,
            )
            if digest != snapshot.source_addresses["layer_manifest_sha256"]:
                raise PipelineRunError("pipeline_artifact_invalid")
            self._manifest(snapshot)
            return snapshot.source_addresses
        if index == 1:
            return self._build_rig(snapshot, run["profile"])
        rig = run["steps"][1]["outputs"]
        addresses = build_region_preview(
            self.state_root, snapshot.project_id,
            snapshot.source_addresses["layer_manifest_sha256"],
            rig["rig_sha256"], rig["rig_bundle_sha256"],
            target_version=target_from_run(run),
        )
        return {key: addresses[key] for key in OUTPUTS[2]}

    def _manifest(self, snapshot):
        loaded = LayerManifestBundleReader(self.state_root).load(
            snapshot.project_id, snapshot.source_addresses["layer_manifest_sha256"],
        )
        if loaded.manifest != snapshot.manifest:
            raise PipelineRunError("pipeline_artifact_invalid")
        return loaded

    def _build_rig(self, snapshot, profile):
        manifest = self._manifest(snapshot)
        result = compile_region_rig(
            manifest.manifest, snapshot.resolved, layer_manifest_sha256=manifest.sha256,
            image_sizes=manifest.image_sizes, allow_manual_required=_diagnostic(snapshot, profile),
        )
        rig = result.rig
        digest = canonical_sha256(rig)
        probes = run_setup_probes(rig, manifest.manifest, snapshot.resolved,
                                 rig_sha256=digest, bundle_path=manifest.path)
        if probes["status"] == "rejected":
            raise PipelineRunError("pipeline_setup_rejected")
        path, published = RigBundleStore(self.state_root).publish(
            snapshot.project_id, rig, result.run_manifest, probes, manifest.path,
        )
        verified = verify_rig_bundle_directory(path, expected_project_id=snapshot.project_id)
        if verified.rig_sha256 != digest or published != digest:
            raise PipelineRunError("pipeline_artifact_invalid")
        return {"rig_sha256": digest, "rig_bundle_sha256": verified.bundle_sha256}

    def _verify_completed(self, snapshot, run):
        try:
            if run["steps"][0]["status"] == "succeeded":
                manifest = self._manifest(snapshot)
            if run["steps"][1]["status"] == "succeeded":
                address = run["steps"][1]["outputs"]
                rig = verify_rig_bundle_directory(
                    self.state_root / "builds" / snapshot.project_id / "rig-ir"
                    / address["rig_sha256"] / address["rig_bundle_sha256"],
                    expected_project_id=snapshot.project_id,
                )
                rebuilt = compile_region_rig(
                    manifest.manifest, snapshot.resolved, layer_manifest_sha256=manifest.sha256,
                    image_sizes=manifest.image_sizes, allow_manual_required=_diagnostic(snapshot, run["profile"]),
                )
                if rig.rig != rebuilt.rig or rig.run != rebuilt.run_manifest:
                    raise PipelineRunError("pipeline_artifact_invalid")
            if run["steps"][2]["status"] == "succeeded":
                outputs = run["steps"][2]["outputs"]
                verified = verify_region_preview(
                    self.state_root, snapshot.project_id, outputs["bundle_sha256"],
                    expected_source_addresses={"layer_manifest_sha256": manifest.sha256, **address},
                    target_version=target_from_run(run),
                )
                if any(verified.addresses[key] != value for key, value in outputs.items()):
                    raise PipelineRunError("pipeline_artifact_invalid")
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            raise PipelineRunError("pipeline_artifact_invalid") from exc


def _diagnostic(snapshot, profile):
    return profile == "draft_auto" and bool(review_issues(snapshot.manifest, snapshot.resolved))


def _gate(capabilities, profile, index):
    if profile == "certification_exact":
        return "certification_exact_entry_required", False
    key = {1: "can_build_region_rig", 2: "can_build_spine_preview"}.get(index)
    if key is None or capabilities[key]:
        return None, False
    review_codes = {"project_review_required", "spine_preview_review_required"}
    reasons = [row["reason_code"] for row in capabilities["blocking_items"]]
    reason = next((item for item in reasons if item not in review_codes), None)
    if reason is not None:
        return reason, False
    return ("project_review_required" if index == 1 else "spine_preview_review_required"), True
