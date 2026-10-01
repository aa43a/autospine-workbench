"""Explicit Kimodo Python staging and read-only, metadata-free verification.

This is a Python/source/dependency component, not a model bundle or a ready
generation engine. It never modifies the input runtime, installs packages,
downloads weights, executes generation, or borrows Core/pose Python.
"""
from __future__ import annotations

import argparse
import base64
import csv
import hashlib
from importlib.metadata import distributions
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
import zipfile

SCHEMA = "autospine.kimodo-portable-python/v1"
MANIFEST = "kimodo-python-manifest.json"
SCOPE = "python-source-dependencies-only-models-not-included"
LAUNCH_POLICY = {"profile": "isolated-no-bytecode-v1", "required_flags": ["-I", "-B", "-X", "utf8"],
                 "bare_executable_supported": False,
                 "reason": "In CPython 3.12 _pth enables isolation after flag configuration; import site alone does not disable user site before startup."}
PYTHON_VERSION = "3.12.10"
ARCHIVE = "python-3.12.10-embed-amd64.zip"
ARCHIVE_SHA256 = "4acbed6dd1c744b0376e3b1cf57ce906f9dc9e95e68824584c8099a63025a3c3"
SPDX_SHA256 = "efa53ba4f26e8a06410677ec6d010e97133a7a1ab38e0485f6936da2911879fa"
SIGSTORE_SHA256 = "8aa5b4e555fd8b73b3dfef2f04328739f52d30706655930dcdf6111603d015be"
OFFICIAL_URL = "https://www.python.org/ftp/python/3.12.10/" + ARCHIVE
SOURCE_RECEIPT = "kimodo-source-provenance.json"
INJECTIONS = {
    "__editable__.kimodo-1.0.0.pth": "Editable import hook binds the development source directory.",
    "__editable___kimodo_1_0_0_finder.py": "Editable finder contains an absolute development source path.",
    "_virtualenv.pth": "Virtualenv startup hook belongs to the external-base development environment.",
    "_virtualenv.py": "Virtualenv startup helper belongs to the external-base development environment.",
}
PTH = b"python312.zip\n.\nkimodo-policy.zip\n../Lib/site-packages\n../../source\nimport site\n"
# _pth enables isolation before site is loaded. No pyvenv.cfg is shipped, and
# the explicit site-packages path is not a prefix/site directory to process.
# sys.dont_write_bytecode is set before importing any unpacked Python module.
POLICY = b'''import sys
sys.dont_write_bytecode = True
import os
import site
_base = os.path.dirname(os.path.abspath(sys.executable))
_paths = [os.path.join(_base, "python312.zip"), _base,
          os.path.join(_base, "kimodo-policy.zip"),
          os.path.normpath(os.path.join(_base, "../Lib/site-packages")),
          os.path.normpath(os.path.join(_base, "../../source"))]
_norm = lambda p: os.path.normcase(os.path.abspath(p))
if (not sys.flags.isolated or not sys.flags.ignore_environment or
        not sys.flags.no_user_site or site.ENABLE_USER_SITE is not False or
        [_norm(p) for p in sys.path] != [_norm(p) for p in _paths]):
    os.write(2, b"Kimodo private Python path policy failed\\n")
    os._exit(78)
if any(n.startswith("__editable__") or n == "_virtualenv" for n in sys.modules):
    os.write(2, b"Kimodo private Python development hook loaded\\n")
    os._exit(78)
del _norm, _base, _paths
import hashlib
import json
import stat
import zipfile
_scripts = os.path.dirname(os.path.abspath(sys.executable))
_root = os.path.normpath(os.path.join(_scripts, "../.."))
def _guard_fail():
    os.write(2, b"Kimodo frozen source startup guard failed\\n")
    os._exit(79)
def _guard_real(path, directory=False):
    info = os.lstat(path)
    if (getattr(info, "st_file_attributes", 0) & 0x400 or
            not (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode))):
        _guard_fail()
    return info
try:
    with zipfile.ZipFile(os.path.join(_scripts, "kimodo-policy.zip")) as _zip:
        _guard = json.loads(_zip.read("kimodo-source-guard.json"))
    _receipt = os.path.join(_root, "kimodo-source-provenance.json")
    _guard_real(_receipt)
    with open(_receipt, "rb") as _stream:
        _receipt_raw = _stream.read(2 * 1024 * 1024 + 1)
    if hashlib.sha256(_receipt_raw).hexdigest() != _guard["receipt_sha256"]:
        _guard_fail()
    _source = os.path.join(_root, "source")
    _guard_real(_source, True)
    _found = {}
    for _directory, _dirs, _names in os.walk(_source, followlinks=False):
        for _name in _dirs:
            _guard_real(os.path.join(_directory, _name), True)
        for _name in _names:
            _file = os.path.join(_directory, _name)
            _before = _guard_real(_file)
            _relative = os.path.relpath(_file, _source).replace(os.sep, "/")
            _digest, _length = hashlib.sha256(), 0
            with open(_file, "rb") as _stream:
                for _block in iter(lambda: _stream.read(1024 * 1024), b""):
                    _length += len(_block)
                    _digest.update(_block)
                _after = os.fstat(_stream.fileno())
            if (_before.st_dev, _before.st_ino, _before.st_size, _before.st_mtime_ns) != (_after.st_dev, _after.st_ino, _after.st_size, _after.st_mtime_ns):
                _guard_fail()
            _found[_relative] = {"byte_length": _length, "sha256": _digest.hexdigest()}
    if _found != _guard["files"]:
        _guard_fail()
    sys._kimodo_source_guard_verified = True
except Exception:
    _guard_fail()
del _guard, _receipt_raw, _found
'''


