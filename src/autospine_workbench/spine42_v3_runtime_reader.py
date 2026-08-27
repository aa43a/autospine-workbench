"""Read-once exact-address reader for P10.7b runtime evidence."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import stat

from .manifest_artifacts import (
    LayerManifestError,
    require_safe_token,
    require_sha256,
)
from .motion_instance_v3_staging_cleanup import is_alias
from .safe_input_files import SafeInputFileError, read_real_file
from .spine42_v3_bundle_files import (
    Spine42V3BundleFilesError,
    existing_exact_child,
    require_real_directory,
)
from .spine42_v3_runtime_bundle import (
    NAMESPACE,
    Spine42V3RuntimeBundle,
    Spine42V3RuntimeBundleError,
    build_spine42_v3_runtime_bundle,
    replay_runtime_evidence,
)
from .spine42_v3_runtime_evidence import (
    MANIFEST_NAME,
    MAX_CAPTURE_BYTES,
    MAX_CAPTURE_TOTAL_BYTES,
    MAX_MANIFEST_BYTES,
    MAX_METRICS_BYTES,
    METRICS_NAME,
    Spine42V3RuntimeEvidence,
    Spine42V3RuntimeEvidenceError,
)
from .spine42_v3_runtime_profile import MAX_CAPTURE_ARTIFACTS


class Spine42V3RuntimeReaderError(RuntimeError):
    """Raised when an exact runtime evidence address is not trustworthy."""


class Spine42V3RuntimeNotFound(Spine42V3RuntimeReaderError):
    """Raised only when a valid exact address component is absent."""


@dataclass(frozen=True, slots=True)
class VerifiedSpine42V3RuntimeEvidence:
    path: Path
    evidence: Spine42V3RuntimeEvidence
    bundle: Spine42V3RuntimeBundle

    @property
    def project_id(self) -> str:
        return self.bundle.project_id

    @property
    def spine42_v3_bundle_sha256(self) -> str:
        return self.bundle.spine42_v3_bundle_sha256

    @property
    def capture_bundle_sha256(self) -> str:
        return self.bundle.bundle_sha256


@dataclass(frozen=True, slots=True)
class VerifiedSpine42V3RuntimeReader:
    """Load one full address without scanning siblings or mutable heads."""

    state_root: Path

    def __post_init__(self) -> None:
        object.__setattr__(self, "state_root", Path(self.state_root))

    def load(
        self, project_id: str, spine42_v3_bundle_sha256: str,
        capture_bundle_sha256: str,
    ) -> VerifiedSpine42V3RuntimeEvidence:
        """Read every declared file once and replay all structure and bytes."""

        try:
            project = require_safe_token(project_id, "Runtime project id")
            upstream = require_sha256(
                spine42_v3_bundle_sha256, "Spine v3 bundle digest"
            )
            capture = require_sha256(
                capture_bundle_sha256, "Runtime capture bundle digest"
            )
            directory = _exact_bundle_path(
                self.state_root, project, upstream, capture
            )
            verified = snapshot_spine42_v3_runtime_directory(directory)
            actual = (
                verified.project_id, verified.spine42_v3_bundle_sha256,
                verified.capture_bundle_sha256,
            )
            if actual != (project, upstream, capture):
                raise Spine42V3RuntimeReaderError(
                    "Runtime evidence differs from its explicit address"
                )
            return verified
        except Spine42V3RuntimeReaderError:
            raise
        except (
            LayerManifestError, OSError, RuntimeError,
            Spine42V3BundleFilesError, TypeError, ValueError,
        ) as exc:
            raise Spine42V3RuntimeReaderError(
                f"Verified runtime evidence load failed: {exc}"
            ) from exc


def snapshot_spine42_v3_runtime_directory(
    directory: Path, *, require_address: bool = True,
) -> VerifiedSpine42V3RuntimeEvidence:
    """Snapshot the fixed inventory once, then replay it in memory."""

    try:
        root = _real_directory_tree(directory, "Runtime evidence directory")
        entries = _inventory(root, {MANIFEST_NAME, METRICS_NAME, "captures"})
        manifest_bytes = read_real_file(
            entries[MANIFEST_NAME], MAX_MANIFEST_BYTES, MANIFEST_NAME
        )
        artifacts = _declared_artifacts(manifest_bytes)
        metrics_bytes = read_real_file(
            entries[METRICS_NAME], MAX_METRICS_BYTES, METRICS_NAME
        )
        captures_root = require_real_directory(
            entries["captures"], "Runtime evidence captures"
        )
        names = {Path(row["stored_path"]).name for row in artifacts}
        captures = _inventory(captures_root, names)
        items, total = [], 0
        for row in artifacts:
            path = row["stored_path"]
            raw = read_real_file(
                captures[Path(path).name], MAX_CAPTURE_BYTES, path
            )
            total += len(raw)
            if total > MAX_CAPTURE_TOTAL_BYTES:
                raise Spine42V3RuntimeReaderError(
                    "Runtime capture PNG total exceeds its limit"
                )
            items.append((row["artifact_id"], raw))
        evidence = replay_runtime_evidence(
            manifest_bytes, metrics_bytes, tuple(items)
        )
        bundle = build_spine42_v3_runtime_bundle(evidence)
        if require_address:
            _require_address(root, bundle)
        return VerifiedSpine42V3RuntimeEvidence(root, evidence, bundle)
    except Spine42V3RuntimeReaderError:
        raise
    except (
        OSError, RuntimeError, SafeInputFileError,
        Spine42V3BundleFilesError, Spine42V3RuntimeBundleError,
        Spine42V3RuntimeEvidenceError, TypeError, ValueError,
    ) as exc:
        raise Spine42V3RuntimeReaderError(
            f"Runtime evidence snapshot failed: {exc}"
        ) from exc


def _exact_bundle_path(root, project, upstream, capture) -> Path:
    try:
        absolute = Path(os.path.abspath(os.fspath(Path(root))))
        try:
            absolute.lstat()
        except FileNotFoundError:
            raise Spine42V3RuntimeNotFound(
                "Exact runtime evidence address does not exist"
            )
        current = _real_directory_tree(absolute, "Runtime evidence state root")
        for name in ("builds", project, NAMESPACE, upstream, capture):
            child = existing_exact_child(current, name)
            if child is None:
                raise Spine42V3RuntimeNotFound(
                    "Exact runtime evidence address does not exist"
                )
            current = require_real_directory(
                child, f"Runtime evidence path {name}"
            )
        current.resolve(strict=True).relative_to(absolute.resolve(strict=True))
        return current
    except Spine42V3RuntimeReaderError:
        raise
    except (OSError, RuntimeError, ValueError) as exc:
        raise Spine42V3RuntimeReaderError(
            "Exact runtime evidence address cannot be resolved"
        ) from exc


def _declared_artifacts(raw: bytes) -> list[dict]:
    try:
        value = json.loads(raw)
        rows = value["artifacts"]
        fields = {
            "artifact_id", "logical_path", "stored_path", "kind", "case_id",
            "sha256", "size_bytes",
        }
        if type(rows) is not list or not 1 <= len(rows) <= MAX_CAPTURE_ARTIFACTS:
            raise Spine42V3RuntimeReaderError(
                "Declared runtime capture count is invalid"
            )
        for row in rows:
            logical = row.get("logical_path") if type(row) is dict else None
            if type(row) is not dict or set(row) != fields \
                    or not _safe_basename(logical) \
                    or row.get("stored_path") != f"captures/{logical}" \
                    or type(row.get("artifact_id")) is not str:
                raise Spine42V3RuntimeReaderError(
                    "Declared runtime capture path is unsafe"
                )
        for field in ("artifact_id", "logical_path", "stored_path"):
            values = [row[field].casefold() for row in rows]
            if len(values) != len(set(values)):
                raise Spine42V3RuntimeReaderError(
                    "Declared runtime captures contain an alias"
                )
        return rows
    except Spine42V3RuntimeReaderError:
        raise
    except (KeyError, TypeError, ValueError) as exc:
        raise Spine42V3RuntimeReaderError(
            "Declared runtime capture inventory is malformed"
        ) from exc


def _inventory(directory: Path, names: set[str]) -> dict[str, Path]:
    try:
        children = list(directory.iterdir())
        actual = {item.name for item in children}
        if len(children) != len(names) or actual != names \
                or len({name.casefold() for name in actual}) != len(actual):
            raise Spine42V3RuntimeReaderError(
                "Runtime inventory is missing, extra, or wrong-case"
            )
        for item in children:
            mode = item.lstat().st_mode
            directory_expected = item.name == "captures"
            valid = stat.S_ISDIR(mode) if directory_expected else stat.S_ISREG(mode)
            if is_alias(item) or valid is not True:
                raise Spine42V3RuntimeReaderError(
                    "Runtime inventory contains an alias or wrong type"
                )
        return {item.name: item for item in children}
    except Spine42V3RuntimeReaderError:
        raise
    except OSError as exc:
        raise Spine42V3RuntimeReaderError(
            "Runtime evidence inventory cannot be inspected"
        ) from exc


def _require_address(path, bundle) -> None:
    parts = tuple(path.parents[index].name for index in range(4))
    if (path.name, *parts) != (
        bundle.bundle_sha256, bundle.spine42_v3_bundle_sha256,
        NAMESPACE, bundle.project_id, "builds",
    ):
        raise Spine42V3RuntimeReaderError(
            "Runtime evidence content-address path is invalid"
        )


def _real_directory_tree(value, label) -> Path:
    try:
        absolute = Path(os.path.abspath(os.fspath(Path(value))))
        for candidate in (absolute, *absolute.parents):
            require_real_directory(candidate, label)
        return absolute
    except (OSError, RuntimeError, Spine42V3BundleFilesError) as exc:
        raise Spine42V3RuntimeReaderError(
            f"{label} or one of its ancestors is unsafe"
        ) from exc


def _safe_basename(value) -> bool:
    return type(value) is str and Path(value).name == value \
        and value.endswith(".png") and "\\" not in value and "\x00" not in value


__all__ = [
    "Spine42V3RuntimeNotFound", "Spine42V3RuntimeReaderError",
    "VerifiedSpine42V3RuntimeEvidence", "VerifiedSpine42V3RuntimeReader",
    "snapshot_spine42_v3_runtime_directory",
]
