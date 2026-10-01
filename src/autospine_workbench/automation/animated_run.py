"""Separate operation identity; frozen region PipelineRun v1 remains byte-stable."""

from copy import deepcopy
import hashlib
from pathlib import Path

from ..resolved_project import canonical_sha256
from .pipeline_run import PipelineRunError

STEPS = ("resolve-project", "build-weighted-mesh", "compile-animated-preview", "review-animation")
ENGINE = "workbench-weighted-animation-v1"


def engine_identity():
    root = Path(__file__).resolve().parents[1]
    paths = {root / "automation" / name for name in (
        "animated_compile.py", "animated_motion.py", "animated_package.py", "animated_partitions.py", "animated_run.py",
        "animated_binding_safety.py")}
    for folder in ("asset/joints", "targets/spine43"):
        paths.update((root / folder).glob("*.py"))
    paths.update(root.glob("alpha_grid*.py"))
    paths.update(root.glob("png_rgba*.py"))
    paths.add(root / "benchmark/layer_binding_draft.py")
    return canonical_sha256({str(p.relative_to(root)).replace("\\", "/"):
                             hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths)})


def create_run(project_id, addresses, clip):
    identity = {"project_id": project_id, "source_addresses": deepcopy(addresses),
                "clip": clip, "engine": ENGINE, "engine_sha256": engine_identity(), "target_version": "4.3.26"}
    return {"schema": "autospine.animated-pipeline-run/v1", **identity,
            "run_id": "run-" + canonical_sha256(identity), "authority": "none",
            "status": "pending", "preview_available": False, "summary": {}, "review_items": [],
            "steps": [{"id": name, "status": "pending", "outputs": {}, "reason_code": None} for name in STEPS]}


def validate_run(run, *, historical=False):
    try:
        if historical:
            from ..manifest_artifacts import require_sha256
            require_sha256(run['engine_sha256'], 'Animated engine')
            identity = {key: run[key] for key in ('project_id', 'source_addresses', 'clip', 'engine_sha256')}
            identity.update(engine=ENGINE, target_version='4.3.26')
            expected = dict(identity, schema='autospine.animated-pipeline-run/v1',
                            run_id='run-'+canonical_sha256(identity), authority='none')
        else:
            expected = create_run(run["project_id"], run["source_addresses"], run["clip"])
        for key in ("schema", "engine", "engine_sha256", "run_id", "authority", "target_version"):
            if expected[key] != run[key]:
                raise PipelineRunError("animated_run_invalid")
        if [step["id"] for step in run["steps"]] != list(STEPS):
            raise PipelineRunError("animated_run_invalid")
        if run["preview_available"]:
            if run["status"] != "needs_review" or any(
                s["status"] != "succeeded" for s in run["steps"][:3]
            ) or run["steps"][3]["status"] != "needs_review":
                raise PipelineRunError("animated_run_invalid")
    except (KeyError, TypeError, ValueError) as exc:
        raise PipelineRunError("animated_run_invalid") from exc
    return run