def _fail(message):
    raise ValueError("kimodo_portable_python_invalid: " + message)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def strict_json(raw):
    def pairs(rows):
        obj = {}
        for key, value in rows:
            if key in obj:
                _fail("duplicate JSON key")
            obj[key] = value
        return obj
    try:
        return json.loads(raw, object_pairs_hook=pairs)
    except (UnicodeError, json.JSONDecodeError) as exc:
        _fail(str(exc))


def safe_path(value):
    if type(value) is not str or not value or len(value) > 500:
        _fail("invalid path")
    p = PurePosixPath(value)
    if p.is_absolute() or p.as_posix() != value or "\\" in value:
        _fail("non-relative path")
    for part in p.parts:
        stem = part.split(".")[0].upper()
        if (part in (".", "..") or part.endswith((" ", ".")) or
                any(c in part for c in ':<>"|?*') or any(ord(c) < 32 for c in part) or
                stem in {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
                         *(f"LPT{i}" for i in range(1, 10))}):
            _fail("unsafe path")
    return value


def _real(path, *, directory=False):
    try:
        info = path.lstat()
    except OSError as exc:
        _fail(str(exc))
    if (path.is_symlink() or getattr(info, "st_file_attributes", 0) & 0x400 or
            not (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode))):
        _fail("alias or wrong file type: " + str(path))
    return info


def _root(path):
    path = Path(os.path.abspath(os.fspath(path)))
    for p in reversed((path, *path.parents)):
        _real(p, directory=True)
    return path


def hash_file(path):
    _real(path)
    h, length = hashlib.sha256(), 0
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4 << 20), b""):
            h.update(block)
            length += len(block)
    return {"byte_length": length, "sha256": h.hexdigest()}


def _walk(root):
    root = _root(root)
    result, folded = [], set()
    for directory, dirs, names in os.walk(root, followlinks=False):
        for name in dirs:
            _real(Path(directory) / name, directory=True)
        for name in names:
            path = Path(directory) / name
            _real(path)
            relative = safe_path(path.relative_to(root).as_posix())
            if relative.casefold() in folded:
                _fail("case-colliding path")
            folded.add(relative.casefold())
            result.append((relative, path))
    return sorted(result)


def _generated_cache(relative, root):
    """Only tagged caches with an existing source are disposable, not pyc-only code."""
    path = PurePosixPath(relative)
    if path.parent.name != "__pycache__":
        return False
    match = re.fullmatch(r"(.+)\.cpython-312(?:\.opt-[12])?\.pyc", path.name)
    if match is None:
        return False
    source = root / path.parent.parent / (match[1] + ".py")
    if not source.is_file():
        return False
    _real(source)
    return True


