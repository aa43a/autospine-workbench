"""Build the offline FBX converter from a fixed official Blender archive.

No developer installation, user configuration, source asset or model is copied.
The caller retrieves the pinned upstream archives; this builder has no network
or executable installation step. All upstream software and licenses are kept.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import stat
import zipfile
from pathlib import Path, PurePosixPath

MANIFEST = "blender-distribution.json"
VERSION = "5.2.1"
PROFILE = "blender-5.2.1-isolated-task-v1"
ZIP_NAME = "blender-5.2.1-windows-x64.zip"
ZIP_SHA = "0e631dad7d0cad6d5d18abdd2e2550f6c0213215334eda00ddbd3d22b96ecb2c"
CHECKSUM_NAME = "blender-5.2.1.sha256"
CHECKSUM_SHA = "eef9101c390c9dadbcb688d301b15ee6326f98f286bf88bed0f72c1e9e57473b"
BASE_URL = "https://download.blender.org/release/Blender5.2/"
SOURCE_URL = "https://download.blender.org/source/blender-5.2.1.tar.xz"
ROOT = "blender-5.2.1-windows-x64"
FIXED_TREE = dict(files=6526, bytes=944579836,
    sha256="7761fa43309cc58f8b4d02fcb993bed1a63cedea1e626b3ea9c1ae8c0d3fad5e")
EXE = dict(bytes=113014232,
    sha256="8f7a131ad8bc148edc218b334f07d92a57f5a357fa66d913b290537fd8353c06")
NOTICE = """# FBX conversion runtime

This separate addon retains the complete official Windows x64 Blender 5.2.1
software tree and original copyright and license files, including
b/copyright.txt, b/license/license.md, b/license/licenses.json and all third
party terms. These upstream terms are not replaced by AutoSpine's terms.

Corresponding Blender source: https://download.blender.org/source/blender-5.2.1.tar.xz
The separately provided original source archive accompanies the binary release.
See the original license files for applicable terms and copyright notices.

