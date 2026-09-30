"""Disposable parent/child/grandchild test; never launches an engine or model."""
from pathlib import Path
import json
import subprocess
import sys
import time

from autospine_workbench.studio_process_lifetime import keep_owned_process_tree


if __name__ == '__main__':
    root = Path(sys.argv[1])
    owner = keep_owned_process_tree()
    if not owner.owns_windows_process_tree:
        raise RuntimeError('Windows lifetime test requires verified Job Object ownership')
    grandchild = "import time; time.sleep(60)"
    worker = (
        'from pathlib import Path; import os,json,subprocess,sys,time; '
        'child=subprocess.Popen([sys.executable,"-c",sys.argv[2]],close_fds=False); '
        'Path(sys.argv[1],"pids.json").write_text(json.dumps([os.getpid(),child.pid])); '
        '\nwhile True:\n'
        ' with Path(sys.argv[1],"heartbeat").open("a") as output: output.write("x"); output.flush()\n'
        ' time.sleep(.05)'
    )
    subprocess.Popen([sys.executable, '-c', worker, str(root), grandchild], close_fds=False)
    time.sleep(60)
