"""Reproducible source-only engine distributions from a committed Git tree.

Developer release tool, not an installer or a model downloader. The desktop
client installs/verifies this independent artifact outside its own repository.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import zipfile

SCHEMA = "autospine.engine-distribution/v1"
MANIFEST_NAME = "engine-distribution.json"
MAX_FILES, MAX_FILE_BYTES, MAX_TOTAL_BYTES = 10000, 24 * 1024 * 1024, 128 * 1024 * 1024
EXCLUDES = ["user-materials", "workspace-state", "trained-models", "git-history", "tests-and-caches", "uncommitted-changes"]
RUNTIME_DEPENDENCIES = [
    dict(id="python", kind="interpreter", constraint=">=3.11", bundled=False, capabilities=["core"]),
    dict(id="psd-decoder", kind="python-packages", constraint="psd-tools + Pillow", bundled=False, capabilities=["psd_import"]),
    dict(id="analysis", kind="python-packages", constraint="numpy + Pillow", bundled=False, capabilities=["mesh", "projection"]),
    dict(id="cloth-solver", kind="python-packages", constraint="numpy==2.4.6 + scipy==1.18.0", bundled=False, capabilities=["cloth_repair"]),
    dict(id="official-runtime", kind="node-packages", constraint="Node.js + @esotericsoftware/spine-core==4.3.13 + @esotericsoftware/spine-webgl==4.3.13", bundled=False, capabilities=["runtime_validation"]),
    dict(id="framebuffer", kind="node-browser", constraint="playwright-core + compatible Chromium", bundled=False, capabilities=["framebuffer"]),
    dict(id="pose", kind="model-runtime", constraint="requirements-pose-runner.txt + pinned DWPose ONNX", bundled=False, capabilities=["pose"]),
    dict(id="kimodo", kind="model-runtime", constraint="separate Kimodo installation and checkpoints", bundled=False, capabilities=["kimodo"]),
    dict(id="fbx", kind="converter", constraint="separately configured Blender", bundled=False, capabilities=["fbx"]),
]
LIMITATIONS = [
    "Engine source only; Python, Node, browser, third-party runtime packages and models are not bundled.",
    "A matching Python environment and capability dependencies must be separately installed and verified.",
    "Create new workspace/state directories outside this artifact; existing projects are never migrated by this tool.",
    "No clean-machine, pose inference, Kimodo generation, FBX conversion or full character workflow claim follows from inventory verification.",
    "Repository source license is not declared; this artifact does not grant third-party or public redistribution rights.",
]
REQUIRED_FILES = {
    "engine/src/autospine_workbench/__init__.py", "engine/src/autospine_workbench/server.py",
    "engine/src/autospine_workbench/engine_session.py", "engine/src/autospine_workbench/studio_process_lifetime.py",
    "engine/web/index.html", "engine/web/app.js", "engine/pyproject.toml", "engine/requirements-pose-runner.txt",
    "engine/run.ps1", "engine/docs/third-party/dwpose-LICENSE.txt", "engine/DEPLOYMENT.md", "engine/DEPENDENCIES.json",
}
ARCHIVE_ROOTS = ["src", "tools", "web", "schemas", "docs/third-party", "pyproject.toml", "requirements-pose-runner.txt", "run.ps1"]
_DISALLOWED = {".git", ".agents", ".codex", ".aws", ".env", "node_modules", "workspace", "state", "model", "models", "checkpoint", "checkpoints", "__pycache__", "test", "tests", "test-results", "output", "release", "tmp", "assets", "upload", "uploads", "jobs", "projects", "deliveries", "credentials"}
_TOP_FILES = {"pyproject.toml", "requirements-pose-runner.txt", "run.ps1"}


class DistributionError(ValueError):
    pass


def safe_path(value: str) -> PurePosixPath:
    if not isinstance(value, str) or not value or len(value) > 240 or "\\" in value or ":" in value or "\0" in value:
        raise DistributionError("distribution_path_invalid")
    parts = value.split("/")
    if any(not part or part in {".", ".."} for part in parts) or value.startswith("/"):
        raise DistributionError("distribution_path_invalid")
    for part in parts:
        if not re.fullmatch(r"[A-Za-z0-9_-][A-Za-z0-9_.-]*", part) or part.endswith((" ", ".")) or re.match(r"^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)", part, re.I):
            raise DistributionError("distribution_path_invalid")
        if any(ord(char) < 32 for char in part) or any(char in '<>"|?*' for char in part):
            raise DistributionError("distribution_path_invalid")
    return PurePosixPath(value)


def allowed_source_path(value: str) -> bool:
    path = safe_path(value)
    if any(part.lower() in _DISALLOWED for part in path.parts):
        return False
    if path.name.lower().startswith("test_") or ".test." in path.name.lower():
        return False
    if value in _TOP_FILES or value == "docs/third-party/dwpose-LICENSE.txt":
        return True
    if len(path.parts) >= 3 and path.parts[:2] == ("src", "autospine_workbench"):
        return path.suffix in {".py", ".js", ".html", ".css"}
    if path.parts[0] == "tools" and len(path.parts) >= 2:
        return path.suffix in {".py", ".js", ".mjs", ".cjs", ".ps1", ".html", ".css"}
    if path.parts[0] == "schemas" and len(path.parts) == 2:
        return path.name.endswith(".schema.json")
    if path.parts[0] == "web":
        if value in {"web/workflow-catalog.json", "web/package.json"}:
            return True
        if len(path.parts) == 2:
            return path.suffix in {".js", ".html", ".css"}
        return path.parts[1] == "modules" and path.suffix in {".js", ".json", ".css"}
    return False


def allowed_distribution_path(value: str) -> bool:
    path = safe_path(value)
    if path.parts[0] != "engine" or len(path.parts) < 2:
        return False
    source = str(PurePosixPath(*path.parts[1:]))
    return source in {"DEPLOYMENT.md", "DEPENDENCIES.json"} or allowed_source_path(source)


def canonical_bytes(value) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _deployment(commit: str) -> bytes:
    return (f"""# AutoSpine independent engine source