The upstream ZIP and official checksum table are pinned in provenance.json.
SHA-256 inventory is an integrity record, not a publisher signature. No user
configuration, project, credentials, engine state or animation is included.
Conversion runs with task-local configuration and temporary files. Installation
does not accept a role binding, animation candidate or human visual review.
"""


def digest(file: Path) -> str:
    with file.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def safe_relative(value: str) -> str:
    parts = PurePosixPath(value).parts
    if (not value or value.startswith("/") or "\\" in value or ":" in value
            or "/".join(parts) != value or len(value) > 200
            or any(not re.fullmatch(r"[A-Za-z0-9_@().+&, -]+", part)
                   or part in {".", ".."} or part.endswith((".", " "))
                   or part.startswith(" ")
                   or re.match(r"(?i)^(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\.|$)", part)
                   for part in parts)):
        raise ValueError("unsafe Blender artifact path")
    return value


def inventory(root: Path) -> list[dict]:
    rows = []
    for file in sorted(root.rglob("*")):
        info = file.lstat()
        if stat.S_ISLNK(info.st_mode):
            raise ValueError("Blender distribution contains link")
        if stat.S_ISDIR(info.st_mode):
            continue
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ValueError("Blender distribution contains non-independent file")
        relative = safe_relative(file.relative_to(root).as_posix())
        if relative == MANIFEST:
            continue
        rows.append(dict(path=relative, bytes=info.st_size, sha256=digest(file)))
    return rows


def tree_identity(rows: list[dict]) -> dict:
    software = [row for row in rows if row["path"].startswith("b/")]
    serial = "".join(f'{row["path"][2:]}\0{row["bytes"]}\0{row["sha256"]}\n'
                     for row in sorted(software, key=lambda row: row["path"]))
    return dict(files=len(software), bytes=sum(row["bytes"] for row in software),
                sha256=hashlib.sha256(serial.encode("utf-8")).hexdigest())


def verify_software_inventory(rows: list[dict]):
    by_path = {row["path"]: row for row in rows}
    if len(by_path) != len(rows) or tree_identity(rows) != FIXED_TREE:
        raise ValueError("fixed Blender software tree differs")
    if {key: by_path.get("b/blender.exe", {}).get(key) for key in EXE} != EXE:
        raise ValueError("fixed Blender executable differs")
    extras = set(by_path) - {row["path"] for row in rows if row["path"].startswith("b/")}
    if extras != {"provenance.json", "LICENSES/README.md"}:
        raise ValueError("unexpected Blender distribution files")


def distribution_manifest(rows: list[dict]) -> dict:
    return dict(schema="autospine.blender-runtime-distribution/v1",
        component="blender-runtime", platform="windows-x64", blender_version=VERSION,
        conversion_profile=PROFILE, blender_path="b/blender.exe",
        provenance_path="provenance.json", files=rows)


def prepare(inputs: Path, output: Path) -> dict:
    for name, expected in ((ZIP_NAME, ZIP_SHA), (CHECKSUM_NAME, CHECKSUM_SHA)):
        file = inputs / name
        info = file.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or digest(file) != expected:
            raise ValueError("fixed Blender input verification failed: " + name)
    if ZIP_SHA + "  " + ZIP_NAME not in (inputs / CHECKSUM_NAME).read_text().splitlines():
        raise ValueError("official Blender checksum differs")
    output.mkdir(parents=True, exist_ok=False)
    seen, total = set(), 0
    with zipfile.ZipFile(inputs / ZIP_NAME) as archive:
        for item in archive.infolist():
            name = safe_relative(item.filename.rstrip("/"))
            if item.is_dir() and name == ROOT:
                continue
            if (stat.S_ISLNK(item.external_attr >> 16) or not name.startswith(ROOT + "/")):
                raise ValueError("Blender archive link or root differs")
            if item.is_dir():
                continue
            relative = safe_relative("b/" + name[len(ROOT) + 1:])
            if relative.lower() in seen or not 0 <= item.file_size <= 128 << 20:
                raise ValueError("Blender archive alias or expansion limit")
            seen.add(relative.lower())
            total += item.file_size
            if total > 1024 << 20 or len(seen) > 8192:
                raise ValueError("Blender archive expansion budget exceeded")
            file = output / relative
            file.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(item) as source, file.open("xb") as target:
                shutil.copyfileobj(source, target, 1 << 20)
            if file.stat().st_size != item.file_size:
                raise ValueError("Blender expanded file size differs")
    (output / "LICENSES").mkdir()
    (output / "LICENSES/README.md").write_text(NOTICE, encoding="utf-8", newline="\n")
    provenance = dict(schema="autospine.blender-runtime-provenance/v1", inputs=[
        dict(filename=name, url=BASE_URL + name, sha256=expected,
             bytes=(inputs / name).stat().st_size)
        for name, expected in ((ZIP_NAME, ZIP_SHA), (CHECKSUM_NAME, CHECKSUM_SHA))],
        corresponding_source_url=SOURCE_URL, authority="none", production_authorized=False)
    (output / "provenance.json").write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")
    rows = inventory(output)
    verify_software_inventory(rows)
    (output / MANIFEST).write_text(json.dumps(distribution_manifest(rows), indent=2) + "\n", encoding="utf-8")
    return dict(directory=str(output), manifest_sha256=digest(output / MANIFEST),
                files=len(rows), bytes=sum(row["bytes"] for row in rows), tree=tree_identity(rows))


def archive(root: Path, output: Path):
    rows = inventory(root)
    verify_software_inventory(rows)
    if json.loads((root / MANIFEST).read_text()) != distribution_manifest(rows):
        raise ValueError("Blender inventory changed before archive")
    with zipfile.ZipFile(output, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as result:
        for row in rows:
            result.write(root / row["path"], root.name + "/" + row["path"])
        result.write(root / MANIFEST, root.name + "/" + MANIFEST)
    return dict(zip=str(output), bytes=output.stat().st_size, sha256=digest(output))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--zip", type=Path)
    args = parser.parse_args()
    result = prepare(args.inputs.resolve(), args.output.resolve())
    if args.zip:
        result["archive"] = archive(args.output, args.zip)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
