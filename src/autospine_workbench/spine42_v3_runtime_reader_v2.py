"""Read-once exact-address reader for P10.7b v2 runtime evidence."""

from __future__ import annotations

from dataclasses import InitVar, dataclass
import os
from pathlib import Path
import stat
import threading
from weakref import WeakKeyDictionary

from .manifest_artifacts import LayerManifestError, require_safe_token, require_sha256
from .motion_instance_v3_staging_cleanup import is_alias
from .safe_input_files import SafeInputFileError, read_real_file
from .spine42_v3_bundle_files import (
    Spine42V3BundleFilesError, existing_exact_child, require_real_directory)
from .spine42_v3_bundle_reader_v2 import (
    VerifiedSpine42V3BundleReaderV2, VerifiedSpine42V3BundleReaderV2Error,
    VerifiedSpine42V3BundleV2)
from .spine42_v3_runtime_bundle_v2 import (
    NAMESPACE, Spine42V3RuntimeBundleV2, Spine42V3RuntimeBundleV2Error,
    replay_spine42_v3_runtime_bundle_v2)
from .spine42_v3_runtime_capture_core import MAX_CAPTURE_BYTES, MAX_CAPTURE_TOTAL_BYTES
from .spine42_v3_runtime_evidence_contract_v2 import FIXED_NAMES, MANIFEST_NAME
from .spine42_v3_runtime_evidence_v2 import MAX_JSON_BYTES
from .spine42_v3_runtime_inventory_v2 import declared_artifacts

class Spine42V3RuntimeReaderV2Error(RuntimeError):
    """Raised when an exact v2 runtime address is not trustworthy."""

class Spine42V3RuntimeV2NotFound(Spine42V3RuntimeReaderV2Error):
    """Raised only when a valid explicit address component is absent."""

def _runtime_reader_capability():
    receipt, issued, lock = object(), WeakKeyDictionary(), threading.Lock()

    @dataclass(frozen=True, slots=True, eq=False, weakref_slot=True)
    class VerifiedSpine42V3RuntimeEvidenceV2:
        path: Path
        bundle: Spine42V3RuntimeBundleV2
        _receipt: InitVar[object] = None

        def __post_init__(self, _receipt: object) -> None:
            if _receipt is not receipt:
                raise Spine42V3RuntimeReaderV2Error(
                    "Verified runtime evidence v2 is reader-issued only"
                )

    def issue(path, bundle):
        value = VerifiedSpine42V3RuntimeEvidenceV2(path, bundle, receipt)
        with lock:
            issued[value] = (path, bundle, _bundle_state(bundle))
        return value

    def require(value):
        if type(value) is not VerifiedSpine42V3RuntimeEvidenceV2:
            raise Spine42V3RuntimeReaderV2Error(
                "Runtime v2 is not reader-issued"
            )
        with lock:
            recorded = issued.get(value)
        if recorded is None:
            raise Spine42V3RuntimeReaderV2Error(
                "Runtime v2 is not reader-issued"
            )
        path, bundle, state = recorded
        if value.path != path or value.bundle is not bundle \
                or _bundle_state(value.bundle) != state:
            raise Spine42V3RuntimeReaderV2Error(
                "Issued runtime v2 changed"
            )
        _require_address(path, bundle)
        return path, bundle

    @dataclass(frozen=True, slots=True)
    class VerifiedSpine42V3RuntimeReaderV2:
        """Load one four-part address without observing mutable heads."""

        state_root: Path

        def __post_init__(self) -> None:
            object.__setattr__(self, "state_root", Path(self.state_root))

        def load(
            self, project_id: str, skeleton_json_sha256: str,
            spine42_v3_bundle_sha256: str, capture_bundle_sha256: str,
        ) -> VerifiedSpine42V3RuntimeEvidenceV2:
            """Read the upstream, then every declared runtime file once."""
            try:
                address = _address(
                    project_id, skeleton_json_sha256,
                    spine42_v3_bundle_sha256, capture_bundle_sha256,
                )
                project, skeleton, upstream_sha, _capture_sha = address
                upstream = VerifiedSpine42V3BundleReaderV2(
                    self.state_root
                ).load(project, skeleton, upstream_sha)
                directory = _exact_bundle_path(self.state_root, *address)
                bundle = _snapshot_spine42_v3_runtime_bundle_v2(
                    directory, upstream, require_address=True,
                )
                actual = (
                    bundle.project_id, bundle.skeleton_json_sha256,
                    bundle.spine42_v3_bundle_sha256, bundle.bundle_sha256,
                )
                if actual != address:
                    raise Spine42V3RuntimeReaderV2Error(
                        "Runtime evidence v2 differs from its explicit address"
                    )
                return issue(directory, bundle)
            except Spine42V3RuntimeReaderV2Error:
                raise
            except _FAILURES as exc:
                raise Spine42V3RuntimeReaderV2Error(
                    "Verified runtime evidence v2 load failed"
                ) from exc

    def snapshot(directory, upstream):
        """Issue only after replaying a strict content-addressed directory."""
        root = Path(os.path.abspath(os.fspath(Path(directory))))
        bundle = _snapshot_spine42_v3_runtime_bundle_v2(
            root, upstream, require_address=True,
        )
        return issue(root, bundle)

    return VerifiedSpine42V3RuntimeEvidenceV2, \
        VerifiedSpine42V3RuntimeReaderV2, snapshot, require