def policy_zip(receipt):
    guard = {"schema": "autospine.kimodo-source-startup-guard/v1",
             "receipt_sha256": hashlib.sha256(canonical(receipt)).hexdigest(),
             "files": {safe_path(r["path"]): {k: r[k] for k in ("byte_length", "sha256")}
                       for r in receipt["files"]}}
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_STORED) as archive:
        member = zipfile.ZipInfo("sitecustomize.py", (2025, 4, 8, 0, 0, 0))
        member.external_attr = 0o100644 << 16
        archive.writestr(member, POLICY)
        member = zipfile.ZipInfo("kimodo-source-guard.json", (2025, 4, 8, 0, 0, 0))
        member.external_attr = 0o100644 << 16
        archive.writestr(member, canonical(guard))
    return stream.getvalue()


def inspect_official_archive(downloads):
    """Bind the actual archive bytes to the SHA256 published in official SPDX."""
    downloads = _root(downloads)
    archive = downloads / ARCHIVE
    if hash_file(archive)["sha256"] != ARCHIVE_SHA256:
        _fail("official archive SHA256 mismatch")
    spdx = downloads / (ARCHIVE + ".spdx.json")
    signature = downloads / (ARCHIVE + ".sigstore")
    _real(spdx); _real(signature)
    if hash_file(spdx)["sha256"] != SPDX_SHA256 or hash_file(signature)["sha256"] != SIGSTORE_SHA256:
        _fail("official provenance evidence changed")
    document = strict_json(spdx.read_bytes())
    matches = [p for p in document.get("packages", []) if p.get("packageFileName") == ARCHIVE]
    if len(matches) != 1 or matches[0].get("downloadLocation") != OFFICIAL_URL:
        _fail("official SPDX archive binding missing")
    if {"algorithm": "SHA256", "checksumValue": ARCHIVE_SHA256} not in matches[0].get("checksums", []):
        _fail("official SPDX digest mismatch")
    bundle = strict_json(signature.read_bytes())
    if bundle.get("mediaType") != "application/vnd.dev.sigstore.bundle.v0.3+json":
        _fail("unexpected signature bundle")
    try:
        message = bundle["messageSignature"]["messageDigest"]
        if message["algorithm"] != "SHA2_256" or base64.b64decode(message["digest"], validate=True).hex() != ARCHIVE_SHA256:
            _fail("signature digest mismatch")
        base64.b64decode(bundle["verificationMaterial"]["certificate"]["rawBytes"], validate=True)
        base64.b64decode(bundle["messageSignature"]["signature"], validate=True)
    except (KeyError, TypeError, ValueError) as exc:
        _fail("invalid signature binding: " + str(exc))
    members = {}
    with zipfile.ZipFile(archive) as reader:
        for info in reader.infolist():
            name = safe_path(info.filename)
            if "/" in name or info.is_dir() or name.casefold() in {n.casefold() for n in members}:
                _fail("unexpected embedded archive path")
            if stat.S_ISLNK(info.external_attr >> 16) or info.file_size > (64 << 20):
                _fail("unexpected embedded archive member")
            raw = reader.read(info)
            members[name] = {"byte_length": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
    for name in ("python.exe", "python312.dll", "python3.dll", "python312.zip", "python312._pth", "LICENSE.txt"):
        if name not in members:
            _fail("embedded archive incomplete")
    return {"version": PYTHON_VERSION, "url": OFFICIAL_URL, "archive": hash_file(archive),
            "spdx": hash_file(spdx), "sigstore": hash_file(signature), "members": members,
            "signature_status": "bundle-present-digest-bound-trust-chain-not-verified"}


def dependency_plan(runtime):
    """Inventory every installed file; only four named development hooks are removed.

    RECORD checks establish equality to the existing installation, not a PyPI
    publisher signature. Console launchers are declared individually and excluded
    because this component invokes the fixed interpreter with -m / script paths.
    """
    runtime = _root(runtime)
    packages = runtime / ".venv/Lib/site-packages"
    files, omitted, cached, by_path = [], [], [], {}
    for relative, path in _walk(packages):
        if _generated_cache(relative, packages):
            cached.append(relative)
            continue
        row = {"path": relative, **hash_file(path)}
        by_path[relative] = row
        if relative in INJECTIONS:
            omitted.append({**row, "reason": INJECTIONS[relative]})
        else:
            files.append(row)
    outside, package_rows, owners, retained_data = [], [], {}, {}
    for dist in sorted(distributions(path=[str(packages)]), key=lambda d: d.metadata["Name"].lower()):
        metadata_path = Path(dist._path)
        relative_metadata = safe_path(metadata_path.relative_to(packages).as_posix())
        _real(metadata_path, directory=True)
        record = metadata_path / "RECORD"
        _real(record)
        licenses = [p for p in by_path if p.startswith(relative_metadata + "/") and
                    any(w in p.rsplit("/", 1)[-1].lower() for w in ("license", "copying", "notice", "attribution"))]
        package_rows.append({"name": dist.metadata["Name"], "version": dist.version,
                             "metadata_directory": relative_metadata,
                             "metadata": hash_file(metadata_path / "METADATA"),
                             "record": hash_file(record), "requires_dist": dist.requires or [],
                             "license_files": licenses,
                             "license_expression": dist.metadata.get("License-Expression"),
                             "license_metadata": dist.metadata.get("License"),
                             "direct_url": strict_json((metadata_path / "direct_url.json").read_bytes())
                             if (metadata_path / "direct_url.json").is_file() else None})
        for rel, digest, size in csv.reader(record.read_text(encoding="utf-8").splitlines()):
            target = packages / rel
            resolved = Path(os.path.abspath(target))
            if resolved.is_relative_to(packages):
                relative = safe_path(resolved.relative_to(packages).as_posix())
                if _generated_cache(relative, packages):
                    continue
                if relative not in by_path:
                    _fail("RECORD file missing: " + rel)
                row = by_path[relative]
                owners.setdefault(relative, []).append(dist.metadata["Name"])
            elif resolved.parent == runtime / ".venv/Scripts":
                safe_path(resolved.name)
                row = hash_file(resolved)
                outside.append({"distribution": dist.metadata["Name"], "path": ".venv/Scripts/" + resolved.name,
                                **row, "reason": "Development console entrypoint; worker uses private python.exe directly."})
            elif resolved.is_relative_to(runtime / ".venv/share"):
                relative = safe_path(resolved.relative_to(runtime).as_posix())
                row = hash_file(resolved)
                retained_data[relative] = {"path": relative, **row, "distribution": dist.metadata["Name"]}
            else:
                _fail("RECORD escapes fixed runtime boundary: " + rel)
            if size and (not size.isdecimal() or int(size) != row["byte_length"]):
                _fail("RECORD size mismatch: " + rel)
            if digest:
                algorithm, encoded = digest.split("=", 1)
                if algorithm != "sha256" or base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)).hex() != row["sha256"]:
                    _fail("RECORD digest mismatch: " + rel)
    for row in files:
        row["distributions"] = sorted(set(owners.get(row["path"], [])))
    return {"files": files, "distributions": package_rows, "removed_development_hooks": omitted,
            "removed_console_entrypoints": sorted(outside, key=lambda r: (r["path"], r["distribution"])),
            "retained_non_site_data": sorted(retained_data.values(), key=lambda r: r["path"]),
            "omitted_bytecode": cached,
            "record_assurance": "Existing installed RECORD hashes checked; publisher signatures not claimed."}