Source commit: `{commit}`. Scope: **engine-source-only**.

This archive preserves the engine source layout and excludes PSDs, project state,
trained models, Git history and uncommitted changes. It contains no Python, Node,
browser, dependency environment or weights. DEPENDENCIES.json declares capability
prerequisites; inventory verification does not prove those capabilities work.

Verify the manifest and its externally supplied SHA-256 before installing.
Extract into a new version directory, never over an existing engine or workspace.
Create separate empty workspace/state directories. In Studio's Run Environment
panel, select this archive's engine directory and a matching Python 3.11+ runtime.
Studio starts its managed loopback service on an OS-assigned port automatically.
The current installer must separately record workspace/state paths; choosing
engine/Python alone does not create a complete clean-machine setup.

PSD import needs psd-tools/Pillow in core Python. Mesh/projection need NumPy/Pillow;
cloth solving uses the exact optional versions in pyproject.toml. Official Runtime
checks need separate Node/Spine packages; GPU capture needs its configured browser.
Pose/Kimodo use separate model environments. This tool installs/downloads none of
them; existing models and projects stay untouched.

The DWPose license text is included for attribution; its model is excluded.
Repository source licensing is not declared. This artifact does not grant public
redistribution rights or bundle a Spine runtime license.

Developer fallback: run engine/run.ps1 with explicit PythonExe, WorkspaceRoot,
StateRoot and Port 0. Studio uses its stronger managed-process launcher with
session ownership and lifecycle handling; users need not start a service.
""").encode("utf-8")


def payload_from_archive(raw: bytes, commit: str) -> dict[str, bytes]:
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise DistributionError("distribution_commit_invalid")
    payload, seen, total = {}, set(), 0
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            for item in archive.infolist():
                if item.is_dir():
                    safe_path(item.filename.rstrip("/"))
                    continue
                safe_path(item.filename)
                mode = item.external_attr >> 16
                if stat.S_ISLNK(mode) or (stat.S_IFMT(mode) and not stat.S_ISREG(mode)):
                    raise DistributionError("distribution_source_link")
                if not allowed_source_path(item.filename):
                    continue
                key = "engine/" + item.filename
                if key.lower() in seen:
                    raise DistributionError("distribution_duplicate_path")
                seen.add(key.lower())
                if item.file_size > MAX_FILE_BYTES:
                    raise DistributionError("distribution_size_limit")
                data = archive.read(item)
                total += len(data)
                if total > MAX_TOTAL_BYTES or len(payload) >= MAX_FILES:
                    raise DistributionError("distribution_size_limit")
                payload[key] = data
    except zipfile.BadZipFile as exc:
        raise DistributionError("distribution_archive_invalid") from exc
    payload["engine/DEPLOYMENT.md"] = _deployment(commit)
    payload["engine/DEPENDENCIES.json"] = canonical_bytes({"scope": "engine-source-only", "runtime_dependencies": RUNTIME_DEPENDENCIES, "limitations": LIMITATIONS})
    if not REQUIRED_FILES <= payload.keys():
        raise DistributionError("distribution_required_files_missing")
    return payload


def manifest_for(payload: dict[str, bytes], commit: str) -> dict:
    files = [dict(path=name, bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest()) for name, raw in sorted(payload.items())]
    result = dict(schema=SCHEMA, component="engine-source", scope="engine-source-only", version="0.1.0+git." + commit[:12], source_commit=commit,
                  platform="windows-x64", engine_root="engine", files=files, excludes=EXCLUDES, runtime_dependencies=RUNTIME_DEPENDENCIES, limitations=LIMITATIONS)
    validate_manifest(result)
    return result


def validate_manifest(value: dict) -> dict:
    required = {"schema", "component", "scope", "version", "source_commit", "platform", "engine_root", "files", "excludes", "runtime_dependencies", "limitations"}
    if type(value) is not dict or set(value) != required or value.get("schema") != SCHEMA or value.get("component") != "engine-source" or value.get("scope") != "engine-source-only" or value.get("platform") != "windows-x64" or value.get("engine_root") != "engine":
        raise DistributionError("distribution_manifest_invalid")
    commit = value.get("source_commit")
    if not isinstance(commit, str) or not re.fullmatch(r"[0-9a-f]{40}", commit) or value.get("version") != "0.1.0+git." + commit[:12]:
        raise DistributionError("distribution_commit_invalid")
    if value["excludes"] != EXCLUDES or value["runtime_dependencies"] != RUNTIME_DEPENDENCIES or value["limitations"] != LIMITATIONS:
        raise DistributionError("distribution_scope_invalid")
    records = value["files"]
    if type(records) is not list or not 1 <= len(records) <= MAX_FILES:
        raise DistributionError("distribution_inventory_invalid")
    seen, total = set(), 0
    for record in records:
        if type(record) is not dict or set(record) != {"path", "bytes", "sha256"} or not allowed_distribution_path(record.get("path")):
            raise DistributionError("distribution_inventory_invalid")
        key = record["path"].lower()
        if key in seen:
            raise DistributionError("distribution_duplicate_path")
        seen.add(key)
        if type(record["bytes"]) is not int or not 0 <= record["bytes"] <= MAX_FILE_BYTES or not isinstance(record["sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", record["sha256"]):
            raise DistributionError("distribution_inventory_invalid")
        total += record["bytes"]
    if total > MAX_TOTAL_BYTES:
        raise DistributionError("distribution_size_limit")
    if not REQUIRED_FILES <= {record["path"] for record in records}:
        raise DistributionError("distribution_required_files_missing")
    return dict(files=len(records), bytes=total, scope="engine-source-only", source_commit=commit)


def verify_directory(root: Path, *, validator=validate_manifest) -> dict:
    root = Path(root).absolute()
    def identity(path):
        info = path.lstat()
        return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns
    def linked(path):
        info = path.lstat()
        return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & 0x400)
    if linked(root) or not root.is_dir():
        raise DistributionError("distribution_directory_invalid")
    manifest_path = root / MANIFEST_NAME
    if linked(manifest_path) or not manifest_path.is_file() or manifest_path.stat().st_nlink != 1 or manifest_path.stat().st_size > 4 * 1024 * 1024:
        raise DistributionError("distribution_manifest_invalid")
    manifest_identity = identity(manifest_path)
    with manifest_path.open("rb") as stream:
        manifest_raw = stream.read(4 * 1024 * 1024 + 1)
    if len(manifest_raw) > 4 * 1024 * 1024:
        raise DistributionError("distribution_manifest_invalid")
    try:
        manifest = json.loads(manifest_raw.decode("utf-8"))
    except (ValueError, UnicodeError) as exc:
        raise DistributionError("distribution_manifest_invalid") from exc
    summary = validator(manifest)
    records = {item["path"]: item for item in manifest["files"]}
    found = set()
    directories, identities = {}, {}
    for folder, dirs, files in os.walk(root, followlinks=False):
        directories[Path(folder)] = identity(Path(folder))
        for name in dirs:
            path = Path(folder) / name
            relative = path.relative_to(root).as_posix()
            if linked(path) or not any(file.startswith(relative + "/") for file in records):
                raise DistributionError("distribution_extra_directory")
        for name in files:
            path = Path(folder) / name
            relative = path.relative_to(root).as_posix()
            if linked(path) or not path.is_file() or path.stat().st_nlink != 1:
                raise DistributionError("distribution_file_invalid")
            if relative == MANIFEST_NAME:
                continue
            if relative not in records:
                raise DistributionError("distribution_extra_file")
            record = records[relative]
            before, count, digest = identity(path), 0, hashlib.sha256()
            with path.open("rb") as stream:
                while raw := stream.read(1024 * 1024):
                    count += len(raw)
                    if count > record["bytes"]:
                        raise DistributionError("distribution_hash_mismatch")
                    digest.update(raw)
            if count != record["bytes"] or digest.hexdigest() != record["sha256"]:
                raise DistributionError("distribution_hash_mismatch")
            if identity(path) != before or linked(path):
                raise DistributionError("distribution_changed")
            identities[path] = before
            found.add(relative)
    if found != records.keys():
        raise DistributionError("distribution_missing_file")
    if identity(manifest_path) != manifest_identity or any(identity(file) != before or linked(file) for file, before in identities.items()) or any(identity(folder) != before or linked(folder) for folder, before in directories.items()):
        raise DistributionError("distribution_changed")
    summary["manifest_sha256"] = hashlib.sha256(manifest_raw).hexdigest()
    return summary


def _git(repo: Path, *args) -> bytes:
    # Limit Git's owner exception to this explicit read-only source checkout.
    result = subprocess.run(["git", "-c", "safe.directory=" + str(repo), "-C", str(repo), *args], capture_output=True, timeout=120, check=False)
    if result.returncode:
        raise DistributionError("distribution_git_failed: " + result.stderr.decode("utf-8", "replace")[:500])
    return result.stdout


def archive_distribution(root: Path, zip_path: Path, *, validator=validate_manifest) -> dict:
    """Archive an immutable verified artifact, recheck the ZIP and source.

    No extraction, installation, source rewriting or output replacement occurs.
    A failed newly created ZIP is preserved, never promoted as verified output.
    """
    root, zip_path = Path(root).absolute(), Path(zip_path).absolute()
    if zip_path.suffix.lower() != ".zip" or zip_path.is_relative_to(root) or zip_path.exists() or zip_path.is_symlink():
        raise DistributionError("distribution_archive_destination_invalid")
    before = verify_directory(root, validator=validator)
    manifest_path = root / MANIFEST_NAME
    manifest_raw = manifest_path.read_bytes()
    if hashlib.sha256(manifest_raw).hexdigest() != before["manifest_sha256"]:
        raise DistributionError("distribution_changed")
    manifest = json.loads(manifest_raw.decode("utf-8"))
    records = {row["path"]: row for row in manifest["files"]}
    records[MANIFEST_NAME] = dict(path=MANIFEST_NAME, bytes=len(manifest_raw), sha256=before["manifest_sha256"])
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, record in sorted(records.items()):
            item = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            item.create_system = 3
            item.external_attr = (stat.S_IFREG | 0o644) << 16
            item.compress_type = zipfile.ZIP_DEFLATED
            item.file_size = record["bytes"]
            count, digest = 0, hashlib.sha256()
            with (root / name).open("rb") as source, archive.open(item, "w") as target:
                while raw := source.read(1024 * 1024):
                    count += len(raw)
                    if count > record["bytes"]:
                        raise DistributionError("distribution_changed")
                    digest.update(raw); target.write(raw)
            if count != record["bytes"] or digest.hexdigest() != record["sha256"]:
                raise DistributionError("distribution_changed")
    with zipfile.ZipFile(zip_path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)) or set(names) != records.keys():
            raise DistributionError("distribution_archive_inventory_mismatch")
        for item in archive.infolist():
            record = records[item.filename]
            if item.is_dir() or item.flag_bits & 1 or item.file_size != record["bytes"] or not stat.S_ISREG(item.external_attr >> 16):
                raise DistributionError("distribution_archive_inventory_mismatch")
            count, digest = 0, hashlib.sha256()
            with archive.open(item) as source:
                while raw := source.read(1024 * 1024):
                    count += len(raw)
                    if count > record["bytes"]:
                        raise DistributionError("distribution_archive_inventory_mismatch")
                    digest.update(raw)
            if count != record["bytes"] or digest.hexdigest() != record["sha256"]:
                raise DistributionError("distribution_archive_hash_mismatch")
    after = verify_directory(root, validator=validator)
    if after != before:
        raise DistributionError("distribution_changed")
    with zip_path.open("rb") as stream:
        archive_sha256 = hashlib.file_digest(stream, "sha256").hexdigest()
    return dict(**before, directory=str(root), archive=str(zip_path), archive_bytes=zip_path.stat().st_size,
                archive_entries=len(records), archive_payload_bytes=sum(row["bytes"] for row in records.values()),
                archive_sha256=archive_sha256, archive_verified=True, source_unchanged=True)


def package_engine(repo: Path, destination: Path, *, commit: str | None = None) -> dict:
    repo, destination = Path(repo).resolve(strict=True), Path(destination).absolute()
    commit = commit or _git(repo, "rev-parse", "HEAD").decode("ascii").strip()
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise DistributionError("distribution_commit_invalid")
    resolved = _git(repo, "rev-parse", commit + "^{commit}").decode("ascii").strip()
    if resolved != commit:
        raise DistributionError("distribution_commit_invalid")
    zip_path = Path(str(destination) + ".zip")
    if destination.exists() or destination.is_symlink() or zip_path.exists():
        raise DistributionError("distribution_destination_exists")
    # A committed archive cannot include the user's dirty working tree.
    payload = payload_from_archive(_git(repo, "archive", "--format=zip", commit, *ARCHIVE_ROOTS), commit)
    manifest = manifest_for(payload, commit)
    payload[MANIFEST_NAME] = canonical_bytes(manifest)
    destination.mkdir(parents=True, exist_ok=False)
    for name, raw in sorted(payload.items()):
        file = destination.joinpath(*PurePosixPath(name).parts)
        file.parent.mkdir(parents=True, exist_ok=True)
        with file.open("xb") as stream:
            stream.write(raw)
    summary = verify_directory(destination)
    with zipfile.ZipFile(zip_path, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, raw in sorted(payload.items()):
            item = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            item.create_system = 3
            item.external_attr = (stat.S_IFREG | 0o644) << 16
            item.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(item, raw, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    return dict(**summary, directory=str(destination), archive=str(zip_path), archive_sha256=hashlib.sha256(zip_path.read_bytes()).hexdigest())


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build")
    build.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    build.add_argument("--output", type=Path, required=True)
    build.add_argument("--commit")
    verify = sub.add_parser("verify")
    verify.add_argument("directory", type=Path)
    archive = sub.add_parser("archive")
    archive.add_argument("directory", type=Path)
    archive.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "build":
            result = package_engine(args.repo, args.output, commit=args.commit)
        elif args.command == "archive":
            with (args.directory / MANIFEST_NAME).open("rb") as stream:
                manifest_raw = stream.read(4 * 1024 * 1024 + 1)
            if len(manifest_raw) > 4 * 1024 * 1024:
                raise DistributionError("distribution_manifest_invalid")
            scope = json.loads(manifest_raw.decode("utf-8")).get("scope")
            validator = validate_manifest
            if scope == "engine-core-runtime":
                from smoke_engine_distribution import validate_core_manifest
                validator = validate_core_manifest
            result = archive_distribution(args.directory, args.output, validator=validator)
        else:
            result = verify_directory(args.directory)
        print(json.dumps(dict(ok=True, **result), ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, zipfile.BadZipFile) as exc:
        print(json.dumps(dict(ok=False, reason=str(exc)), ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
