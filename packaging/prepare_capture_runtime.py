"""Assemble an offline Windows animation-check addon from fixed upstream archives.

No developer installation, browser profile, engine source or project is copied.
The builder never downloads software or runs npm/browser installers.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import stat
import tarfile
import zipfile
from pathlib import Path, PurePosixPath

MANIFEST = "capture-distribution.json"
INPUTS = {
    "node-v24.11.1-win-x64.zip": ("5355ae6d7c49eddcfde7d34ac3486820600a831bf81dc3bdca5c8db6a9bb0e76",
        "https://nodejs.org/dist/v24.11.1/node-v24.11.1-win-x64.zip"),
    "SHASUMS256.txt": ("ed0ec6c5c648a0489edebf2f21f5913e3d6e469c77d19cb4f50a729b66e77883",
        "https://nodejs.org/dist/v24.11.1/SHASUMS256.txt"),
    "chrome-headless-shell-win64.zip": ("839500db9e1b0865961ce8b05134ba3d3d71b82be5dec236d6c87ecd93e082cd",
        "https://cdn.playwright.dev/builds/cft/145.0.7632.6/win64/chrome-headless-shell-win64.zip"),
    "playwright-core-1.58.2.tgz": ("50e358de81526d5b20ce75a89c96bdc50ae653f077bbc834ada26d92046ce713",
        "https://registry.npmjs.org/playwright-core/-/playwright-core-1.58.2.tgz"),
    "spine-webgl-4.3.13.tgz": ("4d9cd1fa4608821e725283ed3bf82653541fd5ce91d8a9d2fc555a775e0d602e",
        "https://registry.npmjs.org/@esotericsoftware/spine-webgl/-/spine-webgl-4.3.13.tgz"),
    "spine-core-4.3.13.tgz": ("761d0f03f84ea073e66a55b11758afb7416cd1494ed20d70c534c324225f52b9",
        "https://registry.npmjs.org/@esotericsoftware/spine-core/-/spine-core-4.3.13.tgz"),
}
PACKAGES = (
    ("playwright-core-1.58.2.tgz", "playwright-core", "1.58.2"),
    ("spine-webgl-4.3.13.tgz", "@esotericsoftware/spine-webgl", "4.3.13"),
    ("spine-core-4.3.13.tgz", "@esotericsoftware/spine-core", "4.3.13"),
)
FIXED_TREES = {
    "browser/": "031acc7430c6f84bc43c52ff074f0290f2174e01978669a9daa1efb1dc7a5385",
    "dependencies/node_modules/playwright-core/": "3bd472e0450f8515c4795413b9ce0bfa4f849df3ad9190441e7692f0bfb09b40",
    "dependencies/node_modules/@esotericsoftware/spine-core/": "84d12bafb4e9c1ab8f1c8bea9e594f21969a4b0209f9570b123402a5cfc25c9c",
    "dependencies/node_modules/@esotericsoftware/spine-webgl/": "38af562b9487b87d02303d627381cdb4240d24b7e9b43164e2fa6bca9d2a154b",
}
FIXED_NODE = {
    "node/node.exe": (89894400, "f13ac3ca23248dc389507e8fe38c34489ab7edb3e6d6700eb6da6a0b7e128eaf"),
    "node/LICENSE": (145976, "b4c7840e841ab8f14543646bd941d01a459fb0f8ce1249244341b2a63272ca79"),
    "node/README.md": (42533, "1ff5f0b2b3a1dcb4438d51774a4b6bc942b222827f7a1b9f4d04d1f1419a525c"),
}
LICENSE_NOTICE = """# Animation-check runtime software

This addon contains fixed Node.js 24.11.1, Playwright Core 1.58.2, the
corresponding Chrome Headless Shell 145.0.7632.6 / Playwright revision 1208,
and @esotericsoftware/spine-core and spine-webgl 4.3.13.

Original terms are retained at node/LICENSE, browser/LICENSE.headless_shell,
dependencies/node_modules/playwright-core/LICENSE and each Spine package's
LICENSE. Spine Runtime's original license has its own conditions; inclusion
does not grant a Spine editor license or change those upstream terms.

