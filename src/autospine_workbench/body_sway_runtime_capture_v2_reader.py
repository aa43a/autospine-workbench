"""Read-only exact-address boundary for published RuntimeCapture v2 bundles."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import json
import os
from pathlib import Path
import stat

from .body_sway_runtime_capture_collector import (
    MAX_CAPTURE_BYTES,
    MAX_CAPTURE_TOTAL_BYTES,
)
from .body_sway_runtime_capture_v2 import BodySwayRuntimeCaptureV2
from .body_sway_runtime_capture_v2_bundle import (
    build_body_sway_runtime_capture_v2_bundle,
)
from .body_sway_runtime_capture_v2_profile import (
    MANIFEST_NAME,
    MAX_CAPTURE_ARTIFACTS,
    MAX_CAPTURE_DOCUMENT_BYTES,
    NAMESPACE,
)
from .body_sway_runtime_capture_v2_validation import (
    require_body_sway_runtime_capture_v2,
)
from .manifest_artifacts import require_safe_token, require_sha256
from .safe_input_files import read_real_file, strict_json_object
from .spine42_bundle_files import (
    existing_exact_child,
    is_alias,
    require_real_directory,
)


class VerifiedBodySwayRuntimeCaptureV2ReaderError(RuntimeError):
    """Raised when an explicit v2 address cannot be trusted."""


class VerifiedBodySwayRuntimeCaptureV2NotFound(
    VerifiedBodySwayRuntimeCaptureV2ReaderError
):
    """Raised only when one exact address component is absent."""


@dataclass(frozen=True, slots=True)
class VerifiedBodySwayRuntimeCaptureV2:
    path: Path
    capture: BodySwayRuntimeCaptureV2
    bundle_sha256: str

    @property
    def project_id(self) -> str:
        return self.capture.document["project_id"]

    @property
    def temporary_preview_v2_sha256(self) -> str:
        return self.capture.document["source"]["temporary_preview_v2_sha256"]

    @property
    def artifact_set_sha256(self) -> str:
        return self.capture.artifact_set_sha256


@dataclass(frozen=True, slots=True)
class VerifiedBodySwayRuntimeCaptureV2Reader:
    state_root: Path

    def __post_init__(self) -> None:
        object.__setattr__(self, "state_root", Path(self.state_root))

    def load(
        self, project_id: str, temporary_preview_v2_sha256: str,
        bundle_sha256: str, artifact_set_sha256: str,
    ) -> VerifiedBodySwayRuntimeCaptureV2:
        """Load only the four explicit components; never scan or use latest."""

        try:
            project = require_safe_token(project_id, "Runtime capture v2 project")
            preview = require_sha256(
                temporary_preview_v2_sha256, "Runtime capture v2 preview"
            )
            bundle_sha = require_sha256(
                bundle_sha256, "Runtime capture v2 bundle"
            )
            artifact_sha = require_sha256(
                artifact_set_sha256, "Runtime capture v2 artifact set"
            )
            directory = _exact_bundle_path(
                self.state_root, project, preview, bundle_sha
            )
            manifest, items = _snapshot(directory)
            document = strict_json_object(manifest, MANIFEST_NAME)
            captures = dict(items)
            require_body_sway_runtime_capture_v2(document, captures)
            canonical = _canonical(document)
            if canonical != manifest:
                raise VerifiedBodySwayRuntimeCaptureV2ReaderError(
                    "Runtime capture v2 manifest is not canonical"
                )
            capture = BodySwayRuntimeCaptureV2.from_detached(document, captures)
            built = build_body_sway_runtime_capture_v2_bundle(capture)
            if built.file_items != ((MANIFEST_NAME, manifest),) + items \
                    or (
                        built.project_id,
                        built.temporary_preview_v2_sha256,
                        built.bundle_sha256,
                        built.artifact_set_sha256,
                    ) != (project, preview, bundle_sha, artifact_sha):
                raise VerifiedBodySwayRuntimeCaptureV2ReaderError(
                    "Runtime capture v2 bytes differ from their exact address"
                )
            return VerifiedBodySwayRuntimeCaptureV2(
                directory, capture, built.bundle_sha256
            )
        except VerifiedBodySwayRuntimeCaptureV2ReaderError:
            raise
        except (
            KeyError, OSError, RuntimeError, TypeError,
            UnicodeError, ValueError,
        ) as exc:
            raise VerifiedBodySwayRuntimeCaptureV2ReaderError(
                f"Verified RuntimeCapture v2 load failed: {exc}"
            ) from exc


def _exact_bundle_path(state_root, project, preview, bundle):
    try:
        root = Path(os.path.abspath(os.fspath(Path(state_root))))
        try:
            root.lstat()
        except FileNotFoundError:
            raise VerifiedBodySwayRuntimeCaptureV2NotFound(
                "Exact RuntimeCapture v2 address does not exist"
            )
        current = require_real_directory(root, "Runtime capture v2 state root")
        for name in ("builds", project, NAMESPACE, preview, bundle):
            child = existing_exact_child(current, name)
            if child is None:
                raise VerifiedBodySwayRuntimeCaptureV2NotFound(
                    "Exact RuntimeCapture v2 address does not exist"
                )
            current = require_real_directory(child, f"Runtime capture v2 {name}")
        current.resolve(strict=True).relative_to(root.resolve(strict=True))
        if is_alias(current):
            raise VerifiedBodySwayRuntimeCaptureV2ReaderError(
                "Runtime capture v2 address is aliased"
            )
        return current
    except VerifiedBodySwayRuntimeCaptureV2ReaderError:
        raise
    except (OSError, RuntimeError, ValueError) as exc:
        raise VerifiedBodySwayRuntimeCaptureV2ReaderError(
            "Exact RuntimeCapture v2 address cannot be resolved"
        ) from exc


def _snapshot(directory):
    root = _exact_inventory(directory, {MANIFEST_NAME, "captures"})
    manifest = read_real_file(
        root[MANIFEST_NAME], MAX_CAPTURE_DOCUMENT_BYTES, MANIFEST_NAME
    )
    document = strict_json_object(manifest, MANIFEST_NAME)
    paths = _declared_paths(document)
    capture_root = require_real_directory(
        root["captures"], "Runtime capture v2 PNG directory"
    )
    children = _exact_inventory(capture_root, {Path(path).name for path in paths})
    items, total = [], 0
    for path in paths:
        payload = read_real_file(children[Path(path).name], MAX_CAPTURE_BYTES, path)
        total += len(payload)
        if total > MAX_CAPTURE_TOTAL_BYTES:
            raise VerifiedBodySwayRuntimeCaptureV2ReaderError(
                "Runtime capture v2 PNG total exceeds its limit"
            )
        items.append((path, payload))
    return manifest, tuple(items)


def _declared_paths(document: Mapping):
    try:
        files = document["artifacts"]["files"]
        if not isinstance(files, list) \
                or not 3 <= len(files) <= MAX_CAPTURE_ARTIFACTS:
            raise VerifiedBodySwayRuntimeCaptureV2ReaderError(
                "Runtime capture v2 declared count is invalid"
            )
        paths = tuple(row["path"] for row in files)
        if any(type(path) is not str or not path.startswith("captures/")
               or path.count("/") != 1 or "\\" in path or "\x00" in path
               or Path(path).name != path.removeprefix("captures/")
               for path in paths) \
                or len({path.casefold() for path in paths}) != len(paths):
            raise VerifiedBodySwayRuntimeCaptureV2ReaderError(
                "Runtime capture v2 paths are unsafe"
            )
        return paths
    except VerifiedBodySwayRuntimeCaptureV2ReaderError:
        raise
    except (KeyError, TypeError, ValueError) as exc:
        raise VerifiedBodySwayRuntimeCaptureV2ReaderError(
            "Runtime capture v2 inventory is malformed"
        ) from exc


def _exact_inventory(directory, names):
    try:
        children = list(directory.iterdir())
        if len(children) != len(names) \
                or {item.name for item in children} != names \
                or len({item.name.casefold() for item in children}) \
                != len(children):
            raise VerifiedBodySwayRuntimeCaptureV2ReaderError(
                "Runtime capture v2 inventory differs"
            )
        for item in children:
            mode = item.lstat().st_mode
            expected_directory = item.name == "captures"
            valid = stat.S_ISDIR(mode) if expected_directory else stat.S_ISREG(mode)
            if is_alias(item) or not valid:
                raise VerifiedBodySwayRuntimeCaptureV2ReaderError(
                    "Runtime capture v2 inventory is unsafe"
                )
        return {item.name: item for item in children}
    except VerifiedBodySwayRuntimeCaptureV2ReaderError:
        raise
    except OSError as exc:
        raise VerifiedBodySwayRuntimeCaptureV2ReaderError(
            "Runtime capture v2 inventory cannot be inspected"
        ) from exc


def _canonical(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, allow_nan=False,
                      sort_keys=True, separators=(",", ":")).encode("utf-8")
