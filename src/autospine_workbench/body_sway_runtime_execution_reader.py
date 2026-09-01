"""Read-only exact-address loader for official runtime execution bundles."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import os
from pathlib import Path
import stat

from .body_sway_runtime_capture_collector import (
    MAX_CAPTURE_BYTES,
    MAX_CAPTURE_TOTAL_BYTES,
)
from .body_sway_runtime_capture_v2_profile import (
    MAX_CAPTURE_ARTIFACTS,
    MAX_CAPTURE_DOCUMENT_BYTES,
)
from .body_sway_runtime_execution import BodySwayRuntimeExecution
from .body_sway_runtime_execution_bundle import (
    body_sway_runtime_execution_bundle_sha256,
    replay_body_sway_runtime_execution,
)
from .body_sway_runtime_execution_profile import (
    MANIFEST_NAME,
    MAX_MANIFEST_BYTES,
    NAMESPACE,
    PAYLOAD_NAME,
)
from .manifest_artifacts import require_safe_token, require_sha256
from .safe_input_files import read_real_file, strict_json_object
from .spine42_bundle_files import (
    existing_exact_child,
    is_alias,
    require_real_directory,
)


class VerifiedBodySwayRuntimeExecutionReaderError(RuntimeError):
    """Raised when an explicit execution address cannot be trusted."""


class VerifiedBodySwayRuntimeExecutionNotFound(
    VerifiedBodySwayRuntimeExecutionReaderError
):
    """Raised only when an exact address component is absent."""


@dataclass(frozen=True, slots=True)
class VerifiedBodySwayRuntimeExecution:
    path: Path
    execution: BodySwayRuntimeExecution
    bundle_sha256: str

    @property
    def project_id(self) -> str:
        return self.execution.document["project_id"]

    @property
    def temporary_preview_v2_sha256(self) -> str:
        return self.execution.document["source"][
            "temporary_preview_v2_sha256"
        ]

    @property
    def artifact_set_sha256(self) -> str:
        return self.execution.artifact_set_sha256


@dataclass(frozen=True, slots=True)
class VerifiedBodySwayRuntimeExecutionReader:
    state_root: Path

    def __post_init__(self) -> None:
        object.__setattr__(self, "state_root", Path(self.state_root))

    def load(
        self, project_id: str, temporary_preview_v2_sha256: str,
        bundle_sha256: str, artifact_set_sha256: str,
    ) -> VerifiedBodySwayRuntimeExecution:
        """Load only project/preview/bundle/artifact; never scan or use latest."""

        try:
            project = require_safe_token(
                project_id, "Runtime execution project",
            )
            preview = require_sha256(
                temporary_preview_v2_sha256, "Runtime execution preview",
            )
            bundle_sha = require_sha256(
                bundle_sha256, "Runtime execution bundle",
            )
            artifact_sha = require_sha256(
                artifact_set_sha256, "Runtime execution artifact set",
            )
            directory = _exact_bundle_path(
                self.state_root, project, preview, bundle_sha,
            )
            execution_bytes, payload_bytes, capture_items = _snapshot(
                directory,
            )
            execution = replay_body_sway_runtime_execution(
                execution_bytes, payload_bytes, capture_items,
            )
            actual = (
                (MANIFEST_NAME, execution_bytes),
                (PAYLOAD_NAME, payload_bytes),
            ) + capture_items
            actual_bundle_sha = body_sway_runtime_execution_bundle_sha256(
                actual,
            )
            if (
                execution.document["project_id"],
                execution.document["source"]
                ["temporary_preview_v2_sha256"],
                actual_bundle_sha,
                execution.artifact_set_sha256,
            ) != (project, preview, bundle_sha, artifact_sha):
                raise VerifiedBodySwayRuntimeExecutionReaderError(
                    "Runtime execution bytes differ from their exact address"
                )
            return VerifiedBodySwayRuntimeExecution(
                directory, execution, actual_bundle_sha,
            )
        except VerifiedBodySwayRuntimeExecutionReaderError:
            raise
        except (
            KeyError, OSError, RuntimeError, TypeError,
            UnicodeError, ValueError,
        ) as exc:
            raise VerifiedBodySwayRuntimeExecutionReaderError(
                f"Verified runtime execution load failed: {exc}"
            ) from exc


def _exact_bundle_path(state_root, project, preview, bundle):
    try:
        root = Path(os.path.abspath(os.fspath(Path(state_root))))
        try:
            root.lstat()
        except FileNotFoundError:
            raise VerifiedBodySwayRuntimeExecutionNotFound(
                "Exact runtime execution address does not exist"
            )
        current = require_real_directory(
            root, "Runtime execution state root",
        )
        for name in ("builds", project, NAMESPACE, preview, bundle):
            child = existing_exact_child(current, name)
            if child is None:
                raise VerifiedBodySwayRuntimeExecutionNotFound(
                    "Exact runtime execution address does not exist"
                )
            current = require_real_directory(
                child, f"Runtime execution {name}",
            )
        current.resolve(strict=True).relative_to(root.resolve(strict=True))
        if is_alias(current):
            raise VerifiedBodySwayRuntimeExecutionReaderError(
                "Runtime execution address is aliased"
            )
        return current
    except VerifiedBodySwayRuntimeExecutionReaderError:
        raise
    except (OSError, RuntimeError, ValueError) as exc:
        raise VerifiedBodySwayRuntimeExecutionReaderError(
            "Exact runtime execution address cannot be resolved"
        ) from exc


def _snapshot(directory):
    root = _exact_inventory(
        directory, {MANIFEST_NAME, PAYLOAD_NAME, "captures"},
    )
    execution_bytes = read_real_file(
        root[MANIFEST_NAME], MAX_MANIFEST_BYTES, MANIFEST_NAME,
    )
    payload_bytes = read_real_file(
        root[PAYLOAD_NAME], MAX_CAPTURE_DOCUMENT_BYTES, PAYLOAD_NAME,
    )
    payload = strict_json_object(payload_bytes, PAYLOAD_NAME)
    paths = _declared_paths(payload)
    capture_root = require_real_directory(
        root["captures"], "Runtime execution captures",
    )
    children = _exact_inventory(
        capture_root, {Path(path).name for path in paths},
    )
    items, total = [], 0
    for path in paths:
        payload = read_real_file(
            children[Path(path).name], MAX_CAPTURE_BYTES, path,
        )
        total += len(payload)
        if total > MAX_CAPTURE_TOTAL_BYTES:
            raise VerifiedBodySwayRuntimeExecutionReaderError(
                "Runtime execution PNG total exceeds its limit"
            )
        items.append((path, payload))
    return execution_bytes, payload_bytes, tuple(items)


def _declared_paths(document: Mapping):
    try:
        files = document["artifacts"]["files"]
        if not isinstance(files, list) \
                or not 3 <= len(files) <= MAX_CAPTURE_ARTIFACTS:
            raise VerifiedBodySwayRuntimeExecutionReaderError(
                "Runtime execution declared count is invalid"
            )
        paths = tuple(row["path"] for row in files)
        if any(
            type(path) is not str or not path.startswith("captures/")
            or path.count("/") != 1 or "\\" in path or "\x00" in path
            or Path(path).name != path.removeprefix("captures/")
            for path in paths
        ) or len({path.casefold() for path in paths}) != len(paths):
            raise VerifiedBodySwayRuntimeExecutionReaderError(
                "Runtime execution paths are unsafe"
            )
        return paths
    except VerifiedBodySwayRuntimeExecutionReaderError:
        raise
    except (KeyError, TypeError, ValueError) as exc:
        raise VerifiedBodySwayRuntimeExecutionReaderError(
            "Runtime execution inventory is malformed"
        ) from exc


def _exact_inventory(directory, names):
    try:
        children = list(directory.iterdir())
        if len(children) != len(names) \
                or {item.name for item in children} != names \
                or len({item.name.casefold() for item in children}) \
                != len(children):
            raise VerifiedBodySwayRuntimeExecutionReaderError(
                "Runtime execution inventory differs"
            )
        for item in children:
            mode = item.lstat().st_mode
            expected_directory = item.name == "captures"
            valid = stat.S_ISDIR(mode) if expected_directory \
                else stat.S_ISREG(mode)
            if is_alias(item) or not valid:
                raise VerifiedBodySwayRuntimeExecutionReaderError(
                    "Runtime execution inventory is unsafe"
                )
        return {item.name: item for item in children}
    except VerifiedBodySwayRuntimeExecutionReaderError:
        raise
    except OSError as exc:
        raise VerifiedBodySwayRuntimeExecutionReaderError(
            "Runtime execution inventory cannot be inspected"
        ) from exc
