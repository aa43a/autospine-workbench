"""Assemble a separate, offline Windows core runtime from verified artifacts.

No global interpreter, site-packages, models, projects or installation state is
copied. This tool does not download dependencies or run package installers.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import importlib.util
import json
import re
import shutil
import stat
import zipfile
from pathlib import Path, PurePosixPath

PYTHON_VERSION = "3.14.3"
PYTHON_SHA256 = "e69d3609130b1c06948620651d0f0ab2183ff978c2b174ddf3d3cae7ff226b89"
PYTHON_URL = "https://www.python.org/ftp/python/3.14.3/python-3.14.3-embeddable-amd64.zip"
PYTHON_MANIFEST_URL = "https://www.python.org/ftp/python/3.14.3/windows-3.14.3.json"
PTH = b"python314.zip\nsitecustomize.zip\n.\nLib/site-packages\n../../engine/src\nimport site\n"
SITE_CUSTOMIZE = b"import sys\nsys.dont_write_bytecode = True\n"


def site_customize_archive() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_STORED) as archive:
        entry = zipfile.ZipInfo("sitecustomize.py", date_time=(1980, 1, 1, 0, 0, 0))
        entry.create_system = 0
        entry.external_attr = 0x20
        archive.writestr(entry, SITE_CUSTOMIZE)
    return buffer.getvalue()
VERSIONS = {
    "numpy": "2.4.6", "scipy": "1.18.0", "pillow": "12.3.0",
    "psd-tools": "1.18.0", "jsonschema": "4.26.0", "attrs": "26.1.0",
    "jsonschema-specifications": "2025.9.1", "referencing": "0.37.0",
    "rpds-py": "2026.6.3", "typing-extensions": "4.16.0",
}
PYTHON_FILES = frozenset("""python.exe pythonw.exe python314.dll python3.dll
vcruntime140.dll vcruntime140_1.dll LICENSE.txt pyexpat.pyd select.pyd
unicodedata.pyd winsound.pyd _asyncio.pyd _bz2.pyd _ctypes.pyd _decimal.pyd
_elementtree.pyd _hashlib.pyd _lzma.pyd _multiprocessing.pyd _overlapped.pyd
_queue.pyd _remote_debugging.pyd _socket.pyd _sqlite3.pyd _ssl.pyd _uuid.pyd
_wmi.pyd _zoneinfo.pyd _zstd.pyd libcrypto-3.dll libffi-8.dll libssl-3.dll
sqlite3.dll python314.zip python314._pth python.cat __install__.json""".split())
PACKAGE_ROOTS = frozenset("""attr attrs attrs-26.1.0.dist-info jsonschema
jsonschema-4.26.0.dist-info jsonschema_specifications
jsonschema_specifications-2025.9.1.dist-info numpy numpy-2.4.6.dist-info
numpy.libs PIL pillow-12.3.0.dist-info psd_tools psd_tools-1.18.0.dist-info
psd_tools.libs referencing referencing-0.37.0.dist-info rpds
rpds_py-2026.6.3.dist-info scipy scipy-1.18.0.dist-info scipy.libs
typing_extensions-4.16.0.dist-info typing_extensions.py""".split())


def sha256(file: Path) -> str:
    with file.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def safe_relative(value: str) -> str:
    parts = PurePosixPath(value).parts
    if (not value or "\\" in value or ":" in value or value.startswith("/")
            or any(part in {".", ".."} or not re.fullmatch(r"[A-Za-z0-9_.-]+", part)
                   or part.endswith(".") or re.match(r"(?i)^(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\.|$)", part)
                   for part in parts) or "/".join(parts) != value):
        raise ValueError("unsafe artifact path")
    return value


def verified_file(file: Path, expected: str) -> None:
    info = file.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or sha256(file) != expected:
        raise ValueError(f"artifact verification failed: {file.name}")


def wheel_lock(file: Path) -> list[dict]:
    value = json.loads(file.read_text(encoding="utf-8"))
    if value.get("schema") != "autospine.core-runtime-wheel-lock/v1" or len(value.get("wheels", [])) != len(VERSIONS):
        raise ValueError("unsupported wheel lock")
    seen = set()
    for item in value["wheels"]:
        if set(item) != {"package", "version", "filename", "sha256", "url", "metadata_url"}:
            raise ValueError("unsupported wheel declaration")
        name = item["package"]
        if name in seen or VERSIONS.get(name) != item["version"]:
            raise ValueError("wheel versions differ from fixed runtime")
        seen.add(name)
        filename = safe_relative(item["filename"])
        if "/" in filename or not filename.endswith(("-cp314-cp314-win_amd64.whl", "-py3-none-any.whl")):
            raise ValueError("wheel platform mismatch")
        if not re.fullmatch(r"[a-f0-9]{64}", item["sha256"]):
            raise ValueError("missing wheel hash")
        if (item["metadata_url"] != f"https://pypi.org/pypi/{name}/{item['version']}/json"
                or not item["url"].startswith("https://files.pythonhosted.org/packages/")
                or not item["url"].endswith("/" + filename)):
            raise ValueError("wheel origin mismatch")
    return value["wheels"]


def extract(zip_path: Path, target: Path, *, python: bool = False) -> None:
    with zipfile.ZipFile(zip_path) as archive:
        names = set()
        total = 0
        for info in archive.infolist():
            if info.is_dir():
                continue
            if not python and "tests" in PurePosixPath(info.filename).parts:
                continue
            name = safe_relative(info.filename)
            # One upstream SciPy wheel includes a copy of its archive. It is
            # not a runtime module and is excluded, not recursively extracted.
            if not python and name.endswith(".whl"):
                continue
            key = name.lower()
            if key in names or stat.S_ISLNK(info.external_attr >> 16):
                raise ValueError("archive alias or link")
            names.add(key)
            if python:
                if name not in PYTHON_FILES:
                    raise ValueError("unexpected Python release file")
            elif name.split("/")[0] not in PACKAGE_ROOTS or "__pycache__" in name.split("/"):
                raise ValueError("unexpected wheel package root")
            total += info.file_size
            if info.file_size > 64 * 1024 * 1024 or total > 512 * 1024 * 1024:
                raise ValueError("archive expansion exceeds fixed budget")
            file = target / name
            file.parent.mkdir(parents=True, exist_ok=True)
            with file.open("xb") as stream:
                stream.write(archive.read(info))
        if python and names != {name.lower() for name in PYTHON_FILES}:
            raise ValueError("Python archive is incomplete")


def prepare(source: Path, python_zip: Path, wheelhouse: Path, lock_file: Path, output: Path) -> dict:
    if output.exists():
        raise ValueError("destination already exists; preserve earlier artifacts")
    source = source.resolve(strict=True)
    specification = importlib.util.spec_from_file_location("_studio_source_distribution", Path(__file__).with_name("engine_distribution.py"))
    distribution = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(distribution)
    distribution.verify_directory(source)
    manifest_path = source / "engine-distribution.json"
    original = json.loads(manifest_path.read_text(encoding="utf-8"))
    if original.get("schema") != "autospine.engine-distribution/v1" or original.get("scope") != "engine-source-only":
        raise ValueError("requires verified engine source distribution")
    declared = {item["path"]: item for item in original["files"]}
    actual = {file.relative_to(source).as_posix() for file in source.rglob("*") if file.is_file()}
    if actual != set(declared) | {"engine-distribution.json"}:
        raise ValueError("source distribution inventory differs")
    for name, item in declared.items():
        safe_relative(name)
        if not name.startswith("engine/") or name.count("/") < 1:
            raise ValueError("unexpected engine root")
        file = source / name
        if not file.resolve(strict=True).is_relative_to(source) or file.stat().st_size != item["bytes"]:
            raise ValueError("source distribution path/size differs")
        verified_file(file, item["sha256"])
    verified_file(python_zip, PYTHON_SHA256)
    wheels = wheel_lock(lock_file)
    for item in wheels:
        verified_file(wheelhouse / item["filename"], item["sha256"])
    output.mkdir(parents=True)
    for name in sorted(declared):
        target = output / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / name, target)
    python_root = output / "runtime/python"
    extract(python_zip, python_root, python=True)
    for item in wheels:
        extract(wheelhouse / item["filename"], python_root / "Lib/site-packages")
    (python_root / "python314._pth").write_bytes(PTH)
    (python_root / "sitecustomize.zip").write_bytes(site_customize_archive())
    provenance = {
        "schema": "autospine.core-runtime-provenance/v1",
        "python": {"version": PYTHON_VERSION, "url": PYTHON_URL, "sha256": PYTHON_SHA256,
                   "hash_source": PYTHON_MANIFEST_URL},
        "wheels": wheels,
        "engine_manifest_sha256": sha256(manifest_path),
        "licenses": "Python LICENSE.txt and wheel dist-info licenses are preserved; upstream tests and nested wheel archives are excluded.",
        "limits": "No Pose model, Node/browser, Blender or Kimodo checkpoints included.",
    }
    (output / "runtime/PROVENANCE.json").write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")
    manifest = dict(original, component="engine-core-runtime", scope="engine-core-runtime",
                    python_root="runtime/python", python_version=PYTHON_VERSION)
    manifest["runtime_dependencies"] = [dict(item, bundled=item["id"] in {"python", "psd-decoder", "analysis", "cloth-solver"})
                                        for item in original["runtime_dependencies"]]
    manifest["limitations"] = ["Core Python, PSD decoder, NumPy and SciPy are bundled; actual runtime probes remain required.",
                               "Pose, official Runtime/browser capture, FBX and Kimodo are not included.",
                               "This is not a complete clean-machine S1-S6 installation or a signed artifact."]
    (output / "engine/DEPENDENCIES.json").write_text(json.dumps({
        "scope": manifest["scope"], "runtime_dependencies": manifest["runtime_dependencies"],
        "limitations": manifest["limitations"],
    }, indent=2) + "\n", encoding="utf-8")
    (output / "engine/DEPLOYMENT.md").write_text(
        "# AutoSpine independent core runtime\n\n"
        f"Source commit: `{manifest['source_commit']}`. Scope: **engine-core-runtime**.\n\n"
        "This separate artifact includes Python 3.14.3, fixed PSD decoder, NumPy, SciPy and schema dependencies. "
        "Python is isolated and references this artifact's engine/src using a fixed relative ._pth file. "
        "Global Python, site-packages, user state and trained models are not copied.\n\n"
        "In Studio 0.3.5+, open Runtime Environment, select this trusted artifact's root, "
        "and install/validate/save. Existing project/state directories stay pinned; only absent initial paths "
        "can become new private directories. The resulting profile takes effect on the next Studio launch. "
        "Studio automatically chooses and manages its own loopback port; do not start a service manually.\n\n"
        "Pose models, Node/official Spine capture dependencies, compatible Chromium, Blender and Kimodo "
        "are excluded. Their capabilities remain missing or separately configured until actually tested. "
        "This artifact is not a complete clean-machine S1-S6 installer.\n\n"
        "runtime/PROVENANCE.json records official Python/PyPI URLs and artifact hashes. Python LICENSE.txt "
        "and wheel dist-info licenses are preserved. Upstream tests and nested wheel archives are excluded. "
        "The artifact manifest is an integrity inventory, not a publisher signature; select only a trusted local artifact. "
        "Repository source licensing is not declared; no public redistribution right is granted.\n",
        encoding="utf-8",
    )
    manifest["files"] = [dict(path=file.relative_to(output).as_posix(), bytes=file.stat().st_size, sha256=sha256(file))
                         for file in sorted(output.rglob("*")) if file.is_file()]
    (output / "engine-distribution.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return {"scope": manifest["scope"], "files": len(manifest["files"]), "bytes": sum(item["bytes"] for item in manifest["files"]),
            "manifest_sha256": sha256(output / "engine-distribution.json")}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for argument in ("engine-source", "python-zip", "wheelhouse", "wheel-lock", "output"):
        parser.add_argument("--" + argument, required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(prepare(args.engine_source, args.python_zip, args.wheelhouse, args.wheel_lock, args.output)))
