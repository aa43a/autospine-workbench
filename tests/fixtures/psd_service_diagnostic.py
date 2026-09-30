"""Bounded real frozen-core PSD intake observation, with isolated test state.

Baseline diagnostic wrappers delegate the original Popen/run arguments.
An explicit differential mode changes only worker stdin to DEVNULL; this is
test-process instrumentation, not a production fix or replacement decoder.
No production code, frozen artifact, user project or human review is changed.
"""
from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
import faulthandler
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import stat
import sys
import threading
import time
from urllib.request import Request, urlopen


class ProcessEntry(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD), ("th32DefaultHeapID", ctypes.c_size_t),
        ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", wintypes.LONG),
        ("dwFlags", wintypes.DWORD), ("szExeFile", wintypes.WCHAR * 260),
    ]


def descendants(pid):
    api = ctypes.WinDLL("kernel32", use_last_error=True)
    api.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    api.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    api.CloseHandle.argtypes = [wintypes.HANDLE]
    api.CloseHandle.restype = wintypes.BOOL
    for name in ("Process32FirstW", "Process32NextW"):
        getattr(api, name).argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessEntry)]
        getattr(api, name).restype = wintypes.BOOL
    handle = api.CreateToolhelp32Snapshot(2, 0)
    if handle == ctypes.c_void_p(-1).value:
        raise OSError(ctypes.get_last_error(), "Process snapshot failed")
    entries = []
    try:
        entry = ProcessEntry()
        entry.dwSize = ctypes.sizeof(entry)
        more = api.Process32FirstW(handle, ctypes.byref(entry))
        while more:
            entries.append(dict(pid=entry.th32ProcessID, parent_pid=entry.th32ParentProcessID,
                                executable=entry.szExeFile, threads=entry.cntThreads))
            more = api.Process32NextW(handle, ctypes.byref(entry))
    finally:
        api.CloseHandle(handle)
    selected, known = [], {pid}
    while True:
        found = [row for row in entries if row["parent_pid"] in known and row["pid"] not in known]
        if not found:
            return selected
        selected.extend(found)
        known.update(row["pid"] for row in found)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--parent-stdin-watch", action="store_true")
    parser.add_argument("--worker-stdin-devnull", action="store_true")
    args = parser.parse_args()
    bundle, source = args.bundle.resolve(strict=True), args.source.resolve(strict=True)
    if not source.is_file() or source.suffix.lower() != ".psd" or not 26 <= source.stat().st_size <= 256 * 1024 * 1024:
        raise ValueError("Source must be a bounded existing PSD")
    output = args.output.absolute()
    diagnostic_root = Path(__file__).resolve().parents[2] / "release/test-results"
    diagnostic_root = diagnostic_root.resolve(strict=True)
    if not output.is_relative_to(diagnostic_root) or output == diagnostic_root:
        raise ValueError("Output must be below this engine repository's release/test-results")
    for selected in (output, *output.parents):
        if not selected.exists() and not selected.is_symlink():
            continue
        attributes = selected.lstat()
        if selected.is_symlink() or getattr(attributes, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
            raise ValueError("Diagnostic output cannot traverse links or reparse points")
        if selected == diagnostic_root:
            break
    if output.exists() or output.is_symlink():
        raise ValueError("Diagnostic output must be a new directory")
    if Path(sys.executable).resolve() != (bundle / "runtime/python/python.exe").resolve(strict=True):
        raise ValueError("Diagnostic must use the artifact private Python")
    from autospine_workbench.studio_process_lifetime import keep_owned_process_tree
    owner = keep_owned_process_tree()
    output.mkdir(parents=True, exist_ok=False)
    workspace, state = output / "workspace", output / "state"
    workspace.mkdir(); state.mkdir()
    before = sha256(source.read_bytes()).hexdigest()
    started = time.monotonic()
    report = dict(schema="autospine.psd-service-diagnostic/v1", ok=False,
                  python=sys.executable, python_version=sys.version, isolated=sys.flags.isolated,
                  dont_write_bytecode=sys.dont_write_bytecode, engine_root=str(bundle / "engine"),
                  source=dict(path=str(source), bytes=source.stat().st_size, sha256=before),
                  process_id=os.getpid(), process_tree_owned=owner.owns_windows_process_tree,
                  parent_stdin_watch=args.parent_stdin_watch, observations=[], launches=[], runs=[],
                  worker_stdin_devnull=args.worker_stdin_devnull,
                  scope="Actual frozen-core create_server PSD intake on this computer; no GUI or user project")
    report_file = output / "report.json"
    save_lock = threading.RLock()

    def save():
        with save_lock:
            report_file.write_text(json.dumps(report, ensure_ascii=True, indent=2) + "\n", encoding="utf8")

    original_popen, original_run = subprocess.Popen, subprocess.run

    class ObservedPopen(original_popen):
        def __init__(self, command, *arguments, **options):
            if args.worker_stdin_devnull:
                options = dict(options, stdin=subprocess.DEVNULL)
            row = dict(command=list(command), started_seconds=time.monotonic() - started,
                       stdin_argument=str(options.get("stdin", "not-specified")),
                       creationflags=options.get("creationflags", 0), cwd=options.get("cwd"),
                       stage="entering-Popen")
            report["launches"].append(row); save()
            super().__init__(command, *arguments, **options)
            row.update(pid=self.pid, stage="launched", launched_seconds=time.monotonic() - started)
            save()

    def observed_run(command, *arguments, **options):
        row = dict(command=list(command), started_seconds=time.monotonic() - started, stage="running")
        report["runs"].append(row); save()
        try:
            result = original_run(command, *arguments, **options)
            row.update(returncode=result.returncode, stdout=result.stdout.decode("utf8", "replace")[:16384],
                       stderr=result.stderr.decode("utf8", "replace")[:16384], stage="returned")
            return result
        except BaseException as error:
            row.update(stage="error", error=repr(error))
            raise
        finally:
            row["ended_seconds"] = time.monotonic() - started
            save()

    subprocess.Popen, subprocess.run = ObservedPopen, observed_run
    server, serving = None, None
    # This optional control reproduces the Studio launcher read, without
    # attaching it to any existing desktop application's process or pipe.
    if args.parent_stdin_watch:
        def read_parent():
            for line in sys.stdin:
                if line.strip() == "shutdown": break
            report["parent_stdin_closed_seconds"] = time.monotonic() - started
            save()
        threading.Thread(target=read_parent, name="diagnostic-parent-stdin", daemon=True).start()
    deadline = threading.Timer(55, lambda: (save(), os._exit(124)))
    deadline.daemon = True; deadline.start()
    try:
        from autospine_workbench.server import create_server
        server = create_server("127.0.0.1", 0, workspace, bundle / "engine/web", state)
        serving = threading.Thread(target=server.serve_forever, kwargs=dict(poll_interval=.1), name="diagnostic-http")
        serving.start()
        session = server.engine_session
        report.update(engine_session=session, port=server.server_port, startup_seconds=time.monotonic() - started)
        origin = session["origin"]
        def request(route, data=None):
            headers = {"X-Autospine-Engine-Session": session["nonce"]}
            if data is not None:
                headers.update({"Origin": origin, "X-Autospine-Intent": "pipeline-preview",
                                "X-Autospine-File-Name": "diagnostic-two-layer.psd", "Content-Type": "application/octet-stream"})
            with urlopen(Request(origin + route, data=data, headers=headers), timeout=5) as result:
                return json.loads(result.read(1048576))
        report["initial_projects"] = request("/api/projects")
        report["queued"] = request("/api/asset-imports", source.read_bytes())
        job_id = report["queued"]["job_id"]
        queued_time = time.monotonic()
        save()
        print(json.dumps(dict(event="queued", pid=os.getpid(), port=server.server_port, job_id=job_id)), flush=True)
        for target in (2, 10, 30):
            while time.monotonic() - queued_time < target:
                time.sleep(min(.05, target - (time.monotonic() - queued_time)))
            job = request("/api/asset-imports/" + job_id)
            folder = state / "jobs/psd-import-v1" / job_id
            row = dict(target_seconds=target, actual_seconds=time.monotonic() - queued_time,
                       job=job, descendants=descendants(os.getpid()),
                       files=[str(file.relative_to(folder)) for file in folder.rglob("*") if file.is_file()])
            report["observations"].append(row)
            with (output / f"threads-{target}s.txt").open("w", encoding="utf8") as trace:
                faulthandler.dump_traceback(file=trace, all_threads=True)
            save()
            print(json.dumps(dict(event="observed", target_seconds=target, job=job, descendants=row["descendants"])), flush=True)
        report["projects_after"] = request("/api/projects")
        report["ok"] = report["observations"][-1]["job"]["status"] == "succeeded"
        report["source_unchanged"] = sha256(source.read_bytes()).hexdigest() == before
    except BaseException as error:
        report["error"] = repr(error)
    finally:
        report["shutdown_started_seconds"] = time.monotonic() - started
        save()
        if server:
            server.shutdown()
            if serving: serving.join(timeout=3)
            server.server_close()
        report.update(shutdown_finished_seconds=time.monotonic() - started,
                      descendants_after_shutdown=descendants(os.getpid()))
        if "queued" in report:
            result = state / "jobs/psd-import-v1" / report["queued"]["job_id"] / "result.json"
            if result.is_file():
                report["durable_job_after_shutdown"] = json.loads(result.read_text(encoding="utf8"))
        subprocess.Popen, subprocess.run = original_popen, original_run
        save()
        deadline.cancel()
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
