"""Inventory frozen golden bytes without granting certification or changing state."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


def git(*args: str) -> bytes:
    return subprocess.check_output(["git", *args], cwd=ROOT)


def inventory() -> dict:
    commit = git("rev-parse", "HEAD").decode().strip()
    paths = git("ls-files", "-z", "tests/goldens").decode().split("\0")
    paths += ["docs/pilots/kimodo-wave-left-v1.md"]
    rows = []
    for name in sorted(set(filter(None, paths))):
        path = (ROOT / name).resolve(strict=True)
        path.relative_to(ROOT)
        raw = path.read_bytes()
        committed = git("show", f"{commit}:{name}")
        rows.append({
            "path": name,
            "size_bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "committed_sha256": hashlib.sha256(committed).hexdigest(),
            "matches_committed_bytes": raw == committed,
        })
    return {
        "schema": "autospine.certification-baseline-inventory/v1",
        "commit": commit,
        "status": "inventory_only",
        "authority": "none",
        "scope": "tracked_goldens_and_pilot_identity_record",
        "files": rows,
        "limitations": [
            "Not a replay of local A/B current artifacts",
            "Not a new official Runtime capture or release approval",
            "Dirty runtime execution work is not certified by this inventory",
        ],
    }


if __name__ == "__main__":
    json.dump(inventory(), sys.stdout, ensure_ascii=False, indent=2)
    print()
