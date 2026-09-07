"""Project-centric CLI: python -m autospine_workbench.automation."""

import argparse
import json
from pathlib import Path
import re

from ..project_store import ProjectStore
from .pipeline_application import PipelineApplication
from .preview_download import export_preview
from .target_version import DEFAULT_TARGET_VERSION


def parser():
    result = argparse.ArgumentParser(description="Build a reviewed region Spine setup preview by project.")
    repository = Path(__file__).resolve().parents[3]
    result.add_argument("--workspace", type=Path, default=repository.parent)
    result.add_argument("--state-root", type=Path, default=repository / "workspace")
    commands = result.add_subparsers(dest="command", required=True)
    for name in ("capabilities", "preview"):
        command = commands.add_parser(name)
        command.add_argument("project_id")
        command.add_argument("--profile", default="production_review")
        if name == "preview":
            command.add_argument("--target-version", default=DEFAULT_TARGET_VERSION,
                                 help="Spine JSON target: 4.3.26 (default) or 4.2.")
            command.add_argument("--resume", action="store_true")
            command.add_argument("--output", type=Path, help="Save JSON/Atlas/PNG/QA as a ZIP archive.")
    for name in ("status", "cancel"):
        commands.add_parser(name).add_argument("run_id")
    return result


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        application = PipelineApplication(ProjectStore(
            args.workspace, args.state_root, measure_composite_quality=False,
        ))
        if args.command == "capabilities":
            document = application.capabilities(args.project_id, args.profile)
        elif args.command == "preview":
            document = application.preview(args.project_id, args.profile, resume=args.resume,
                                           target_version=args.target_version)
            if args.output is not None and document["status"] == "succeeded":
                export_preview(application.state_root, document, args.output)
        else:
            document = application.runs.load(args.run_id)
            if args.command == "cancel":
                document = application.cancel(args.run_id, document["state_sha256"])
        print(json.dumps(document, ensure_ascii=False, sort_keys=True, allow_nan=False))
        return {"blocked": 2, "needs_review": 2, "failed": 1, "canceled": 3,
                "running": 2, "pending": 2}.get(document.get("status"), 0)
    except (OSError, RuntimeError, ValueError, TypeError, KeyError) as exc:
        reason = getattr(exc, "reason_code", "pipeline_request_failed")
        if not isinstance(reason, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,79}", reason):
            reason = "pipeline_request_failed"
        print(json.dumps({"status": "failed", "reason_code": reason, "authority": "none"}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
