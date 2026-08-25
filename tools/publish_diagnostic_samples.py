"""Publish P1 artifacts from resolved setup joints for diagnostic use only.

This tool deliberately does not run a pose model.  It turns the current
resolved setup limb joints into a canonical pose v1 document with zero scores
and unknown visibility, then passes that temporary document to the production
``pose-geometry`` analysis command.  It never writes overrides or revisions.
"""

from __future__ import annotations

import argparse
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import sys
import tempfile
from typing import Any, Sequence


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPOSITORY_ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from autospine_workbench.candidate_provenance import sha256_file  # noqa: E402
from autospine_workbench.pose_commands import analyze_joints  # noqa: E402
from autospine_workbench.project_store import ProjectStore  # noqa: E402
from autospine_workbench.resolved_project import canonical_sha256  # noqa: E402


DEFAULT_PROJECT_IDS = ("seethrough_output", "seethrough_output_5")
LIMB_JOINT_IDS = tuple(
    f"{name}.{side}"
    for name in ("shoulder", "elbow", "wrist", "hip", "knee", "ankle")
    for side in ("left", "right")
)
DIAGNOSTIC_NOTICE = (
    "Current resolved setup joints are diagnostic priors, not pose-model predictions."
)


def build_diagnostic_pose(store: ProjectStore, project_id: str) -> dict[str, Any]:
    """Build a deterministic canonical pose v1 from the resolved setup."""

    project = store.get_project(project_id)
    resolved = project["resolved"]
    setup_joints = {
        item["id"]: item for item in resolved["skeleton"]["joints"]
    }
    missing = sorted(set(LIMB_JOINT_IDS) - set(setup_joints))
    if missing:
        raise ValueError(f"Resolved setup is missing limb joints: {', '.join(missing)}")

    config = {
        "purpose": "diagnostic-only",
        "prior": "resolved-setup-prior",
        "policy_version": 1,
        "resolved_snapshot_sha256": resolved["sha256"],
        "joint_ids": list(LIMB_JOINT_IDS),
        "score_policy": "constant-zero-not-model-confidence",
        "visibility_policy": "constant-unknown",
    }
    composite = store.resolve_asset(project_id, "composite")
    canvas = project["canvas"]
    return {
        "format": "autospine-pose-observations",
        "format_version": 1,
        "project_id": project_id,
        "source": {
            "image_kind": "composite",
            "image_sha256": sha256_file(composite, "project composite"),
            "canvas_size": [canvas["width"], canvas["height"]],
        },
        "detector": {
            "id": "resolved-setup-prior",
            "version": "diagnostic-only-v1",
            "model_revision": "resolved-setup-prior/diagnostic-only",
            "config_sha256": canonical_sha256(config),
            "runtime": "diagnostic-only",
        },
        "subject": {
            "detected_count": 1,
            "selected_index": 0,
            "selection_method": "single",
        },
        "coordinate_system": {
            "origin": "top_left",
            "x_axis": "right",
            "y_axis": "down",
            "units": "pixel",
            "side_naming": "character_side",
        },
        "joints": {
            joint_id: {
                "xy": [
                    round(float(setup_joints[joint_id]["x"]), 6),
                    round(float(setup_joints[joint_id]["y"]), 6),
                ],
                "detector_score": 0.0,
                "visibility": "unknown",
            }
            for joint_id in LIMB_JOINT_IDS
        },
    }


def publish_diagnostic_project(
    workspace: Path,
    state_root: Path,
    project_id: str,
    *,
    alpha_threshold: int = 8,
) -> dict[str, Any]:
    """Publish pose, geometry, and candidates without changing project state."""

    store = ProjectStore(workspace, state_root=state_root)
    revision_before = store.get_project(project_id)["overrides"]["revision"]
    pose_document = build_diagnostic_pose(store, project_id)
    with tempfile.TemporaryDirectory(prefix="autospine-diagnostic-pose-") as directory:
        pose_path = Path(directory) / f"{project_id}.pose-v1.json"
        pose_path.write_text(
            json.dumps(pose_document, ensure_ascii=False, sort_keys=True),
            encoding="utf-8",
        )
        output = io.StringIO()
        with redirect_stdout(output):
            status = analyze_joints(
                project_id,
                workspace,
                state_root,
                provider_name="pose-geometry",
                pose_path=pose_path,
                alpha_threshold=alpha_threshold,
            )
    response = json.loads(output.getvalue())
    revision_after = store.get_project(project_id)["overrides"]["revision"]
    if revision_after != revision_before:
        raise RuntimeError("Project revision changed during diagnostic publication")
    if status != 0 or not response.get("ok"):
        raise RuntimeError(str(response.get("error") or "Diagnostic publication failed"))
    return {
        "project_id": project_id,
        "ok": True,
        "diagnostic_only": True,
        "not_model_accuracy": True,
        "pose_prior": "resolved-setup-prior",
        "notice": DIAGNOSTIC_NOTICE,
        "revision_before": revision_before,
        "revision_after": revision_after,
        "revision_unchanged": True,
        "pose_document_sha256": canonical_sha256(pose_document),
        "artifacts": response["artifacts"],
    }


def publish_diagnostic_samples(
    workspace: Path,
    state_root: Path,
    project_ids: Sequence[str] = DEFAULT_PROJECT_IDS,
    *,
    alpha_threshold: int = 8,
) -> dict[str, Any]:
    """Publish one or more explicitly non-model diagnostic sample chains."""

    projects = [
        publish_diagnostic_project(
            workspace, state_root, project_id, alpha_threshold=alpha_threshold
        )
        for project_id in project_ids
    ]
    return {
        "ok": True,
        "diagnostic_only": True,
        "not_model_accuracy": True,
        "notice": DIAGNOSTIC_NOTICE,
        "projects": projects,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=DIAGNOSTIC_NOTICE)
    parser.add_argument(
        "project_ids", nargs="*", default=list(DEFAULT_PROJECT_IDS),
        help="Project IDs (defaults to both supplied See-through samples)",
    )
    parser.add_argument(
        "--workspace", type=Path, default=REPOSITORY_ROOT.parent,
        help="Workspace containing tmp/psd_audit/results",
    )
    parser.add_argument(
        "--state-root", type=Path, default=REPOSITORY_ROOT / "workspace",
        help="Workbench state root for immutable analysis artifacts",
    )
    parser.add_argument("--alpha-threshold", type=int, default=8)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = publish_diagnostic_samples(
            args.workspace,
            args.state_root,
            args.project_ids,
            alpha_threshold=args.alpha_threshold,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        result = {
            "ok": False,
            "diagnostic_only": True,
            "not_model_accuracy": True,
            "error": str(exc),
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
