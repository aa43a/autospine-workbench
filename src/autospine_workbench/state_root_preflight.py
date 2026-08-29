"""Active startup checks for the filesystem primitives used by mutations."""

from __future__ import annotations

import os
from pathlib import Path
import secrets
import stat


class StateRootMutationUnavailable(RuntimeError):
    """Raised when the local state root cannot publish immutable artifacts."""


def preflight_state_root_mutations(
    state_root: Path, project_ids: tuple[str, ...] = (),
) -> None:
    """Exercise mkdir, durable write, hard-link, readback, and cleanup.

    ``os.access`` is intentionally insufficient on Windows and in restricted
    launch environments.  Probe the root plus every existing per-project build
    directory because either level may have a different effective ACL.
    """

    try:
        root = Path(state_root).expanduser().resolve()
        root.mkdir(parents=True, exist_ok=True)
        _require_real_directory(root)
        targets = [root]
        builds = root / "builds"
        if builds.exists():
            _require_real_directory(builds)
            for project_id in project_ids:
                target = builds / project_id
                if target.exists():
                    _require_real_directory(target)
                    targets.append(target)
        for target in targets:
            _probe_publication_primitives(target)
    except StateRootMutationUnavailable:
        raise
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        raise StateRootMutationUnavailable(
            "State-root mutation primitives are unavailable"
        ) from exc


def _probe_publication_primitives(parent: Path) -> None:
    token = secrets.token_hex(16)
    probe = parent / f".autospine-write-preflight-{token}"
    source = probe / "source.tmp"
    linked = probe / "linked.tmp"
    created = False
    failure: BaseException | None = None
    try:
        os.mkdir(probe)
        created = True
        payload = b"autospine-state-root-preflight-v1\n"
        with source.open("xb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.link(source, linked)
        if linked.read_bytes() != payload:
            raise StateRootMutationUnavailable(
                "State-root publication readback failed"
            )
    except (OSError, RuntimeError, ValueError) as exc:
        failure = exc
    cleanup_error = _remove_probe(probe, source, linked, created)
    if failure is not None or cleanup_error is not None:
        raise StateRootMutationUnavailable(
            "State-root publication probe failed"
        ) from (failure or cleanup_error)


def _remove_probe(
    probe: Path, source: Path, linked: Path, created: bool,
) -> OSError | None:
    if not created:
        return None
    try:
        linked.unlink(missing_ok=True)
        source.unlink(missing_ok=True)
        probe.rmdir()
        return None
    except OSError as exc:
        return exc


def _require_real_directory(path: Path) -> None:
    try:
        info = path.lstat()
        junction = getattr(path, "is_junction", None)
        if stat.S_ISLNK(info.st_mode) \
                or callable(junction) and junction() \
                or not stat.S_ISDIR(info.st_mode):
            raise StateRootMutationUnavailable(
                "State-root preflight target is not a real directory"
            )
    except StateRootMutationUnavailable:
        raise
    except OSError as exc:
        raise StateRootMutationUnavailable(
            "State-root preflight target cannot be inspected"
        ) from exc
