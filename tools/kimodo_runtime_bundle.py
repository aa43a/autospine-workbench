"""Build a private fixed Kimodo addon from separately audited local inputs.

No downloads, inference, editable installs, symlinks, developer venv, or Git
history are included. This tool does not grant model redistribution rights.
The output is a new directory; existing source, models and packages stay intact.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import stat
import sys

sys.dont_write_bytecode = True

SCHEMA = "autospine.kimodo-runtime-distribution/v1"
MANIFEST = "kimodo-distribution.json"
PROFILE = "fixed-source-python31210-kimodo-soma-rp11-v1"
PROVENANCE = "provenance/runtime.json"
PYTHON_MANIFEST = "kimodo-python-manifest.json"
MAX_FILES = 40000
MAX_FILE = 8 << 30
MAX_TOTAL = 26 << 30
ADDITIONAL_NOTICES = {
    "text-encoders/LLM2Vec-Meta-Llama-3-8B-Instruct-mntp-supervised/README.md": (
        62702, "e821992eb2485dcbab0f8903ae3819d806db6f587dfd179adafe31ef28fdda1d"),
}


def additional_notices(runtime):
    """Keep the separately supplied supervised-adapter notice, fully pinned."""
    rows = []
    for name, (size, digest) in ADDITIONAL_NOTICES.items():
        streamed(runtime / name, expected=dict(byte_length=size, sha256=digest))
        rows.append(dict(path=name, byte_length=size, sha256=digest))
    return rows


def canonical(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def identity(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_nlink,
            info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def opened_identity(info):
    # Handle stats cannot infer executable permission bits from a Windows .exe
    # pathname. The regular-file check remains explicit on both observations.
    return (info.st_dev, info.st_ino, info.st_nlink, info.st_size, info.st_mtime_ns)


def regular(path):
    info = path.lstat()
    if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or path.is_symlink()
            or getattr(info, "st_file_attributes", 0) & 0x400):
        raise ValueError("kimodo_bundle_file_unsafe: " + str(path))
    return info


def directory(path):
    for entry in reversed((path, *path.parents)):
        info = entry.lstat()
        if (not stat.S_ISDIR(info.st_mode) or entry.is_symlink()
                or getattr(info, "st_file_attributes", 0) & 0x400):
            raise ValueError("kimodo_bundle_directory_unsafe: " + str(entry))
    return path


def streamed(path, *, output=None, expected=None):
    before = regular(path)
    if before.st_size > MAX_FILE:
        raise ValueError("kimodo_bundle_file_limit")
    digest, count = sha256(), 0
    with path.open("rb") as src:
        opened = os.fstat(src.fileno())
        # Windows lstat/fstat expose different legacy ctime semantics. Compare
        # their inode/size/mtime identity; ctime is still checked within each
        # observation method before and after the complete byte stream.
        if not stat.S_ISREG(opened.st_mode) or opened_identity(opened) != opened_identity(before):
            raise ValueError("kimodo_bundle_changed")
        target = output.open("xb") if output else None
        try:
            while chunk := src.read(8 << 20):
                count += len(chunk)
                if count > before.st_size:
                    raise ValueError("kimodo_bundle_changed")
                digest.update(chunk)
                if target:
                    target.write(chunk)
            if target:
                target.flush()
                os.fsync(target.fileno())
            if (identity(os.fstat(src.fileno())) != identity(opened)
                    or identity(regular(path)) != identity(before)):
                raise ValueError("kimodo_bundle_changed")
        finally:
            if target:
                target.close()
    result = dict(byte_length=count, sha256=digest.hexdigest())
    if count != before.st_size or (expected and result != expected):
        raise ValueError("kimodo_bundle_digest_mismatch: " + str(path))
    return result


def tree_digest(rows):
    digest = sha256()
    for row in sorted(rows, key=lambda r: r["path"]):
        digest.update((row["path"] + "\0" + str(row["bytes"]) + "\0"
                       + row["sha256"] + "\n").encode("utf-8"))
    return digest.hexdigest()


def stage(runtime, python_stage, output, *, git_executable):
    """Copy only fixed audited Python and required model closure into a new addon."""
    from kimodo_portable_python import safe_path, strict_json, verify_python_stage
    from autospine_workbench.automation.motion_generation_runtime_plan import build_runtime_integrity_plan

    runtime, python_stage = directory(Path(runtime).absolute()), directory(Path(python_stage).absolute())
    output = Path(output).absolute()
    directory(output.parent)
    if output.exists() or any(output == p or output.is_relative_to(p) for p in (runtime, python_stage)):
        raise ValueError("kimodo_bundle_output_not_new")
    print(json.dumps(dict(step="verify-python", output=str(output))), flush=True)
    python_report = verify_python_stage(python_stage)
    python_raw = (python_stage / PYTHON_MANIFEST).read_bytes()
    python_manifest = strict_json(python_raw)
    print(json.dumps(dict(step="verify-all-model-bytes")), flush=True)
    models = build_runtime_integrity_plan(runtime, git_executable=git_executable,
                                         verify_weight_bytes=True)
    if not models["all_required_model_bytes_verified"] or models["source_plan"]["receipt_sha256"] != python_manifest["source"]["receipt_sha256"]:
        raise ValueError("kimodo_bundle_source_pair_mismatch")
    planned = [(python_stage, row["path"], row["byte_length"], row["sha256"])
               for row in python_manifest["inventory"]]
    planned.append((python_stage, PYTHON_MANIFEST, len(python_raw), sha256(python_raw).hexdigest()))
    planned.extend((runtime, row["path"], row["byte_length"], row["sha256"])
                   for row in models["payload"])
    notices = additional_notices(runtime)
    planned.extend((runtime, row["path"], row["byte_length"], row["sha256"])
                   for row in notices)
    folded, total = set(), 0
    for _, name, size, _ in planned:
        safe_path(name)
        if name.casefold() in folded:
            raise ValueError("kimodo_bundle_inventory_collision")
        folded.add(name.casefold())
        total += size
        if size > MAX_FILE or total > MAX_TOTAL or len(folded) > MAX_FILES:
            raise ValueError("kimodo_bundle_inventory_limit")
    output.mkdir()
    rows = []
    for index, (root, name, size, expected) in enumerate(planned):
        target = output / name
        target.parent.mkdir(parents=True, exist_ok=True)
        streamed(root / name, output=target, expected=dict(byte_length=size, sha256=expected))
        rows.append(dict(path=name, bytes=size, sha256=expected))
        if index % 2000 == 0 or size > 64 << 20:
            print(json.dumps(dict(step="copy", files_done=index + 1, files_total=len(planned))), flush=True)
    provenance = dict(schema="autospine.kimodo-runtime-provenance/v1",
                      python_component=python_report, model_payload=models["payload"],
                      additional_notices=notices,
                      source_inventory_sha256=python_manifest["source"]["source_inventory_sha256"],
                      model_inventory_sha256=models["payload_inventory_sha256"],
                      source_commit=models["source_plan"]["receipt"]["repository"]["loader_revision"],
                      runtime_ready=False, inference_performed=False,
                      scope="private-local-addon-integrity-only",
                      license_notice="Original source, dependencies, adapters, checkpoint and base-model licenses are retained. This inventory grants no redistribution rights.")
    (output / PROVENANCE).parent.mkdir(parents=True, exist_ok=True)
    raw = canonical(provenance)
    (output / PROVENANCE).write_bytes(raw)
    rows.append(dict(path=PROVENANCE, bytes=len(raw), sha256=sha256(raw).hexdigest()))
    manifest = dict(schema=SCHEMA, component="kimodo-runtime", platform="windows-x64",
                    generation_profile=PROFILE, python_path=".venv/Scripts/python.exe",
                    provenance_path=PROVENANCE, python_manifest_sha256=sha256(python_raw).hexdigest(),
                    files=sorted(rows, key=lambda r: r["path"]))
    raw = canonical(manifest)
    (output / MANIFEST).write_bytes(raw)
    result = dict(schema=SCHEMA, root=str(output), manifest_sha256=sha256(raw).hexdigest(),
                  tree_sha256=tree_digest(rows), files=len(rows), bytes=sum(r["bytes"] for r in rows),
                  python_manifest_sha256=manifest["python_manifest_sha256"], runtime_ready=False,
                  model_bytes_verified=True, inference_performed=False)
    print(json.dumps(dict(step="verify-new-addon")), flush=True)
    checked = verify(output, expected_manifest_sha256=result["manifest_sha256"])
    if checked["tree_sha256"] != result["tree_sha256"]:
        raise ValueError("kimodo_bundle_copied_tree_changed")
    return result


def verify(root, *, expected_manifest_sha256):
    """Verify caller-addressed bytes, not admit an unknown fixed-profile bundle.

    Stage checks the Python/source policy before writing this directory. Studio
    independently pins the entire released tree and nested Python manifest;
    this standalone verifier does not replace either admission check.
    """
    from kimodo_portable_python import safe_path, strict_json

    root = directory(Path(root).absolute())
    if type(expected_manifest_sha256) is not str or not re.fullmatch(r"[a-f0-9]{64}", expected_manifest_sha256):
        raise ValueError("kimodo_bundle_manifest_digest_invalid")
    path = root / MANIFEST
    before = identity(regular(path))
    raw = path.read_bytes()
    if len(raw) > 8 << 20 or sha256(raw).hexdigest() != expected_manifest_sha256:
        raise ValueError("kimodo_bundle_manifest_changed")
    manifest = strict_json(raw)
    if (set(manifest) != {"schema", "component", "platform", "generation_profile", "python_path", "provenance_path", "python_manifest_sha256", "files"}
            or manifest["schema"] != SCHEMA or manifest["component"] != "kimodo-runtime"
            or manifest["platform"] != "windows-x64" or manifest["generation_profile"] != PROFILE
            or manifest["python_path"] != ".venv/Scripts/python.exe" or manifest["provenance_path"] != PROVENANCE):
        raise ValueError("kimodo_bundle_manifest_invalid")
    expected, folded, total = {}, set(), 0
    if type(manifest["files"]) is not list or not 1 <= len(manifest["files"]) <= MAX_FILES:
        raise ValueError("kimodo_bundle_inventory_limit")
    for row in manifest["files"]:
        if set(row) != {"path", "bytes", "sha256"}:
            raise ValueError("kimodo_bundle_record_invalid")
        name = safe_path(row["path"])
        if (name.casefold() in folded or type(row["bytes"]) is not int or not 0 <= row["bytes"] <= MAX_FILE
                or type(row["sha256"]) is not str or not re.fullmatch(r"[a-f0-9]{64}", row["sha256"])):
            raise ValueError("kimodo_bundle_record_invalid")
        folded.add(name.casefold())
        expected[name] = row
        total += row["bytes"]
    if total > MAX_TOTAL:
        raise ValueError("kimodo_bundle_inventory_limit")
    found, snapshots = set(), []
    allowed_dirs = {str(parent) for name in expected for parent in Path(name).parents if str(parent) != "."}
    for current, dirs, names in os.walk(root, followlinks=False):
        current = Path(current)
        directory(current)
        for name in dirs:
            subdir = directory(current / name)
            if str(subdir.relative_to(root)) not in allowed_dirs:
                raise ValueError("kimodo_bundle_extra_directory")
        snapshots.append((current, identity(current.lstat())))
        if current != root and not dirs and not names:
            raise ValueError("kimodo_bundle_extra_empty_directory")
        for name in names:
            file = current / name
            relative = safe_path(file.relative_to(root).as_posix())
            if relative == MANIFEST:
                continue
            row = expected.get(relative)
            if not row or relative in found:
                raise ValueError("kimodo_bundle_undeclared_file")
            before_file = identity(regular(file))
            streamed(file, expected=dict(byte_length=row["bytes"], sha256=row["sha256"]))
            snapshots.append((file, before_file))
            found.add(relative)
    if found != set(expected):
        raise ValueError("kimodo_bundle_missing_file")
    for file, prior in snapshots:
        if identity(file.lstat()) != prior:
            raise ValueError("kimodo_bundle_changed")
    if identity(regular(path)) != before or path.read_bytes() != raw:
        raise ValueError("kimodo_bundle_manifest_changed")
    python_raw = (root / PYTHON_MANIFEST).read_bytes()
    if sha256(python_raw).hexdigest() != manifest["python_manifest_sha256"]:
        raise ValueError("kimodo_bundle_python_pair_changed")
    python_manifest = strict_json(python_raw)
    python_files = python_manifest["inventory"]
    if any(expected.get(r["path"]) != dict(path=r["path"], bytes=r["byte_length"], sha256=r["sha256"]) for r in python_files):
        raise ValueError("kimodo_bundle_python_inventory_changed")
    return dict(schema=SCHEMA, integrity_verified=True, files=len(found), bytes=total,
                manifest_sha256=expected_manifest_sha256, tree_sha256=tree_digest(manifest["files"]),
                scope="caller-addressed-byte-inventory-only", fixed_profile_admitted=False,
                runtime_ready=False, inference_performed=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("stage")
    for name in ("runtime", "python-stage", "output", "git-executable"):
        build.add_argument("--" + name, required=True)
    check = sub.add_parser("verify")
    check.add_argument("--root", required=True)
    check.add_argument("--expected-manifest-sha256", required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    result = (stage(args.runtime, args.python_stage, args.output, git_executable=args.git_executable)
              if args.command == "stage" else verify(args.root, expected_manifest_sha256=args.expected_manifest_sha256))
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
