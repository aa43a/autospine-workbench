"""Content-addressed byte bundle for one runtime capture manifest and PNG set."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from typing import Any

from .body_sway_runtime_capture import BodySwayRuntimeCapture
from .body_sway_runtime_capture_collector import (
    MAX_CAPTURE_BYTES,
    MAX_CAPTURE_TOTAL_BYTES,
)
from .body_sway_runtime_capture_profile import (
    MAX_CAPTURE_ARTIFACTS,
    MAX_CAPTURE_DOCUMENT_BYTES,
)
from .body_sway_runtime_capture_validation import (
    BodySwayRuntimeCaptureValidationError,
    require_body_sway_runtime_capture,
)


MANIFEST_NAME = "body-sway-runtime-capture.json"
BUNDLE_ADDRESS_DOMAIN = b"autospine.body-sway-runtime-capture-bundle/v1\x00"


class BodySwayRuntimeCaptureBundleError(ValueError):
    """Raised when runtime capture bytes cannot form the fixed disk bundle."""


@dataclass(frozen=True, slots=True)
class BodySwayRuntimeCaptureBundle:
    """Frozen exact bytes and identities used by the immutable store."""

    project_id: str
    temporary_preview_sha256: str
    manifest_sha256: str
    artifact_set_sha256: str
    bundle_sha256: str
    _file_items: tuple[tuple[str, bytes], ...] = field(repr=False)

    @property
    def file_items(self) -> tuple[tuple[str, bytes], ...]:
        return self._file_items

    @property
    def manifest_bytes(self) -> bytes:
        return self._file_items[0][1]

    @property
    def capture_bytes(self) -> dict[str, bytes]:
        return dict(self._file_items[1:])


def build_body_sway_runtime_capture_bundle(
    capture: BodySwayRuntimeCapture,
) -> BodySwayRuntimeCaptureBundle:
    """Validate and freeze the sole fixed manifest-plus-PNG inventory."""

    try:
        if type(capture) is not BodySwayRuntimeCapture:
            raise BodySwayRuntimeCaptureBundleError(
                "Runtime capture bundle requires an exact capture snapshot"
            )
        document = capture.document
        captures = capture.capture_bytes
        require_body_sway_runtime_capture(document, captures)
        manifest = capture.canonical_bytes
        canonical = json.dumps(
            document, ensure_ascii=False, allow_nan=False,
            sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")
        if manifest != canonical \
                or not 0 < len(manifest) <= MAX_CAPTURE_DOCUMENT_BYTES:
            raise BodySwayRuntimeCaptureBundleError(
                "Runtime capture manifest is non-canonical or unbounded"
            )
        paths = tuple(row["path"] for row in document["artifacts"]["files"])
        if len(paths) != len(set(paths)) or set(paths) != set(captures):
            raise BodySwayRuntimeCaptureBundleError(
                "Runtime capture PNG inventory is not exact"
            )
        items = ((MANIFEST_NAME, manifest),) + tuple(
            (path, captures[path]) for path in paths
        )
        bundle_sha = body_sway_runtime_capture_bundle_sha256(
            manifest, items[1:]
        )
        return BodySwayRuntimeCaptureBundle(
            project_id=document["project_id"],
            temporary_preview_sha256=(
                document["source"]["temporary_preview_sha256"]
            ),
            manifest_sha256=hashlib.sha256(manifest).hexdigest(),
            artifact_set_sha256=document["artifacts"]["artifact_set_sha256"],
            bundle_sha256=bundle_sha,
            _file_items=items,
        )
    except BodySwayRuntimeCaptureBundleError:
        raise
    except (
        BodySwayRuntimeCaptureValidationError, KeyError, OverflowError,
        TypeError, UnicodeError, ValueError,
    ) as exc:
        raise BodySwayRuntimeCaptureBundleError(
            f"Runtime capture bundle compilation failed: {exc}"
        ) from exc


def body_sway_runtime_capture_bundle_sha256(
    canonical_manifest_bytes: bytes,
    ordered_capture_items: tuple[tuple[str, bytes], ...],
) -> str:
    """Hash the independent binary domain and every length-framed byte field."""

    if type(canonical_manifest_bytes) is not bytes:
        raise BodySwayRuntimeCaptureBundleError(
            "Runtime capture manifest payload must be bytes"
        )
    items = tuple(ordered_capture_items)
    if not 3 <= len(items) <= MAX_CAPTURE_ARTIFACTS \
            or not 0 < len(canonical_manifest_bytes) <= MAX_CAPTURE_DOCUMENT_BYTES:
        raise BodySwayRuntimeCaptureBundleError(
            "Runtime capture bundle inventory or manifest is unbounded"
        )
    digest = hashlib.sha256()
    _frame(digest, BUNDLE_ADDRESS_DOMAIN)
    _frame(digest, canonical_manifest_bytes)
    _frame(digest, len(items).to_bytes(8, "big"))
    folded: set[str] = set()
    total = 0
    for item in items:
        if type(item) is not tuple or len(item) != 2:
            raise BodySwayRuntimeCaptureBundleError(
                "Runtime capture bundle item is invalid"
            )
        path, payload = item
        if type(path) is not str or not path.startswith("captures/") \
                or path.count("/") != 1 or "\\" in path or "\x00" in path:
            raise BodySwayRuntimeCaptureBundleError(
                "Runtime capture bundle path is invalid"
            )
        if path.casefold() in folded or type(payload) is not bytes \
                or not 0 < len(payload) <= MAX_CAPTURE_BYTES:
            raise BodySwayRuntimeCaptureBundleError(
                "Runtime capture bundle item is aliased or unbounded"
            )
        folded.add(path.casefold())
        total += len(payload)
        if total > MAX_CAPTURE_TOTAL_BYTES:
            raise BodySwayRuntimeCaptureBundleError(
                "Runtime capture bundle exceeds its total byte limit"
            )
        _frame(digest, path.encode("utf-8"))
        _frame(digest, payload)
    return digest.hexdigest()


def _frame(digest: Any, value: bytes) -> None:
    digest.update(len(value).to_bytes(8, "big"))
    digest.update(value)
