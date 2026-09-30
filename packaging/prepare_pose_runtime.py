"""Build an independent offline Pose addon from fixed official artifacts.

No venv, global site-packages, user project or absolute engine path is copied.
The installed engine owns the fixed bootstrap which starts this interpreter.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import stat
import zipfile
from pathlib import Path, PurePosixPath

from prepare_core_runtime import (PYTHON_VERSION, PYTHON_SHA256, PYTHON_URL,
    PYTHON_MANIFEST_URL, PYTHON_FILES, safe_relative, verified_file, sha256,
    extract, site_customize_archive)

MODEL_SHA256 = "724f4ff2439ed61afb86fb8a1951ec39c6220682803b4a8bd4f598cd913b1843"
MODEL_BYTES = 134399116
MODEL_PATH = "models/dw-ll_ucoco_384.onnx"
MODEL_REVISION = "1a7144101628d69ee7a3768d1ee3a094070dc388"
MODEL_URL = f"https://huggingface.co/yzd-v/DWPose/resolve/{MODEL_REVISION}/dw-ll_ucoco_384.onnx"
MODEL_CARD_URL = f"https://huggingface.co/yzd-v/DWPose/raw/{MODEL_REVISION}/README.md"
MODEL_CARD_SHA256 = "98b45ea81164d1e1a1dd82255207053b15cd6c69d922a1c5cf3387ce604d4b74"
LICENSE_URL = "https://raw.githubusercontent.com/IDEA-Research/DWPose/3dca5db79d9f9ffdd378753ddf6ec66535aace88/LICENSE"
LICENSE_SHA256 = "ec5aa54eef312195c4494873a37158b19b0d523e25cec570189e6aa86289cf42"
PTH = b"python314.zip\nsitecustomize.zip\n.\nLib/site-packages\nimport site\n"
MANIFEST = "pose-distribution.json"
PACKAGE_ROOTS = frozenset("""numpy numpy.libs numpy-2.4.6.dist-info PIL pillow-12.3.0.dist-info
cv2 opencv_python_headless-4.13.0.92.dist-info onnxruntime onnxruntime-1.27.0.dist-info
flatbuffers flatbuffers-25.12.19.dist-info packaging packaging-26.3.dist-info
google protobuf-7.36.1.dist-info""".split())
FIXED_WHEELS = {
    "numpy": ("2.4.6", "numpy-2.4.6-cp314-cp314-win_amd64.whl", "b507f5c4c1d508876d1819b6bf9a49d365b96320b5d4993426b33a23ca4b8261"),
    "pillow": ("12.3.0", "pillow-12.3.0-cp314-cp314-win_amd64.whl", "fdafc9cce40277e0f7a0feabce0ee50dd2fa1800f3b38015e51296b5e814048d"),
    "onnxruntime": ("1.27.0", "onnxruntime-1.27.0-cp314-cp314-win_amd64.whl", "49e416be0d717338b6d041b99911b716d70c397d277056450724f93bdded3fc2"),
    "opencv-python-headless": ("4.13.0.92", "opencv_python_headless-4.13.0.92-cp37-abi3-win_amd64.whl", "77a82fe35ddcec0f62c15f2ba8a12ecc2ed4207c17b0902c7a3151ae29f37fb6"),
    "flatbuffers": ("25.12.19", "flatbuffers-25.12.19-py2.py3-none-any.whl", "7634f50c427838bb021c2d66a3d1168e9d199b0607e6329399f04846d42e20b4"),
    "packaging": ("26.3", "packaging-26.3-py3-none-any.whl", "d7193f7c8e4e93f444fde0262bf90af30e16fa0ad0ad44cb553c87339b23cd1c"),
    "protobuf": ("7.36.1", "protobuf-7.36.1-cp310-abi3-win_amd64.whl", "51139351435d9b43d88a55eaa49fb6f737fbb478fb0cbf2cf694d1a04a9d3363"),
}


def wheel_lock(file: Path) -> list[dict]:
    value = json.loads(file.read_text(encoding="utf-8"))
    if set(value) != {"schema", "wheels"} or value["schema"] != "autospine.pose-runtime-wheel-lock/v1" \
            or len(value["wheels"]) != len(FIXED_WHEELS):
        raise ValueError("unsupported Pose wheel lock")
    seen = set()
    for item in value["wheels"]:
        if set(item) != {"package", "version", "filename", "sha256", "url", "metadata_url"}:
            raise ValueError("unexpected Pose wheel fields")
        package = item["package"]
        if package in seen or FIXED_WHEELS.get(package) != (item["version"], item["filename"], item["sha256"]):
            raise ValueError("Pose wheel identity mismatch")
        seen.add(package)
        if item["metadata_url"] != f"https://pypi.org/pypi/{package}/{item['version']}/json" \
                or not item["url"].startswith("https://files.pythonhosted.org/packages/") \
                or not item["url"].endswith("/" + safe_relative(item["filename"])):
            raise ValueError("Pose wheel origin mismatch")
    return value["wheels"]


def extract_wheel(file: Path, target: Path):
    with zipfile.ZipFile(file) as archive:
        seen, total = set(), 0
        for record in archive.infolist():
            if record.is_dir() or "tests" in PurePosixPath(record.filename).parts:
                continue
            name = safe_relative(record.filename)
            if name.split("/")[0] not in PACKAGE_ROOTS or "__pycache__" in name.split("/") \
                    or stat.S_ISLNK(record.external_attr >> 16) or name.lower() in seen:
                raise ValueError("unexpected Pose wheel path or alias")
            if name.endswith((".whl", ".pyc", ".exe", ".psd", ".fbx", ".pth", ".safetensors", ".ckpt", ".pkl")):
                raise ValueError("unexpected Pose wheel payload")
            seen.add(name.lower())
            total += record.file_size
            fixed_large = name == 'cv2/cv2.pyd' and record.file_size == 74492416
            if (record.file_size > 64 << 20 and not fixed_large) or total > 512 << 20:
                raise ValueError("Pose wheel expansion exceeds budget")
            output = target / name
            output.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(record) as source, output.open("xb") as destination:
                shutil.copyfileobj(source, destination, 1 << 20)
            if output.stat().st_size != record.file_size:
                raise ValueError("Pose wheel expansion size changed")
            if fixed_large and sha256(output) != '90034927004e4a4ebf29360480d609c8a8d2ca07c93f8b89dff86399e8534b2a':
                raise ValueError("fixed large OpenCV library digest differs")


def inventory(root: Path):
    records = []
    for file in sorted(root.rglob("*")):
        info = file.lstat()
        if stat.S_ISLNK(info.st_mode) or (not file.is_dir() and (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1)):
            raise ValueError("Pose artifact contains links")
        if file.is_file() and file.name != MANIFEST:
            records.append(dict(path=file.relative_to(root).as_posix(), bytes=info.st_size, sha256=sha256(file)))
    if len(records) > 32768 or sum(row["bytes"] for row in records) > 512 << 20:
        raise ValueError("Pose artifact exceeds inventory budget")
    return records


def prepare(python_zip: Path, wheelhouse: Path, lock_file: Path, model: Path,
            model_card: Path, license_file: Path, output: Path):
    if output.exists() or output.is_symlink():
        raise ValueError("destination already exists; preserve earlier artifacts")
    verified_file(python_zip, PYTHON_SHA256)
    verified_file(model, MODEL_SHA256)
    if model.stat().st_size != MODEL_BYTES:
        raise ValueError("fixed model size mismatch")
    verified_file(model_card, MODEL_CARD_SHA256)
    verified_file(license_file, LICENSE_SHA256)
    wheels = wheel_lock(lock_file)
    for row in wheels:
        verified_file(wheelhouse / row["filename"], row["sha256"])
    output.mkdir(parents=True, exist_ok=False)
    python_root = output / "python"
    extract(python_zip, python_root, python=True)
    for row in wheels:
        extract_wheel(wheelhouse / row["filename"], python_root / "Lib/site-packages")
    (python_root / "python314._pth").write_bytes(PTH)
    (python_root / "sitecustomize.zip").write_bytes(site_customize_archive())
    (output / "models").mkdir()
    shutil.copyfile(model, output / MODEL_PATH)
    (output / "LICENSES").mkdir()
    shutil.copyfile(model_card, output / "LICENSES/DWPose-model-card.md")
    shutil.copyfile(license_file, output / "LICENSES/DWPose-LICENSE.txt")
    (output / "LICENSES/README.md").write_text(
        "# Pose addon notices\n\nThe fixed Hugging Face model revision declares Apache-2.0 in its model card. "
        "The matching upstream DWPose license text and original model card are preserved. "
        "This records upstream declarations for this exact checkpoint, not an assertion about all models. "
        "Python LICENSE.txt and every vendored wheel's dist-info licenses are retained.\n\n"
        "Use Studio 0.3.10 or later with the engine's checked Pose bootstrap. Select this directory as a Pose runtime addon "
        "in Runtime Environment, install/validate/save, and reopen. No manual service or port is required. "
        "Installed interpreter, imports and entrypoint are checked before configuration is published. "
        "Real image inference and joint review happen separately in source preparation.\n\n"
        "This package contains neither engine code, user sources nor review records. "
        "It does not install Kimodo, Blender or official browser capture. Inventory is integrity evidence, "
        "not a publisher signature or a complete clean-machine S1-S6 qualification.\n", encoding="utf-8")
    provenance = dict(schema="autospine.pose-runtime-provenance/v1",
        python=dict(version=PYTHON_VERSION, url=PYTHON_URL, sha256=PYTHON_SHA256, hash_source=PYTHON_MANIFEST_URL),
        wheels=wheels, model=dict(url=MODEL_URL, bytes=MODEL_BYTES, sha256=MODEL_SHA256,
            revision=MODEL_REVISION, model_card_url=MODEL_CARD_URL, model_card_sha256=MODEL_CARD_SHA256,
            declared_license="apache-2.0", license_url=LICENSE_URL, license_sha256=LICENSE_SHA256),
        runner_profile="dwpose-wholebody-fullcanvas-v1", engine_requirement="checked Pose bootstrap and runtime environment identity",
        limitations=["No inference or joint review is fabricated by package installation.",
                     "No global Python, venv, engine source, project state or absolute developer paths copied.",
                     "FBX, Kimodo and official framebuffer capture remain separate dependencies."])
    (output / "provenance.json").write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")
    manifest = dict(schema="autospine.pose-runtime-distribution/v1", component="pose-runtime", platform="windows-x64",
        python_root="python", python_version=PYTHON_VERSION, model_path=MODEL_PATH, model_sha256=MODEL_SHA256,
        model_bytes=MODEL_BYTES, runner_profile="dwpose-wholebody-fullcanvas-v1", provenance_path="provenance.json", files=inventory(output))
    (output / MANIFEST).write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    # Recheck input bytes so an artifact changed during copying is never published as verified.
    verified_file(python_zip, PYTHON_SHA256)
    verified_file(model, MODEL_SHA256)
    for row in wheels:
        verified_file(wheelhouse / row["filename"], row["sha256"])
    return dict(directory=str(output), manifest_sha256=sha256(output / MANIFEST),
                files=len(manifest["files"]), bytes=sum(row["bytes"] for row in manifest["files"]))


def archive(root: Path, output: Path):
    if output.exists() or output.is_symlink():
        raise ValueError("archive exists; preserve earlier artifacts")
    before = inventory(root)
    declared = json.loads((root / MANIFEST).read_text(encoding="utf-8"))["files"]
    if before != declared:
        raise ValueError("Pose inventory changed before archive")
    records = [*before, dict(path=MANIFEST, bytes=(root / MANIFEST).stat().st_size, sha256=sha256(root / MANIFEST))]
    with zipfile.ZipFile(output, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zipped:
        for row in sorted(records, key=lambda item: item["path"]):
            entry = zipfile.ZipInfo(row["path"], date_time=(1980, 1, 1, 0, 0, 0))
            entry.create_system = 3
            entry.external_attr = (stat.S_IFREG | 0o644) << 16
            entry.compress_type = zipfile.ZIP_DEFLATED
            with (root / row["path"]).open("rb") as source, zipped.open(entry, "w") as target:
                shutil.copyfileobj(source, target, 1 << 20)
    with zipfile.ZipFile(output) as zipped:
        if set(zipped.namelist()) != {row["path"] for row in records} or len(zipped.namelist()) != len(records):
            raise ValueError("Pose archive inventory differs")
        for row in records:
            with zipped.open(row["path"]) as source:
                if hashlib.file_digest(source, "sha256").hexdigest() != row["sha256"]:
                    raise ValueError("Pose archive digest differs")
    if inventory(root) != before:
        raise ValueError("Pose source changed during archive")
    return dict(archive=str(output), archive_bytes=output.stat().st_size, archive_sha256=sha256(output), verified=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build")
    for name in ("python-zip", "wheelhouse", "wheel-lock", "model", "model-card", "license-file", "output"):
        build.add_argument("--" + name, required=True, type=Path)
    zip_parser = sub.add_parser("archive")
    zip_parser.add_argument("directory", type=Path)
    zip_parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = (prepare(args.python_zip, args.wheelhouse, args.wheel_lock, args.model, args.model_card, args.license_file, args.output)
              if args.command == "build" else archive(args.directory, args.output))
    print(json.dumps(result))
