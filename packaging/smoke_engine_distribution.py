"""Real empty-state HTTP startup from a verified independent engine artifact.

Uses an explicitly selected, already installed Python. This is not clean-machine
installation, PSD intake, pose inference, animation acceptance or Runtime QA.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import json
import os
from pathlib import Path
import queue
import socket
import subprocess
import threading
import time
from urllib.request import Request, urlopen

from engine_distribution import (SCHEMA, RUNTIME_DEPENDENCIES, LIMITATIONS, canonical_bytes,
                                 safe_path, validate_manifest, verify_directory)
from prepare_core_runtime import PACKAGE_ROOTS, PYTHON_FILES, PYTHON_VERSION, PTH, site_customize_archive


def validate_core_manifest(value):
    """Explicit core inventory contract; inventory is not runtime execution proof."""
    keys = {"schema", "component", "scope", "version", "source_commit", "platform", "engine_root", "files", "excludes", "runtime_dependencies", "limitations", "python_root", "python_version"}
    if type(value) is not dict or set(value) != keys or value.get("schema") != SCHEMA or value.get("scope") != "engine-core-runtime" or value.get("component") != "engine-core-runtime" or value.get("python_root") != "runtime/python" or value.get("python_version") != PYTHON_VERSION:
        raise ValueError("core_manifest_invalid")
    dependencies = [dict(item, bundled=index < 4) for index, item in enumerate(RUNTIME_DEPENDENCIES)]
    if value["runtime_dependencies"] != dependencies or type(value["limitations"]) is not list or not value["limitations"] or any(type(item) is not str or not item for item in value["limitations"]):
        raise ValueError("core_manifest_capabilities_invalid")
    if type(value["files"]) is not list or not 1 <= len(value["files"]) <= 32768:
        raise ValueError("core_inventory_invalid")
    source = deepcopy(value)
    source.pop("python_root"); source.pop("python_version")
    source.update(scope="engine-source-only", component="engine-source", runtime_dependencies=RUNTIME_DEPENDENCIES, limitations=LIMITATIONS)
    source["files"] = [row for row in value["files"] if type(row) is dict and isinstance(row.get("path"), str) and row["path"].startswith("engine/")]
    validate_manifest(source)
    seen, total = set(), 0
    for row in value["files"]:
        if type(row) is not dict or set(row) != {"path", "bytes", "sha256"}:
            raise ValueError("core_inventory_invalid")
        name = str(safe_path(row["path"]))
        if name.lower() in seen or type(row["bytes"]) is not int or not 0 <= row["bytes"] <= 64 * 1024 * 1024:
            raise ValueError("core_inventory_invalid")
        if type(row["sha256"]) is not str or len(row["sha256"]) != 64 or any(letter not in "0123456789abcdef" for letter in row["sha256"]):
            raise ValueError("core_inventory_invalid")
        seen.add(name.lower()); total += row["bytes"]
        if total > 512 * 1024 * 1024: raise ValueError("core_inventory_limit")
        if name.startswith("engine/"): continue
        if name in {"runtime/PROVENANCE.json", "runtime/python/sitecustomize.zip"} or name in {"runtime/python/" + file for file in PYTHON_FILES}: continue
        prefix = "runtime/python/Lib/site-packages/"
        if not name.startswith(prefix) or name[len(prefix):].split("/")[0] not in PACKAGE_ROOTS:
            raise ValueError("core_inventory_path_invalid")
        if any(part.lower() in {"models", "checkpoints", "credentials", "__pycache__", ".git"} for part in safe_path(name).parts):
            raise ValueError("core_inventory_path_invalid")
        if name.endswith((".exe", ".onnx", ".safetensors", ".pyc", ".whl", ".psd", ".psb", ".fbx", ".bvh", ".pth")):
            raise ValueError("core_inventory_path_invalid")
    if not ({"runtime/python/" + file for file in PYTHON_FILES} | {"runtime/python/sitecustomize.zip"}) <= {row["path"] for row in value["files"]}:
        raise ValueError("core_python_incomplete")
    return dict(files=len(value["files"]), bytes=total, scope="engine-core-runtime", source_commit=value["source_commit"])

LAUNCHER = r'''
import json, os, sys, threading
from pathlib import Path
engine, workspace, state = map(Path, sys.argv[1:4])
core_mode = sys.argv[4] == 'core'
sys.path.insert(0, str(engine / 'src'))
from autospine_workbench.studio_process_lifetime import keep_owned_process_tree
owned = keep_owned_process_tree()
core_probe = None
if core_mode:
    import importlib.util, importlib.metadata, site, subprocess
    root = engine.parent.resolve()
    if not sys.flags.isolated or not sys.flags.ignore_environment or site.ENABLE_USER_SITE is not False or not sys.dont_write_bytecode:
        raise ValueError('core_python_not_isolated')
    if importlib.util.find_spec('autospine_global_sentinel') is not None:
        raise ValueError('external_site_participated')
    if any(not Path(item).resolve().is_relative_to(root) for item in sys.path):
        raise ValueError('core_python_external_search_path')
    from PIL import Image
    from psd_tools import PSDImage
    from autospine_workbench.automation.psd_intake_worker import extract_psd
    pixel = (11, 22, 33, 255)
    psd = PSDImage.new('RGB', (1, 1))
    psd.create_pixel_layer(Image.new('RGBA', (1, 1), pixel), name='isolated-decode-fixture')
    source = workspace.parent / 'isolated-decode-fixture.psd'
    psd.save(source)
    decoded = workspace.parent / 'isolated-decode-fixture'
    audit = extract_psd(source, decoded)
    if audit['canvas'] != [1, 1] or audit['pixel_layers'] != 1 or Image.open(decoded / audit['layers'][0]['crop_path']).convert('RGBA').getpixel((0, 0)) != pixel:
        raise ValueError('core_psd_decoder_mismatch')
    worker_decoded = workspace.parent / 'worker-decode-fixture'
    worker = subprocess.run([sys.executable, '-m', 'autospine_workbench.automation.psd_intake_worker',
        '--input', str(source), '--output', str(worker_decoded)], capture_output=True, text=True, timeout=20,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    if worker.returncode or json.loads(worker.stdout).get('pixel_layers') != 1:
        raise ValueError('core_psd_worker_failed')
    worker_audit = json.loads((worker_decoded / 'audit.json').read_text(encoding='utf-8'))
    if worker_audit['authority'] != 'none' or Image.open(worker_decoded / worker_audit['layers'][0]['crop_path']).convert('RGBA').getpixel((0, 0)) != pixel:
        raise ValueError('core_psd_worker_mismatch')
    import numpy as np
    from scipy.optimize import least_squares
    import jsonschema
    solved = least_squares(lambda x: np.asarray([x[0] - 3]), [0]).x[0]
    if abs(solved - 3) > 1e-8: raise ValueError('core_solver_failed')
    jsonschema.validate({'value': float(solved)}, {'type': 'object', 'properties': {'value': {'type': 'number'}}, 'required': ['value']})
    versions = {name: importlib.metadata.version(name) for name in ('numpy', 'scipy', 'Pillow', 'psd-tools', 'jsonschema')}
    package_roots = {name: str(importlib.metadata.distribution(name).locate_file('').resolve()) for name in versions}
    if any(not Path(item).is_relative_to(root) for item in package_roots.values()): raise ValueError('core_package_external_root')
    core_probe = dict(isolated=sys.flags.isolated, ignore_environment=sys.flags.ignore_environment, dont_write_bytecode=sys.dont_write_bytecode,
        user_site_enabled=site.ENABLE_USER_SITE, foreign_module_visible=False,
        sys_path=sys.path, package_roots=package_roots, versions=versions,
        psd_decode=dict(canvas=audit['canvas'], pixel_layers=audit['pixel_layers'], rgba=list(pixel), authority=audit['authority']),
        psd_subprocess_without_B=dict(exit_code=worker.returncode, pixel_layers=worker_audit['pixel_layers'], authority=worker_audit['authority']),
        scipy_solution=float(solved), schema_validation='passed')
from autospine_workbench.server import create_server
server = create_server('127.0.0.1', 0, workspace, engine / 'web', state)
def stop():
    for line in sys.stdin:
        if line.strip() == 'shutdown': break
    deadline = threading.Timer(15, lambda: os._exit(124))
    deadline.daemon = True
    deadline.start()
    server.shutdown()
threading.Thread(target=stop, daemon=True).start()
print(json.dumps(dict(port=server.server_port, pid=os.getpid(), python=sys.executable,
    python_version=sys.version.split()[0], engine_session=server.engine_session,
    process_tree_owned=owned.owns_windows_process_tree, core_probe=core_probe)), flush=True)
try: server.serve_forever(poll_interval=.1)
finally: server.server_close()
'''


def smoke(root: Path, python: Path, output: Path) -> dict:
    root, python, output = Path(root).resolve(strict=True), Path(python).resolve(strict=True), Path(output).absolute()
    if not python.is_file() or output.exists() or output.is_symlink():
        raise ValueError("smoke_path_invalid")
    scope = json.loads((root / 'engine-distribution.json').read_text(encoding='utf-8')).get('scope')
    core_mode = scope == 'engine-core-runtime'
    verifier = validate_core_manifest if core_mode else validate_manifest
    inventory = verify_directory(root, validator=verifier)
    if core_mode and (python != (root / 'runtime/python/python.exe').resolve(strict=True) or (root / 'runtime/python/python314._pth').read_bytes() != PTH or
                      (root / 'runtime/python/sitecustomize.zip').read_bytes() != site_customize_archive()):
        raise ValueError('core_python_entry_mismatch')
    output.mkdir(parents=True, exist_ok=False)
    workspace, state = output / "new-workspace", output / "new-state"
    workspace.mkdir(); state.mkdir()
    report = dict(ok=False, artifact=inventory, python_launcher=str(python), checks=[], errors=[],
                  scope="verified-core-bundle-new-empty-state" if core_mode else "verified-source-new-empty-state-with-existing-python", limitations=[
                      "This is an isolated artifact test on the current machine, not a separate clean Windows computer.",
                      "Only a generated one-pixel PSD and scalar solver are tested; no character, Pose, Kimodo, FBX, cloth animation or framebuffer job is started." if core_mode else
                      "Existing installed Python is used; no PSD, Pose, Kimodo, FBX, cloth, animation or framebuffer job is started."])
    child, handshake = None, None
    logs = {"stdout": [], "stderr": []}
    startup = queue.Queue()
    def read_stdout(stream):
        for line in stream:
            if sum(map(len, logs["stdout"])) < 65536: logs["stdout"].append(line)
            try:
                value = json.loads(line)
                if type(value) is dict and "port" in value and "engine_session" in value:
                    startup.put(value)
            except ValueError:
                pass
    def read_stderr(stream):
        for line in stream:
            if sum(map(len, logs["stderr"])) < 65536: logs["stderr"].append(line)
    try:
        environment = os.environ.copy()
        # Never inherit unrelated mutable engine/pose/model path overrides.
        for key in tuple(environment):
            if key.startswith("AUTOSPINE_") or key == "PYTHONPATH": environment.pop(key, None)
        if core_mode:
            foreign = output / 'foreign-global-site'
            foreign.mkdir()
            (foreign / 'autospine_global_sentinel.py').write_text("raise RuntimeError('foreign environment entered')\n", encoding='utf-8')
            environment['PYTHONPATH'] = str(foreign)
        child = subprocess.Popen([str(python), "-I", "-B", "-u", "-c", LAUNCHER, str(root / "engine"), str(workspace), str(state), 'core' if core_mode else 'source'],
                                 stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                 cwd=output, env=environment, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        readers = [threading.Thread(target=read_stdout, args=(child.stdout,), daemon=True), threading.Thread(target=read_stderr, args=(child.stderr,), daemon=True)]
        for reader in readers: reader.start()
        handshake = startup.get(timeout=45)
        report["handshake"] = handshake
        if core_mode:
            probe = handshake.get('core_probe')
            if not probe or probe.get('versions') != {'numpy': '2.4.6', 'scipy': '1.18.0', 'Pillow': '12.3.0', 'psd-tools': '1.18.0', 'jsonschema': '4.26.0'}:
                raise ValueError('core_versions_mismatch')
            report['checks'].extend(['embedded Python isolated its search paths and ignored external PYTHONPATH bait',
                'bundled decoder and actual worker without -B extracted a generated one-pixel PSD with exact RGBA and authority none',
                'bundled NumPy/SciPy solved a scalar numerical constraint and JSON schema validation executed'])
        session = handshake["engine_session"]
        port = handshake["port"]
        origin = "http://127.0.0.1:" + str(port)
        if session["workspace_root"] != str(workspace.resolve()) or session["state_root"] != str(state.resolve()) or session["origin"] != origin:
            raise ValueError("smoke_session_mismatch")
        if os.name == "nt" and not handshake["process_tree_owned"]:
            raise ValueError("smoke_process_tree_unowned")
        report["checks"].append("artifact server bound an OS-assigned loopback port with exact empty workspace/state ownership")
        def read(path):
            request = Request(origin + path, headers={"X-Autospine-Engine-Session": session["nonce"]})
            with urlopen(request, timeout=10) as response:
                raw = response.read(4 * 1024 * 1024 + 1)
                if len(raw) > 4 * 1024 * 1024: raise ValueError("smoke_response_limit")
                return response.status, raw
        status, raw = read("/api/health")
        health = json.loads(raw)
        if status != 200 or health.get("engine_session") != session: raise ValueError("smoke_health_mismatch")
        report["health"] = health
        report["checks"].append("real health endpoint confirms exact managed session")
        status, raw = read("/api/projects")
        projects = json.loads(raw)
        if status != 200 or projects.get("projects") != []: raise ValueError("smoke_projects_not_empty")
        report["checks"].append("new workspace project catalog is empty; no existing audits were discovered")
        status, raw = read("/")
        if status != 200 or b"<html" not in raw.lower(): raise ValueError("smoke_web_missing")
        report["checks"].append("packaged web entry served successfully")
    except BaseException as exc:
        report["errors"].append(type(exc).__name__ + ": " + str(exc))
    finally:
        if child is not None:
            if child.poll() is None:
                try:
                    child.stdin.write("shutdown\n"); child.stdin.flush(); child.stdin.close()
                    child.wait(timeout=20)
                except Exception as exc:
                    report["errors"].append("shutdown: " + str(exc))
                    child.kill(); child.wait(timeout=10)
            report["exit_code"] = child.returncode
            if child.returncode != 0: report["errors"].append("engine_exit_nonzero")
            if handshake:
                with socket.socket() as connection:
                    connection.settimeout(2)
                    if connection.connect_ex(("127.0.0.1", handshake["port"])) == 0: report["errors"].append("owned_listener_remains")
                    else: report["checks"].append("owned worker exited cleanly and its listener is gone")
        try:
            if verify_directory(root, validator=verifier) != inventory: raise ValueError("artifact_changed")
            report["checks"].append("artifact inventory remains unchanged after server startup/shutdown")
        except Exception as exc:
            report["errors"].append(str(exc))
        report["logs"] = logs
        report["ok"] = not report["errors"] and len(report["checks"]) == (9 if core_mode else 6)
        (output / "report.json").write_bytes(canonical_bytes(report))
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    result = smoke(args.bundle, args.python, args.output)
    print(json.dumps({key: result[key] for key in ("ok", "checks", "errors", "scope")}, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