def _bundle_state(bundle):
    fields = (
        bundle.project_id, bundle.clip_id, bundle.skeleton_json_sha256,
        bundle.spine42_v3_bundle_sha256, bundle.evidence_sha256,
        bundle.bundle_sha256,
    )
    items = tuple((type(name), name, type(raw), raw)
                  for name, raw in bundle.file_items)
    return tuple((type(value), value) for value in fields) + items


(
    VerifiedSpine42V3RuntimeEvidenceV2,
    VerifiedSpine42V3RuntimeReaderV2,
    snapshot_spine42_v3_runtime_directory_v2,
    _require_issued_spine42_v3_runtime_reader_v2,
) = _runtime_reader_capability()

def _snapshot_spine42_v3_runtime_bundle_v2(
    directory: Path, upstream: VerifiedSpine42V3BundleV2, *,
    require_address: bool,
) -> Spine42V3RuntimeBundleV2:
    """Replay strict disk bytes without minting reader authority."""
    try:
        if type(upstream) is not VerifiedSpine42V3BundleV2:
            raise Spine42V3RuntimeReaderV2Error(
                "Runtime snapshot v2 requires reader-issued P10.7a input")
        root = _real_directory_tree(directory, "Runtime evidence v2 directory")
        entries = _inventory(root, set(FIXED_NAMES) | {"captures"}, True)
        manifest = read_real_file(
            entries[MANIFEST_NAME], MAX_JSON_BYTES, MANIFEST_NAME,
        )
        rows = _declared_artifacts(manifest)
        fixed = [(MANIFEST_NAME, manifest)]
        fixed.extend((name, read_real_file(entries[name], MAX_JSON_BYTES, name))
                     for name in FIXED_NAMES[1:])
        captures_root = require_real_directory(
            entries["captures"], "Runtime evidence v2 captures",
        )
        names = {row["logical_path"] for row in rows}
        capture_files = _inventory(captures_root, names, False)
        captures, total = [], 0
        for row in rows:
            raw = read_real_file(
                capture_files[row["logical_path"]], MAX_CAPTURE_BYTES,
                row["stored_path"],
            )
            total += len(raw)
            if total > MAX_CAPTURE_TOTAL_BYTES:
                raise Spine42V3RuntimeReaderV2Error(
                    "Runtime capture v2 total exceeds its limit")
            captures.append((row["stored_path"], raw))
        bundle = replay_spine42_v3_runtime_bundle_v2(
            upstream, tuple(fixed + captures))
        if require_address:
            _require_address(root, bundle)
        return bundle
    except Spine42V3RuntimeReaderV2Error:
        raise
    except _FAILURES as exc:
        raise Spine42V3RuntimeReaderV2Error(
            "Runtime evidence v2 snapshot failed") from exc

