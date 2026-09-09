"""Operator setup and SHA-free project animation preview commands."""

import argparse
import json
from pathlib import Path

from ..benchmark.artifacts import read_input
from ..benchmark.elbow_target_cli import archive, export
from ..manifest_artifacts import require_safe_token
from ..project_store import ProjectStore
from ..resolved_project import canonical_sha256
from ..safe_input_files import read_real_file
from .animated_application import AnimatedApplication
from .animated_inputs import register_inputs
from .animated_store import _publish_bytes
from .project_snapshot import _read
from .storage_io import directory


def import_audit(store, project_id, audit_directory):
    """Copy an audit byte-for-byte; paths in its data do not choose destinations."""
    require_safe_token(project_id, "Project id")
    source = directory(Path(audit_directory).absolute())
    target = store.audit_root / project_id
    files = list(source.rglob("*"))
    if len(files) > 2048:
        raise ValueError("animated_audit_resource_limit")
    total, prepared = 0, {}
    for path in sorted(files):
        if path.is_dir():
            directory(path)
            continue
        relative = path.relative_to(source)
        if path.suffix.lower() not in {".json", ".png"}:
            continue
        raw = read_real_file(path, 64 << 20, "audit import")
        total += len(raw)
        if total > 256 << 20:
            raise ValueError("animated_audit_resource_limit")
        prepared[relative] = raw
    if Path("audit.json") not in prepared:
        raise ValueError("animated_audit_missing")
    # Check all bytes before publication; publish the discovery marker last.
    for relative, raw in prepared.items():
        destination = target / relative
        if destination.exists() and read_real_file(destination, 64 << 20, "audit import") != raw:
            raise ValueError("animated_audit_conflict")
    for relative in sorted(prepared, key=lambda p: (p == Path("audit.json"), str(p))):
        _publish_bytes(target / relative, prepared[relative])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path(".."))
    parser.add_argument("--state-root", type=Path, default=Path("workspace"))
    sub = parser.add_subparsers(dest="action", required=True)
    register = sub.add_parser("register", help="Register an existing exact annotation/binding source")
    register.add_argument("project")
    register.add_argument("--manifest", type=Path, required=True)
    register.add_argument("--draft", type=Path, required=True)
    register.add_argument("--audit-directory", type=Path)
    preview = sub.add_parser("preview", help="Build by project identity, with no manual addresses")
    preview.add_argument("project")
    preview.add_argument("--clip", default="limb-flex-15")
    preview.add_argument("--output", type=Path)
    options = parser.parse_args(argv)
    store = ProjectStore(options.workspace, state_root=options.state_root, measure_composite_quality=False)
    if options.action == "register":
        if options.audit_directory:
            import_audit(store, options.project, options.audit_directory)
        digest = register_inputs(store, options.project, read_input(options.manifest),
                                 canonical_sha256(read_input(options.draft)))
        result = {"project_id": options.project, "registration_sha256": digest, "authority": "none"}
    else:
        app = AnimatedApplication(store)
        result = app.preview(options.project, _read(store, options.project)[2].resolved_project_sha256, options.clip)
        if options.output and result["preview_available"]:
            export(options.output, archive(app.verified_files(options.project, result)))
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
