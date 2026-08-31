"""Immutable receipt, payload-v2, and PNG bundle for official execution."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path

from .body_sway_runtime_capture_collector import (
    MAX_CAPTURE_BYTES,
    MAX_CAPTURE_TOTAL_BYTES,
)
from .body_sway_runtime_capture_v2 import BodySwayRuntimeCaptureV2
from .body_sway_runtime_capture_v2_profile import (
    MAX_CAPTURE_ARTIFACTS,
    MAX_CAPTURE_DOCUMENT_BYTES,
)
from .body_sway_runtime_execution import (
    BodySwayRuntimeExecution,
    BodySwayRuntimeExecutionError,
)
from .body_sway_runtime_execution_profile import (
    BUNDLE_ADDRESS_DOMAIN,
    MANIFEST_NAME,
    MAX_MANIFEST_BYTES,
    PAYLOAD_NAME,
)


class BodySwayRuntimeExecutionBundleError(ValueError):
    """Raised when official execution bytes cannot form the fixed bundle."""


@dataclass(frozen=True, slots=True)
class BodySwayRuntimeExecutionBundle:
    project_id: str
    temporary_preview_v2_sha256: str
    execution_sha256: str
    runtime_capture_v2_sha256: str
    artifact_set_sha256: str
    bundle_sha256: str
    _file_items: tuple[tuple[str, bytes], ...] = field(repr=False)

    @property
    def file_items(self) -> tuple[tuple[str, bytes], ...]:
        return self._file_items


def build_body_sway_runtime_execution_bundle(
    execution: BodySwayRuntimeExecution,
) -> BodySwayRuntimeExecutionBundle:
    """Replay the nested evidence, then length-frame every exact byte."""

    try:
        if type(execution) is not BodySwayRuntimeExecution:
            raise BodySwayRuntimeExecutionBundleError(
                "Runtime execution bundle requires exact evidence"
            )
        capture = execution.capture
        replayed = replay_body_sway_runtime_execution(
            execution.canonical_bytes,
            capture.canonical_bytes,
            tuple(capture.capture_bytes.items()),
        )
        if replayed.canonical_bytes != execution.canonical_bytes \
                or replayed.capture.canonical_bytes \
                != capture.canonical_bytes \
                or replayed.capture.capture_bytes != capture.capture_bytes:
            raise BodySwayRuntimeExecutionBundleError(
                "Runtime execution differs from detached replay"
            )
        paths = [row["path"] for row in capture.document["artifacts"]["files"]]
        items = (
            (MANIFEST_NAME, execution.canonical_bytes),
            (PAYLOAD_NAME, capture.canonical_bytes),
        ) + tuple((path, capture.capture_bytes[path]) for path in paths)
        source = execution.document["source"]
        return BodySwayRuntimeExecutionBundle(
            execution.document["project_id"],
            source["temporary_preview_v2_sha256"],
            execution.sha256,
            capture.sha256,
            capture.artifact_set_sha256,
            body_sway_runtime_execution_bundle_sha256(items),
            items,
        )
    except BodySwayRuntimeExecutionBundleError:
        raise
    except (
        BodySwayRuntimeExecutionError, KeyError, TypeError, ValueError,
    ) as exc:
        raise BodySwayRuntimeExecutionBundleError(
            f"Runtime execution bundle compilation failed: {exc}"
        ) from exc


def replay_body_sway_runtime_execution(
    execution_bytes: bytes,
    payload_bytes: bytes,
    capture_items: tuple[tuple[str, bytes], ...],
) -> BodySwayRuntimeExecution:
    """Validate canonical documents and the complete declared PNG inventory."""

    try:
        execution_document = _document(
            execution_bytes, MAX_MANIFEST_BYTES, MANIFEST_NAME,
        )
        payload_document = _document(
            payload_bytes, MAX_CAPTURE_DOCUMENT_BYTES, PAYLOAD_NAME,
        )
        captures = dict(capture_items)
        if len(captures) != len(capture_items):
            raise BodySwayRuntimeExecutionBundleError(
                "Runtime execution PNG paths are duplicated"
            )
        capture = BodySwayRuntimeCaptureV2.from_detached(
            payload_document, captures,
        )
        execution = BodySwayRuntimeExecution.from_detached(
            execution_document, capture,
        )
        if execution.canonical_bytes != execution_bytes \
                or capture.canonical_bytes != payload_bytes:
            raise BodySwayRuntimeExecutionBundleError(
                "Runtime execution documents are not canonical"
            )
        return execution
    except BodySwayRuntimeExecutionBundleError:
        raise
    except (
        BodySwayRuntimeExecutionError, UnicodeError,
        TypeError, ValueError,
    ) as exc:
        raise BodySwayRuntimeExecutionBundleError(
            f"Runtime execution replay failed: {exc}"
        ) from exc


def body_sway_runtime_execution_bundle_sha256(
    file_items: tuple[tuple[str, bytes], ...],
) -> str:
    items = tuple(file_items)
    if not 5 <= len(items) <= MAX_CAPTURE_ARTIFACTS + 2 \
            or tuple(path for path, _raw in items[:2]) \
            != (MANIFEST_NAME, PAYLOAD_NAME):
        raise BodySwayRuntimeExecutionBundleError(
            "Runtime execution bundle inventory is invalid"
        )
    digest, names, total = hashlib.sha256(), set(), 0
    _frame(digest, BUNDLE_ADDRESS_DOMAIN)
    _frame(digest, len(items).to_bytes(8, "big"))
    for index, item in enumerate(items):
        if type(item) is not tuple or len(item) != 2:
            raise BodySwayRuntimeExecutionBundleError(
                "Runtime execution bundle item is invalid"
            )
        path, raw = item
        limit = (
            MAX_MANIFEST_BYTES if index == 0 else
            MAX_CAPTURE_DOCUMENT_BYTES if index == 1 else MAX_CAPTURE_BYTES
        )
        if type(path) is not str or path.casefold() in names \
                or type(raw) is not bytes or not 0 < len(raw) <= limit \
                or index >= 2 and not _safe_capture_path(path):
            raise BodySwayRuntimeExecutionBundleError(
                "Runtime execution bundle path or payload is invalid"
            )
        names.add(path.casefold())
        total += len(raw) if index >= 2 else 0
        _frame(digest, path.encode("utf-8"))
        _frame(digest, raw)
    if total > MAX_CAPTURE_TOTAL_BYTES:
        raise BodySwayRuntimeExecutionBundleError(
            "Runtime execution PNG total exceeds its limit"
        )
    return digest.hexdigest()


def _document(raw, limit, label):
    if type(raw) is not bytes or not 0 < len(raw) <= limit:
        raise BodySwayRuntimeExecutionBundleError(f"{label} is unbounded")
    value = json.loads(raw.decode("utf-8"))
    if not isinstance(value, dict) or _canonical(value) != raw:
        raise BodySwayRuntimeExecutionBundleError(f"{label} is not canonical")
    return value


def _safe_capture_path(value):
    return type(value) is str and value.startswith("captures/") \
        and value.count("/") == 1 and "\\" not in value \
        and "\x00" not in value and Path(value).suffix == ".png"


def _frame(digest, value):
    digest.update(len(value).to_bytes(8, "big"))
    digest.update(value)


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False,
                      sort_keys=True, separators=(",", ":")).encode("utf-8")


__all__ = [
    "BodySwayRuntimeExecutionBundle",
    "BodySwayRuntimeExecutionBundleError",
    "body_sway_runtime_execution_bundle_sha256",
    "build_body_sway_runtime_execution_bundle",
    "replay_body_sway_runtime_execution",
]