def _address(project, skeleton, upstream, capture):
    try:
        return (
            require_safe_token(project, "Runtime v2 project id"),
            require_sha256(skeleton, "Runtime v2 skeleton"),
            require_sha256(upstream, "Runtime v2 P10.7a bundle"),
            require_sha256(capture, "Runtime v2 capture bundle"),
        )
    except LayerManifestError as exc:
        raise Spine42V3RuntimeReaderV2Error(
            "Runtime evidence v2 address is invalid") from exc

def _exact_bundle_path(root, project, skeleton, upstream, capture):
    try:
        base = Path(os.path.abspath(os.fspath(Path(root))))
        current = _real_directory_tree(base, "Runtime evidence v2 state root")
        for name in (
            "builds", project, NAMESPACE, skeleton, upstream, capture,
        ):
            child = existing_exact_child(current, name)
            if child is None:
                raise Spine42V3RuntimeV2NotFound(
                    "Exact runtime evidence v2 address does not exist")
            current = require_real_directory(
                child, f"Runtime evidence v2 path {name}",
            )
        current.resolve(strict=True).relative_to(base.resolve(strict=True))
        return current
    except Spine42V3RuntimeReaderV2Error:
        raise
    except (OSError, RuntimeError, ValueError) as exc:
        raise Spine42V3RuntimeReaderV2Error(
            "Exact runtime evidence v2 address cannot be resolved") from exc

def _declared_artifacts(raw):
    return declared_artifacts(raw, Spine42V3RuntimeReaderV2Error)


def _inventory(directory, names, root_inventory):
    try:
        children = list(directory.iterdir())
        actual = {item.name for item in children}
        if len(children) != len(names) or actual != names \
                or len({name.casefold() for name in actual}) != len(actual):
            raise Spine42V3RuntimeReaderV2Error(
                "Runtime inventory v2 is missing, extra, or wrong-case")
        for item in children:
            directory_expected = root_inventory and item.name == "captures"
            mode = item.lstat().st_mode
            valid = stat.S_ISDIR(mode) if directory_expected else stat.S_ISREG(mode)
            if is_alias(item) or valid is not True:
                raise Spine42V3RuntimeReaderV2Error(
                    "Runtime inventory v2 contains an alias or wrong type")
        return {item.name: item for item in children}
    except Spine42V3RuntimeReaderV2Error:
        raise
    except OSError as exc:
        raise Spine42V3RuntimeReaderV2Error(
            "Runtime evidence v2 inventory cannot be inspected") from exc

def _require_address(path, bundle):
    parents = tuple(path.parents[index].name for index in range(5))
    if (path.name, *parents) != (
        bundle.bundle_sha256, bundle.spine42_v3_bundle_sha256,
        bundle.skeleton_json_sha256, NAMESPACE, bundle.project_id, "builds",
    ):
        raise Spine42V3RuntimeReaderV2Error(
            "Runtime evidence v2 content-address path is invalid")

def _real_directory_tree(value, label):
    try:
        absolute = Path(os.path.abspath(os.fspath(Path(value))))
        try:
            absolute.lstat()
        except FileNotFoundError as exc:
            raise Spine42V3RuntimeV2NotFound(
                "Runtime evidence v2 is absent") from exc
        for candidate in (absolute, *absolute.parents):
            require_real_directory(candidate, label)
        return absolute
    except Spine42V3RuntimeReaderV2Error:
        raise
    except (OSError, RuntimeError, Spine42V3BundleFilesError) as exc:
        raise Spine42V3RuntimeReaderV2Error(
            f"{label} ancestry is unsafe") from exc

_FAILURES = (
    LayerManifestError, OSError, RuntimeError, SafeInputFileError,
    Spine42V3BundleFilesError, Spine42V3RuntimeBundleV2Error,
    TypeError, ValueError, VerifiedSpine42V3BundleReaderV2Error,
)
__all__ = [
    "Spine42V3RuntimeReaderV2Error", "Spine42V3RuntimeV2NotFound",
    "VerifiedSpine42V3RuntimeEvidenceV2", "VerifiedSpine42V3RuntimeReaderV2",
    "snapshot_spine42_v3_runtime_directory_v2",
]
