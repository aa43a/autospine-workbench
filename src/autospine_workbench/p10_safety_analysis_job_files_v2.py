"""Alias-safe filesystem primitives for P10.4b v2 async jobs."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import stat
import tempfile

from .body_sway_visual_review_store_files import (
    BodySwayVisualReviewFilesError,
    exact_subdirectory,
)
from .safe_input_files import read_real_file, strict_json_object
from .spine42_bundle_files import (
    Spine42BundleFilesError, existing_exact_child,
    is_alias,
    require_real_directory,
    sync_directory,
)


NAMESPACE = "body-sway-safety-analysis-v2"
LATEST_NAMESPACE = "body-sway-safety-analysis-latest-v2"
MAX_EVENTS = 10_000
_EVENT = re.compile(r"^([0-9]{6})\.json$")
_SHA = re.compile(r"^[0-9a-f]{64}$")


class P10SafetyAnalysisJobFilesV2Error(RuntimeError):
    """Raised when an async-job filesystem address is unsafe."""


def normalized_state_root(value: Path) -> Path:
    try:
        return Path(os.path.abspath(os.fspath(value)))
    except (OSError, TypeError, ValueError) as exc:
        raise P10SafetyAnalysisJobFilesV2Error(
            "Safety analysis state root is invalid"
        ) from exc


def run_directory(state_root: Path, run_id: str, *, create: bool) -> Path:
    require_run_id(run_id)
    root = _directory(_safe_root(state_root), "jobs", create=create)
    namespace = _directory(root, NAMESPACE, create=create)
    return _directory(namespace, run_id, create=create)


def run_ids(state_root: Path) -> tuple[str, ...]:
    namespace = _directory(
        _directory(_safe_root(state_root), "jobs", create=True),
        NAMESPACE, create=True,
    )
    try:
        children = list(namespace.iterdir())
        if len(children) > 10_000:
            raise P10SafetyAnalysisJobFilesV2Error(
                "Safety analysis run inventory is excessive"
            )
        runs = [item for item in children if item.name != "latest"]
        legacy = [item for item in children if item.name == "latest"]
        if any(is_alias(item) or not stat.S_ISDIR(item.lstat().st_mode)
               for item in legacy) or any(
            _SHA.fullmatch(item.name) is None
            or is_alias(item)
            or not stat.S_ISDIR(item.lstat().st_mode)
            for item in runs
        ):
            raise P10SafetyAnalysisJobFilesV2Error(
                "Safety analysis run inventory is unsafe"
            )
        return tuple(sorted(item.name for item in runs))
    except OSError as exc:
        raise P10SafetyAnalysisJobFilesV2Error(
            "Safety analysis runs cannot be enumerated"
        ) from exc


def read_latest_index(state_root: Path, job_id: str):
    require_run_id(job_id)
    current = _safe_root(state_root)
    for name in ("jobs", LATEST_NAMESPACE):
        found = existing_exact_child(current, name)
        if found is None:
            return None
        try:
            current = require_real_directory(found, "Safety latest index")
        except Spine42BundleFilesError as exc:
            raise P10SafetyAnalysisJobFilesV2Error(
                "Safety latest index is unsafe"
            ) from exc
    found = existing_exact_child(current, f"{job_id}.json")
    if found is None:
        return None
    return read_json(found, 4096)


def replace_latest_index(state_root: Path, job_id: str, document) -> None:
    require_run_id(job_id)
    parent = _directory(
        _directory(
            _safe_root(state_root), "jobs", create=True,
        ), LATEST_NAMESPACE, create=True,
    )
    payload = _canonical(document).encode("utf-8")
    if not 0 < len(payload) <= 4096:
        raise P10SafetyAnalysisJobFilesV2Error(
            "Safety latest index is invalid"
        )
    temporary = None
    try:
        descriptor, raw_path = tempfile.mkstemp(
            prefix=".latest-", suffix=".tmp", dir=parent,
        )
        temporary = Path(raw_path)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        destination = parent / f"{job_id}.json"
        found = existing_exact_child(parent, destination.name)
        if found is not None and (
            is_alias(found) or not stat.S_ISREG(found.lstat().st_mode)
        ):
            raise P10SafetyAnalysisJobFilesV2Error(
                "Safety latest index destination is unsafe"
            )
        os.replace(temporary, destination)
        temporary = None
        sync_directory(parent)
        if read_json(destination, 4096) != document:
            raise P10SafetyAnalysisJobFilesV2Error(
                "Safety latest index readback differs"
            )
    except OSError as exc:
        raise P10SafetyAnalysisJobFilesV2Error(
            "Safety latest index cannot be replaced"
        ) from exc
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass


def event_inventory(directory: Path) -> tuple[tuple[int, Path], ...]:
    found: dict[int, Path] = {}
    try:
        children = list(directory.iterdir())
        if len(children) > MAX_EVENTS:
            raise P10SafetyAnalysisJobFilesV2Error(
                "Safety analysis event history is excessive"
            )
        for path in children:
            match = _EVENT.fullmatch(path.name)
            if match is None or is_alias(path) \
                    or not stat.S_ISREG(path.lstat().st_mode):
                raise P10SafetyAnalysisJobFilesV2Error(
                    "Safety analysis event inventory is unsafe"
                )
            found[int(match.group(1))] = path
    except OSError as exc:
        raise P10SafetyAnalysisJobFilesV2Error(
            "Safety analysis events cannot be enumerated"
        ) from exc
    if sorted(found) != list(range(1, len(found) + 1)):
        raise P10SafetyAnalysisJobFilesV2Error(
            "Safety analysis events are not contiguous"
        )
    return tuple(sorted(found.items()))


def exact_directory(parent: Path, name: str, *, create: bool) -> Path:
    return _directory(parent, name, create=create)


def publish_once(
    path: Path, payload: bytes, maximum: int = 128 * 1024,
) -> None:
    """Publish canonical JSON once under an artifact-specific byte limit."""

    if not 0 < len(payload) <= maximum:
        raise P10SafetyAnalysisJobFilesV2Error(
            "Safety analysis document size is invalid"
        )
    try:
        strict_json_object(payload, "Safety analysis document")
        if _canonical(json.loads(payload)).encode("utf-8") != payload:
            raise ValueError("canonical")
        found = existing_exact_child(path.parent, path.name)
        if found is not None:
            if is_alias(found) or not stat.S_ISREG(found.lstat().st_mode) \
                    or read_real_file(found, maximum, path.name) != payload:
                raise ValueError("existing")
            return
        descriptor, raw_path = tempfile.mkstemp(
            prefix=".safety-", suffix=".tmp", dir=path.parent,
        )
        temporary = Path(raw_path)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.link(temporary, path)
                sync_directory(path.parent)
            except FileExistsError:
                pass
            found = existing_exact_child(path.parent, path.name)
            if found is None or is_alias(found) \
                    or not stat.S_ISREG(found.lstat().st_mode) \
                    or read_real_file(found, maximum, path.name) != payload:
                raise ValueError("readback")
        finally:
            temporary.unlink(missing_ok=True)
    except (OSError, UnicodeError, ValueError) as exc:
        raise P10SafetyAnalysisJobFilesV2Error(
            "Safety analysis file cannot be published"
        ) from exc


def read_json(path: Path, maximum: int):
    try:
        found = existing_exact_child(path.parent, path.name)
        if found is None or is_alias(found) \
                or not stat.S_ISREG(found.lstat().st_mode):
            raise ValueError("address")
        raw = read_real_file(found, maximum, path.name)
        if not 0 < len(raw) <= maximum:
            raise ValueError("size")
        value = strict_json_object(raw, "Safety analysis document")
        if not isinstance(value, dict) \
                or _canonical(value).encode("utf-8") != raw:
            raise ValueError("canonical")
        return value
    except (
        OSError,
        UnicodeError,
        ValueError,
        json.JSONDecodeError,
    ) as exc:
        raise P10SafetyAnalysisJobFilesV2Error(
            "Safety analysis file is unsafe"
        ) from exc


def require_run_id(value: str) -> None:
    if type(value) is not str or _SHA.fullmatch(value) is None:
        raise P10SafetyAnalysisJobFilesV2Error(
            "Safety analysis run id is invalid"
        )


def _safe_root(path: Path) -> Path:
    try:
        return require_real_directory(path, "Safety analysis state root")
    except Spine42BundleFilesError as exc:
        raise P10SafetyAnalysisJobFilesV2Error(
            "Safety analysis state root is unsafe"
        ) from exc


def _directory(parent: Path, name: str, *, create: bool) -> Path:
    try:
        return exact_subdirectory(parent, name, create=create)
    except BodySwayVisualReviewFilesError as exc:
        raise P10SafetyAnalysisJobFilesV2Error(
            "Safety analysis directory is unsafe"
        ) from exc


def _canonical(value) -> str:
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    )


__all__ = [
    "P10SafetyAnalysisJobFilesV2Error", "event_inventory",
    "exact_directory", "normalized_state_root", "publish_once",
    "read_json", "read_latest_index", "replace_latest_index",
    "require_run_id", "run_directory", "run_ids",
]
