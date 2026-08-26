"""Read-only exact-address boundary for published P10 runtime captures."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import json
import os
from pathlib import Path
import stat
from typing import Any

from .body_sway_runtime_capture import BodySwayRuntimeCapture
from .body_sway_runtime_capture_bundle import (
    MANIFEST_NAME,
    BodySwayRuntimeCaptureBundleError,
    build_body_sway_runtime_capture_bundle,
)
from .body_sway_runtime_capture_collector import (
    MAX_CAPTURE_BYTES,
    MAX_CAPTURE_TOTAL_BYTES,
)
from .body_sway_runtime_capture_profile import (
    MAX_CAPTURE_ARTIFACTS,
    MAX_CAPTURE_DOCUMENT_BYTES,
)
from .body_sway_runtime_capture_store import NAMESPACE
from .body_sway_runtime_capture_validation import (
    BodySwayRuntimeCaptureValidationError,
    require_body_sway_runtime_capture,
)
from .manifest_artifacts import (
    LayerManifestError,
    require_safe_token,
    require_sha256,
)
from .safe_input_files import (
    SafeInputFileError,
    read_real_file,
    strict_json_object,
)
from .spine42_bundle_files import (
    Spine42BundleFilesError,
    existing_exact_child,
    is_alias,
    require_real_directory,
)


class VerifiedBodySwayRuntimeCaptureReaderError(RuntimeError):
    """Raised when an explicit runtime-capture address cannot be trusted."""


class VerifiedBodySwayRuntimeCaptureNotFound(
    VerifiedBodySwayRuntimeCaptureReaderError
):
    """Raised only when an exact capture path component does not exist."""


@dataclass(frozen=True, slots=True)
class VerifiedBodySwayRuntimeCapture:
    """One fully snapshotted and internally verified published capture."""

    path: Path
    capture: BodySwayRuntimeCapture
    bundle_sha256: str

    @property
    def project_id(self) -> str:
        return self.capture.document["project_id"]

    @property
    def temporary_preview_sha256(self) -> str:
        return self.capture.document["source"]["temporary_preview_sha256"]

    @property
    def artifact_set_sha256(self) -> str:
        return self.capture.artifact_set_sha256


@dataclass(frozen=True, slots=True)
class VerifiedBodySwayRuntimeCaptureReader:
    """Load one full address; never scan captures or consult a latest alias."""

    state_root: Path

    def __post_init__(self) -> None:
        object.__setattr__(self, "state_root", Path(self.state_root))

    def load(
        self,
        project_id: str,
        temporary_preview_sha256: str,
        bundle_sha256: str,
        artifact_set_sha256: str,
    ) -> VerifiedBodySwayRuntimeCapture:
        """Read all exact bytes once and verify their four-part address."""

        try:
            project = require_safe_token(project_id, "Runtime capture project id")
            preview_sha = require_sha256(
                temporary_preview_sha256, "Runtime capture preview digest"
            )
            bundle_sha = require_sha256(
                bundle_sha256, "Runtime capture bundle digest"
            )
            artifact_sha = require_sha256(
                artifact_set_sha256, "Runtime capture artifact-set digest"
            )
            directory = _exact_bundle_path(
                self.state_root, project, preview_sha, bundle_sha
            )
            manifest, capture_items = _snapshot(directory)
            document = strict_json_object(manifest, MANIFEST_NAME)
            captures = dict(capture_items)
            require_body_sway_runtime_capture(document, captures)
            canonical = _canonical(document)
            if canonical != manifest:
                raise VerifiedBodySwayRuntimeCaptureReaderError(
                    "Runtime capture manifest is not canonical JSON"
                )
            capture = BodySwayRuntimeCapture(
                canonical.decode("utf-8"), tuple(capture_items)
            )
            bundle = build_body_sway_runtime_capture_bundle(capture)
            if bundle.file_items != ((MANIFEST_NAME, manifest),) + capture_items:
                raise VerifiedBodySwayRuntimeCaptureReaderError(
                    "Runtime capture inventory order differs from its manifest"
                )
            actual_address = (
                bundle.project_id,
                bundle.temporary_preview_sha256,
                bundle.bundle_sha256,
                bundle.artifact_set_sha256,
            )
            if actual_address != (project, preview_sha, bundle_sha, artifact_sha):
                raise VerifiedBodySwayRuntimeCaptureReaderError(
                    "Runtime capture bytes differ from their full explicit address"
                )
            return VerifiedBodySwayRuntimeCapture(
                directory, capture, bundle.bundle_sha256
            )
        except VerifiedBodySwayRuntimeCaptureReaderError:
            raise
        except (
            BodySwayRuntimeCaptureBundleError,
            BodySwayRuntimeCaptureValidationError,
            LayerManifestError,
            SafeInputFileError,
            Spine42BundleFilesError,
            KeyError,
            OSError,
            RuntimeError,
            TypeError,
            UnicodeError,
            ValueError,
        ) as exc:
            raise VerifiedBodySwayRuntimeCaptureReaderError(
                f"Verified runtime capture load failed: {exc}"
            ) from exc


def _exact_bundle_path(
    state_root: Path, project: str, preview_sha: str, bundle_sha: str,
) -> Path:
    try:
        root = Path(os.path.abspath(os.fspath(Path(state_root))))
        try:
            root.lstat()
        except FileNotFoundError:
            raise VerifiedBodySwayRuntimeCaptureNotFound(
                "Exact runtime capture address does not exist"
            )
        current = require_real_directory(root, "Runtime capture state root")
        for name in (
            "builds", project, NAMESPACE, preview_sha, bundle_sha,
        ):
            child = existing_exact_child(current, name)
            if child is None:
                raise VerifiedBodySwayRuntimeCaptureNotFound(
                    "Exact runtime capture address does not exist"
                )
            current = require_real_directory(
                child, f"Runtime capture path {name}"
            )
        resolved_root = root.resolve(strict=True)
        resolved = current.resolve(strict=True)
        resolved.relative_to(resolved_root)
        if is_alias(current) or is_alias(resolved):
            raise VerifiedBodySwayRuntimeCaptureReaderError(
                "Runtime capture address is aliased"
            )
        return current
    except VerifiedBodySwayRuntimeCaptureReaderError:
        raise
    except (OSError, RuntimeError, ValueError) as exc:
        raise VerifiedBodySwayRuntimeCaptureReaderError(
            "Exact runtime capture address cannot be resolved"
        ) from exc


def _snapshot(directory: Path) -> tuple[bytes, tuple[tuple[str, bytes], ...]]:
    root = _exact_inventory(directory, {MANIFEST_NAME, "captures"})
    manifest = read_real_file(
        root[MANIFEST_NAME], MAX_CAPTURE_DOCUMENT_BYTES, MANIFEST_NAME
    )
    document = strict_json_object(manifest, MANIFEST_NAME)
    paths = _declared_paths(document)
    capture_root = require_real_directory(
        root["captures"], "Runtime capture PNG directory"
    )
    children = _exact_inventory(capture_root, {Path(path).name for path in paths})
    items = []
    total = 0
    for path in paths:
        payload = read_real_file(
            children[Path(path).name], MAX_CAPTURE_BYTES, path
        )
        total += len(payload)
        if total > MAX_CAPTURE_TOTAL_BYTES:
            raise VerifiedBodySwayRuntimeCaptureReaderError(
                "Runtime capture PNG total exceeds its limit"
            )
        items.append((path, payload))
    return manifest, tuple(items)


def _declared_paths(document: Mapping[str, Any]) -> tuple[str, ...]:
    try:
        files = document["artifacts"]["files"]
        if not isinstance(files, list) \
                or not 3 <= len(files) <= MAX_CAPTURE_ARTIFACTS:
            raise VerifiedBodySwayRuntimeCaptureReaderError(
                "Runtime capture declared inventory count is invalid"
            )
        paths = tuple(row["path"] for row in files)
        if any(
            type(path) is not str
            or not path.startswith("captures/")
            or path.count("/") != 1
            or "\\" in path
            or "\x00" in path
            or Path(path).name != path.removeprefix("captures/")
            for path in paths
        ) or len({path.casefold() for path in paths}) != len(paths):
            raise VerifiedBodySwayRuntimeCaptureReaderError(
                "Runtime capture declared inventory paths are unsafe"
            )
        return paths
    except VerifiedBodySwayRuntimeCaptureReaderError:
        raise
    except (KeyError, TypeError, ValueError) as exc:
        raise VerifiedBodySwayRuntimeCaptureReaderError(
            "Runtime capture declared inventory is malformed"
        ) from exc


def _exact_inventory(directory: Path, names: set[str]) -> dict[str, Path]:
    try:
        children = list(directory.iterdir())
        if len(children) != len(names) or {item.name for item in children} != names \
                or len({item.name.casefold() for item in children}) != len(children):
            raise VerifiedBodySwayRuntimeCaptureReaderError(
                "Runtime capture inventory is missing, extra, or wrong-case"
            )
        for item in children:
            mode = item.lstat().st_mode
            expected_directory = item.name == "captures"
            if is_alias(item) or (
                stat.S_ISDIR(mode) if expected_directory else stat.S_ISREG(mode)
            ) is not True:
                raise VerifiedBodySwayRuntimeCaptureReaderError(
                    "Runtime capture inventory contains an alias or wrong type"
                )
        return {item.name: item for item in children}
    except VerifiedBodySwayRuntimeCaptureReaderError:
        raise
    except OSError as exc:
        raise VerifiedBodySwayRuntimeCaptureReaderError(
            "Runtime capture inventory cannot be inspected"
        ) from exc


def _canonical(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
