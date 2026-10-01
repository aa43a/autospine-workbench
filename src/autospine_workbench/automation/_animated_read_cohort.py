"""Share only a cohort admitted before its complete candidate byte verification.

Completed values are never registered for reuse. Limits bound active verification
and coordination, not caller-owned response bytes after read() has returned.
"""
from concurrent.futures import Future
from copy import copy
from dataclasses import dataclass, field
from hashlib import sha256
import os
from pathlib import PurePosixPath
import stat
from threading import Condition, local
from types import MappingProxyType

from ..manifest_artifacts import require_sha256
from ..resolved_project import canonical_sha256
from ..safe_input_files import read_real_file
from ..spine42_v3_bundle_files import is_alias
from .animated_jobs import safe_file
from .pipeline_run import PipelineRunError
from .storage_io import canonical_bytes, directory, read_document


def _invalid():
    return PipelineRunError("pipeline_artifact_invalid")


def _failure_copy(error):
    try:
        return copy(error)
    except BaseException:
        return PipelineRunError(getattr(error, "reason_code", "animated_read_failed"))


def _metadata(path, *, file):
    info = path.lstat()
    if is_alias(path) or (file and (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1)) \
            or (not file and not stat.S_ISDIR(info.st_mode)):
        raise _invalid()
    return (info.st_dev, info.st_ino, info.st_mode, info.st_nlink,
            info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _tree(folder, inventory):
    expected = set(inventory) | {"inventory.json"}
    allowed = {"staging"}
    for name in inventory:
        allowed.update(str(parent) for parent in PurePosixPath(name).parents if str(parent) != ".")
    snapshots, found = {}, set()

    def walk(current, prefix=""):
        snapshots[prefix] = _metadata(current, file=False)
        folded = set()
        for child in current.iterdir():
            name = prefix + child.name
            if child.name.casefold() in folded or is_alias(child):
                raise _invalid()
            folded.add(child.name.casefold())
            if name in expected:
                snapshots[name] = _metadata(child, file=True)
                found.add(name)
            elif name in allowed:
                walk(child, name + "/")
            else:
                raise _invalid()

    walk(folder)
    if found != expected:
        raise _invalid()
    return snapshots


@dataclass(frozen=True)
class _Plan:
    inventory: dict
    manifest: bytes
    snapshots: dict


def prepare(folder, digest, max_file, max_total):
    """All cohort members validate paths, manifest and byte limits before sealing."""
    inventory = read_document(folder / "inventory.json")
    if canonical_sha256(inventory) != digest or not 0 < len(inventory) <= 1024:
        raise _invalid()
    folded = set()
    for name, expected in inventory.items():
        safe_file(name)
        require_sha256(expected, "Animated file")
        if name.casefold() in folded:
            raise _invalid()
        folded.add(name.casefold())
        directory((folder / name).parent)
    snapshots = _tree(folder, inventory)
    sizes = [snapshots[name][4] for name in inventory]
    if any(size > max_file for size in sizes) or sum(sizes) > max_total:
        raise PipelineRunError("animated_resource_limit")
    return _Plan(inventory, canonical_bytes(inventory), snapshots)


def verify(folder, digest, plan, max_file, max_total):
    """Hash every declared file, including images unused by the current atlas."""
    files, size = {}, 0
    for name, expected in plan.inventory.items():
        if _metadata(folder / name, file=True) != plan.snapshots[name]:
            raise _invalid()
        raw = read_real_file(folder / name, max_file, "animated bundle")
        size += len(raw)
        if type(raw) is not bytes or sha256(raw).hexdigest() != expected or size > max_total:
            raise _invalid()
        files[name] = raw
    inventory = read_document(folder / "inventory.json")
    if canonical_sha256(inventory) != digest or canonical_bytes(inventory) != plan.manifest \
            or _tree(folder, inventory) != plan.snapshots:
        raise _invalid()
    return files


@dataclass
class _Flight:
    future: Future = field(default_factory=Future)
    members: int = 1
    prepared: int = 0
    plans: list = field(default_factory=list)
    errors: list = field(default_factory=list)


class ReadCohorts:
    def __init__(self, *, max_flights=2, max_members=16, max_bytes=640 << 20):
        if any(type(value) is not int or value < 1 for value in (max_flights, max_members, max_bytes)):
            raise ValueError("animated_read_cohort_budget")
        self.max_flights, self.max_members, self.max_bytes = max_flights, max_members, max_bytes
        self._condition, self._local = Condition(), local()
        self._preparing, self._active, self._bytes = {}, 0, 0

    def read(self, key, prepare_read, verify_read, *, reservation):
        # Never wait on a Future owned by this thread, including nested publish.
        if getattr(self._local, "reading", False):
            raise PipelineRunError("animated_read_reentrant")
        if type(reservation) is not int or not 0 < reservation <= self.max_bytes:
            raise PipelineRunError("animated_resource_limit")
        self._local.reading = True
        try:
            return self._read(key, prepare_read, verify_read, reservation)
        finally:
            self._local.reading = False

    def _read(self, key, prepare_read, verify_read, reservation):
        with self._condition:
            while True:
                flight = self._preparing.get(key)
                if flight is not None and flight.members < self.max_members:
                    flight.members += 1
                    leader = False
                    break
                if flight is None and self._active < self.max_flights \
                        and self._bytes + reservation <= self.max_bytes:
                    flight = _Flight()
                    self._preparing[key] = flight
                    self._active += 1
                    self._bytes += reservation
                    leader = True
                    break
                self._condition.wait()

        plan, error = None, None
        try:
            plan = prepare_read()
        except BaseException as exc:
            error = _failure_copy(exc)
        with self._condition:
            flight.prepared += 1
            if error is None:
                flight.plans.append(plan)
            else:
                flight.errors.append(error)
            self._condition.notify_all()
            if leader:
                # Seal before any candidate content byte. Late callers form a new
                # cohort; no completed or partially verified flight is joinable.
                if self._preparing.get(key) is flight:
                    del self._preparing[key]
                self._condition.notify_all()
                try:
                    while flight.prepared != flight.members:
                        self._condition.wait()
                except BaseException as exc:
                    error = _failure_copy(exc)

        if leader:
            outcome = None
            try:
                if error is not None:
                    raise error
                if flight.errors:
                    raise flight.errors[0]
                if any(candidate != plan for candidate in flight.plans):
                    raise _invalid()
                outcome = MappingProxyType(verify_read(plan))
            except BaseException as exc:
                error = _failure_copy(exc)
            finally:
                with self._condition:
                    self._active -= 1
                    self._bytes -= reservation
                    self._condition.notify_all()
                # Result bytes belong only to already-admitted request stacks.
                flight.future.set_result((outcome, error))
        files, failure = flight.future.result()
        if failure is not None:
            raise _failure_copy(failure)
        return dict(files)


_COHORTS = ReadCohorts()


def read_verified(folder, digest, *, max_file, max_total):
    key = (os.path.normcase(str(folder.parent.resolve(strict=True))), digest, max_file, max_total)
    return _COHORTS.read(key,
        lambda: prepare(folder, digest, max_file, max_total),
        lambda plan: verify(folder, digest, plan, max_file, max_total),
        reservation=max_total + max_file)