Inputs are exact official archives recorded in provenance.json. The Node ZIP
matches the recorded official SHASUMS256.txt. Browser/package SHA-256 pins
record the retrieved fixed archives; an integrity inventory is not a publisher
signature. No user browser, history, credentials, project, model or engine data
is included. Installation checks software identity; actual animation capture
and human visual acceptance remain separate workflow results.
"""


def digest(file: Path) -> str:
    with file.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def safe_relative(value: str) -> str:
    parts = PurePosixPath(value).parts
    if (not value or value.startswith("/") or "\\" in value or ":" in value
            or "/".join(parts) != value or len(value) > 220
            or any(not re.fullmatch(r"[A-Za-z0-9_@.-]+", part) or part in {".", ".."}
                   or part.endswith(".")
                   or re.match(r"(?i)^(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\.|$)", part)
                   for part in parts)):
        raise ValueError("unsafe capture artifact path")
    return value


def record_file(root: Path, name: str, source, size: int, *, seen: set[str]):
    name = safe_relative(name)
    if name.lower() in seen or not 0 <= size <= 256 << 20:
        raise ValueError("capture alias or expansion limit")
    seen.add(name.lower())
    output = root / name
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("xb") as target:
        copied = 0
        while block := source.read(1 << 20):
            copied += len(block)
            if copied > size:
                raise ValueError("capture input expanded past declared size")
            target.write(block)
        if copied != size:
            raise ValueError("capture input size differs")


def extract_zip(file: Path, root: Path, prefix: str, *, selected=None):
    seen, total = set(), 0
    with zipfile.ZipFile(file) as archive:
        for item in archive.infolist():
            name = item.filename.rstrip("/")
            safe_relative(name)
            if name == prefix and item.is_dir():
                continue
            if stat.S_ISLNK(item.external_attr >> 16) or not name.startswith(prefix + "/"):
                raise ValueError("capture archive link or root mismatch")
            relative = name[len(prefix) + 1:]
            if item.is_dir():
                continue
            if selected is not None and relative not in selected:
                continue
            total += item.file_size
            if total > 512 << 20:
                raise ValueError("capture archive expansion budget exceeded")
            with archive.open(item) as source:
                record_file(root, relative, source, item.file_size, seen=seen)
    if selected is not None and seen != {name.lower() for name in selected}:
        raise ValueError("capture ZIP missing fixed entries")


def extract_tar(file: Path, root: Path):
    seen, total = set(), 0
    with tarfile.open(file, "r:gz") as archive:
        for item in archive.getmembers():
            name = item.name.rstrip("/")
            safe_relative(name)
            if not name.startswith("package/") or not (item.isfile() or item.isdir()):
                raise ValueError("capture npm link or root mismatch")
            if item.isdir():
                continue
            total += item.size
            if total > 32 << 20 or item.size > 16 << 20:
                raise ValueError("capture npm expansion budget exceeded")
            with archive.extractfile(item) as source:
                record_file(root, name[len("package/"):], source, item.size, seen=seen)


def inventory(root: Path):
    rows = []
    for file in sorted(root.rglob("*")):
        info = file.lstat()
        if stat.S_ISLNK(info.st_mode) or (not file.is_dir()
                and (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1)):
            raise ValueError("capture runtime contains non-independent files")
        if file.is_file() and file.name != MANIFEST:
            name = safe_relative(file.relative_to(root).as_posix())
            rows.append(dict(path=name, bytes=info.st_size, sha256=digest(file)))
    if len(rows) > 8192 or sum(row["bytes"] for row in rows) > 768 << 20:
        raise ValueError("capture runtime exceeds inventory budget")
    return rows


def tree_identity(rows, prefix):
    selected = [dict(path=row["path"][len(prefix):], bytes=row["bytes"], sha256=row["sha256"])
                for row in rows if row["path"].startswith(prefix)]
    selected.sort(key=lambda row: row["path"])
    payload = json.dumps(selected, ensure_ascii=True, separators=(",", ":")).encode()
    return dict(files=len(selected), bytes=sum(row["bytes"] for row in selected),
                sha256=hashlib.sha256(payload).hexdigest())


def distribution_manifest(rows):
    return dict(schema="autospine.capture-runtime-distribution/v1", component="capture-runtime",
        platform="windows-x64", runtime_version="4.3.13", playwright_version="1.58.2",
        node_version="24.11.1", browser_version="145.0.7632.6", browser_revision="1208",
        capture_profile="official-webgl-swiftshader-native-v1", node_path="node/node.exe",
        browser_path="browser/chrome-headless-shell.exe", dependencies_root="dependencies",
        provenance_path="provenance.json", files=rows)


def verify_software_inventory(rows):
    by_path = {row["path"]: row for row in rows}
    if len(by_path) != len(rows):
        raise ValueError("duplicate capture inventory path")
    for prefix, expected in FIXED_TREES.items():
        if tree_identity(rows, prefix)["sha256"] != expected:
            raise ValueError("fixed capture software tree differs: " + prefix)
    for name, (size, expected) in FIXED_NODE.items():
        row = by_path.get(name, {})
        if row.get("bytes") != size or row.get("sha256") != expected:
            raise ValueError("fixed capture Node file differs")
    if not {"provenance.json", "LICENSES/README.md"} <= by_path.keys() or any(
            name not in FIXED_NODE and name not in {"provenance.json", "LICENSES/README.md"}
            and not any(name.startswith(prefix) for prefix in FIXED_TREES) for name in by_path):
        raise ValueError("unexpected capture software file")


def prepare(inputs: Path, output: Path):
    for name, (expected, _) in INPUTS.items():
        file = inputs / name
        info = file.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or digest(file) != expected:
            raise ValueError("fixed capture input verification failed: " + name)
    shasums = (inputs / "SHASUMS256.txt").read_text()
    if INPUTS["node-v24.11.1-win-x64.zip"][0] + "  node-v24.11.1-win-x64.zip" not in shasums.splitlines():
        raise ValueError("official Node ZIP hash differs")
    output.mkdir(parents=True, exist_ok=False)
    extract_zip(inputs / "node-v24.11.1-win-x64.zip", output / "node", "node-v24.11.1-win-x64",
                selected={"node.exe", "LICENSE", "README.md"})
    extract_zip(inputs / "chrome-headless-shell-win64.zip", output / "browser", "chrome-headless-shell-win64")
    for filename, name, version in PACKAGES:
        package = output / "dependencies/node_modules" / name
        extract_tar(inputs / filename, package)
        metadata = json.loads((package / "package.json").read_text())
        if metadata["name"] != name or metadata["version"] != version or not (package / "LICENSE").is_file():
            raise ValueError("capture package identity or license differs")
    license_root = output / "LICENSES"
    license_root.mkdir()
    (license_root / "README.md").write_text(LICENSE_NOTICE, encoding="utf-8", newline="\n")
    provenance = dict(schema="autospine.capture-runtime-provenance/v1", inputs=[
        dict(filename=name, sha256=sha, url=url, bytes=(inputs / name).stat().st_size)
        for name, (sha, url) in INPUTS.items()], authority="none", production_authorized=False)
    (output / "provenance.json").write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")
    rows = inventory(output)
    verify_software_inventory(rows)
    manifest = distribution_manifest(rows)
    (output / MANIFEST).write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return dict(directory=str(output), manifest_sha256=digest(output / MANIFEST), files=len(rows),
                bytes=sum(row["bytes"] for row in rows), trees={prefix: tree_identity(rows, prefix) for prefix in
                ["browser/", "dependencies/node_modules/playwright-core/",
                 "dependencies/node_modules/@esotericsoftware/spine-core/",
                 "dependencies/node_modules/@esotericsoftware/spine-webgl/"]})


def archive(root: Path, output: Path):
    manifest = json.loads((root / MANIFEST).read_text())
    rows = inventory(root)
    if manifest != distribution_manifest(rows):
        raise ValueError("capture inventory changed before archive")
    verify_software_inventory(rows)
    with zipfile.ZipFile(output, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as result:
        for row in rows + [dict(path=MANIFEST)]:
            result.write(root / row["path"], row["path"])
    with zipfile.ZipFile(output) as check:
        expected = {row["path"]: row for row in rows}
        expected[MANIFEST] = dict(bytes=(root / MANIFEST).stat().st_size, sha256=digest(root / MANIFEST))
        if set(check.namelist()) != set(expected) or len(check.namelist()) != len(expected):
            raise ValueError("capture ZIP inventory differs")
        for name, row in expected.items():
            with check.open(name) as source:
                if check.getinfo(name).file_size != row["bytes"] or hashlib.file_digest(source, "sha256").hexdigest() != row["sha256"]:
                    raise ValueError("capture ZIP bytes differ")
    return dict(path=str(output), bytes=output.stat().st_size, sha256=digest(output))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build")
    build.add_argument("--inputs", required=True, type=Path)
    build.add_argument("--output", required=True, type=Path)
    pack = sub.add_parser("archive")
    pack.add_argument("directory", type=Path)
    pack.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(prepare(args.inputs, args.output) if args.command == "build" else archive(args.directory, args.output)))