def _write(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(raw)


def _copy_verified(source, target, expected):
    _real(source)
    target.parent.mkdir(parents=True, exist_ok=True)
    h, length = hashlib.sha256(), 0
    with source.open("rb") as src, target.open("xb") as dst:
        for block in iter(lambda: src.read(4 << 20), b""):
            dst.write(block); h.update(block); length += len(block)
    if {"byte_length": length, "sha256": h.hexdigest()} != expected:
        _fail("input changed while copying: " + str(source))


def stage_python(runtime, downloads, output, *, git_executable, baseline_python_version):
    """Create a fresh private staging directory. No overwrite, install or inference."""
    from autospine_workbench.automation.motion_generation_frozen_source import build_frozen_source_plan, verify_frozen_source
    runtime, downloads = _root(runtime), _root(downloads)
    output = Path(os.path.abspath(os.fspath(output)))
    _root(output.parent)
    if output.exists() or output.is_symlink() or output.is_relative_to(runtime) or runtime.is_relative_to(output):
        _fail("staging output must be fresh and separate from original runtime")
    official = inspect_official_archive(downloads)
    dependencies = dependency_plan(runtime)
    source = build_frozen_source_plan(runtime, git_executable=git_executable)
    output.mkdir()
    scripts = output / ".venv/Scripts"
    for name, expected in official["members"].items():
        with zipfile.ZipFile(downloads / ARCHIVE) as archive:
            raw = archive.read(name)
        _write(scripts / name, PTH if name == "python312._pth" else raw)
    _write(scripts / "kimodo-policy.zip", policy_zip(source["receipt"]))
    for row in dependencies["files"]:
        _copy_verified(runtime / ".venv/Lib/site-packages" / row["path"],
                       output / ".venv/Lib/site-packages" / row["path"],
                       {k: row[k] for k in ("byte_length", "sha256")})
    for row in dependencies["retained_non_site_data"]:
        _copy_verified(runtime / row["path"], output / row["path"],
                       {k: row[k] for k in ("byte_length", "sha256")})
    for row in source["receipt"]["files"]:
        _copy_verified(runtime / "source" / row["path"], output / "source" / row["path"],
                       {k: row[k] for k in ("byte_length", "sha256")})
    _write(output / SOURCE_RECEIPT, canonical(source["receipt"]))
    for name in (ARCHIVE, ARCHIVE + ".spdx.json", ARCHIVE + ".sigstore"):
        _copy_verified(downloads / name, output / "provenance/python" / name, hash_file(downloads / name))
    source_verified = verify_frozen_source(output)
    rows = [{"path": p, **hash_file(f)} for p, f in _walk(output)]
    manifest = {"schema": SCHEMA, "scope": SCOPE, "python": official, "launch_policy": LAUNCH_POLICY,
                "baseline_python_version": baseline_python_version,
                "dependencies": dependencies,
                "source": {"receipt_sha256": source_verified["receipt_sha256"],
                           "source_inventory_sha256": source_verified["source_inventory_sha256"]},
                "inventory": rows, "runtime_ready": False,
                "not_validated": ["models-not-bundled", "model-load-not-tested", "generation-not-performed",
                                  "target-machine-driver-and-cuda-probe-required", "python-patch-change-requires-probes"]}
    _write(output / MANIFEST, canonical(manifest))
    return {"root": str(output), "manifest_sha256": hash_file(output / MANIFEST)["sha256"],
            "file_count": len(rows), "byte_length": sum(r["byte_length"] for r in rows), "runtime_ready": False}


def verify_python_stage(root, *, expected_manifest_sha256=None):
    """Every retained byte is rehashed; Git, source metadata and PATH are unused."""
    from autospine_workbench.automation.motion_generation_frozen_source import verify_frozen_source
    root = _root(root)
    manifest_path = root / MANIFEST
    actual_manifest = hash_file(manifest_path)
    if expected_manifest_sha256 is not None and actual_manifest["sha256"] != expected_manifest_sha256:
        _fail("manifest receipt mismatch")
    if actual_manifest["byte_length"] > (32 << 20):
        _fail("manifest too large")
    manifest = strict_json(manifest_path.read_bytes())
    expected_keys = {"schema", "scope", "python", "launch_policy", "baseline_python_version", "dependencies", "source",
                     "inventory", "runtime_ready", "not_validated"}
    if type(manifest) is not dict or set(manifest) != expected_keys or manifest["schema"] != SCHEMA or manifest["scope"] != SCOPE:
        _fail("schema mismatch")
    if manifest["runtime_ready"] is not False:
        _fail("partial component cannot claim ready")
    if manifest["launch_policy"] != LAUNCH_POLICY:
        _fail("isolated interpreter launch policy mismatch")
    expected, folded = {}, set()
    for row in manifest["inventory"]:
        if type(row) is not dict or set(row) != {"path", "byte_length", "sha256"}:
            _fail("inventory schema mismatch")
        p = safe_path(row["path"])
        if p.casefold() in folded or type(row["byte_length"]) is not int or row["byte_length"] < 0:
            _fail("duplicate path or invalid byte length")
        folded.add(p.casefold())
        if type(row["sha256"]) is not str or re.fullmatch("[0-9a-f]{64}", row["sha256"]) is None:
            _fail("invalid digest")
        expected[p] = {k: row[k] for k in ("byte_length", "sha256")}
    actual = {p: hash_file(f) for p, f in _walk(root) if p != MANIFEST}
    if actual != expected:
        _fail("installed file inventory mismatch")
    expected_directories = {p.as_posix() for name in expected for p in PurePosixPath(name).parents if p.as_posix() != "."}
    for current, dirs, _ in os.walk(root, followlinks=False):
        for name in dirs:
            if (Path(current) / name).relative_to(root).as_posix() not in expected_directories:
                _fail("undeclared installed directory")
    official = inspect_official_archive(root / "provenance/python")
    if manifest["python"] != official:
        _fail("official archive receipt mismatch")
    for name, record in official["members"].items():
        path = root / ".venv/Scripts" / name
        if name == "python312._pth":
            if path.read_bytes() != PTH:
                _fail("private search path policy changed")
        elif hash_file(path) != record:
            _fail("embedded Python bytes changed")
    source = verify_frozen_source(root)
    if (root / ".venv/Scripts/kimodo-policy.zip").read_bytes() != policy_zip(strict_json((root / SOURCE_RECEIPT).read_bytes())):
        _fail("startup policy changed")
    if (root / ".venv/pyvenv.cfg").exists():
        _fail("external-base virtualenv configuration shipped")
    sp = root / ".venv/Lib/site-packages"
    for path in INJECTIONS:
        if (sp / path).exists():
            _fail("development hook shipped")
    dependency_keys = {"files", "distributions", "removed_development_hooks", "removed_console_entrypoints",
                       "retained_non_site_data", "omitted_bytecode", "record_assurance"}
    if type(manifest["dependencies"]) is not dict or set(manifest["dependencies"]) != dependency_keys:
        _fail("dependency plan schema mismatch")
    dependency_records = manifest["dependencies"]["files"]
    if {".venv/Lib/site-packages/" + r["path"]: {k: r[k] for k in ("byte_length", "sha256")}
            for r in dependency_records} != {p: r for p, r in actual.items() if p.startswith(".venv/Lib/site-packages/")}:
        _fail("dependency inventory receipt mismatch")
    for row in manifest["dependencies"]["retained_non_site_data"]:
        if not safe_path(row["path"]).startswith(".venv/share/") or actual.get(row["path"]) != {k: row[k] for k in ("byte_length", "sha256")}:
            _fail("retained dependency data receipt mismatch")
    if manifest["source"] != {"receipt_sha256": source["receipt_sha256"], "source_inventory_sha256": source["source_inventory_sha256"]}:
        _fail("source receipt mismatch")
    return {"schema": SCHEMA, "integrity_verified": True, "runtime_ready": False,
            "manifest_sha256": actual_manifest["sha256"], "file_count": len(actual),
            "byte_length": sum(r["byte_length"] for r in actual.values()),
            "not_validated": manifest["not_validated"], "python_version": PYTHON_VERSION,
            "baseline_python_version": manifest["baseline_python_version"],
            "signature_status": official["signature_status"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("stage")
    for name in ("runtime", "downloads", "output", "git-executable", "baseline-python-version"):
        build.add_argument("--" + name, required=True)
    verify = sub.add_parser("verify")
    verify.add_argument("--root", required=True)
    verify.add_argument("--expected-manifest-sha256")
    args = parser.parse_args()
    if args.command == "stage":
        result = stage_python(args.runtime, args.downloads, args.output,
                              git_executable=args.git_executable, baseline_python_version=args.baseline_python_version)
    else:
        result = verify_python_stage(args.root, expected_manifest_sha256=args.expected_manifest_sha256)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
