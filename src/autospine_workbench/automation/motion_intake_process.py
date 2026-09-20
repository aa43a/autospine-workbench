"""Process-tree cancellation and bounded progress for external motion decoders."""
import json
import os
import re
import signal
import subprocess

from .storage_io import canonical_bytes, read_document

STEPS = {'verify_source', 'convert_fbx', 'verify_bridge', 'inspect_bvh', 'compile_motion',
         'retarget', 'publish_candidate', 'runtime'}


def progress(folder, step):
    if step not in STEPS:
        raise ValueError('motion_progress_invalid')
    temporary = folder / 'progress.tmp'
    temporary.write_bytes(canonical_bytes(dict(step=step)))
    os.replace(temporary, folder / 'progress.json')


def read_progress(folder):
    try:
        step = read_document(folder / 'progress.json').get('step')
        return step if step in STEPS else None
    except (OSError, RuntimeError, ValueError):
        return None


def failure_reason(path):
    # Decoder output is diagnostic; never expose local paths or arbitrary stdout.
    with path.open('rb') as handle:
        handle.seek(max(0, os.fstat(handle.fileno()).st_size - 4096))
        lines = handle.read(4096).decode('utf-8', errors='replace').splitlines()
    for line in reversed(lines[-3:]):
        try:
            reason = json.loads(line).get('reason_code', '')
            if isinstance(reason, str) and re.fullmatch(r'(motion|character)_[a-z0-9_]{1,80}', reason):
                return reason
        except (ValueError, AttributeError):
            pass
    return 'motion_decode_failed'


def terminate_tree(process):
    if process.poll() is not None:
        return
    if os.name == 'nt':
        try:
            subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
                           capture_output=True, timeout=10, check=True)
        except (OSError, subprocess.SubprocessError):
            # Release the owned process handle even if OS tree discovery is denied.
            # Still fail the cancellation: descendant termination is not proven.
            process.kill()
            process.wait(timeout=10)
            raise
    else:
        os.killpg(process.pid, signal.SIGKILL)
    process.wait(timeout=10)
