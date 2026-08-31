"""Content-addressed manifest and PNG bundle for RuntimeCapture v2."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json

from .body_sway_runtime_capture_collector import (
    MAX_CAPTURE_BYTES,
    MAX_CAPTURE_TOTAL_BYTES,
)
from .body_sway_runtime_capture_v2 import BodySwayRuntimeCaptureV2
from .body_sway_runtime_capture_v2_profile import (
    BUNDLE_ADDRESS_DOMAIN,
    MANIFEST_NAME,
    MAX_CAPTURE_ARTIFACTS,
    MAX_CAPTURE_DOCUMENT_BYTES,
)
from .body_sway_runtime_capture_v2_validation import (
    require_body_sway_runtime_capture_v2,
)


class BodySwayRuntimeCaptureV2BundleError(ValueError):
    """Raised when exact v2 bytes cannot form the fixed bundle."""


@dataclass(frozen=True, slots=True)
class BodySwayRuntimeCaptureV2Bundle:
    project_id: str
    temporary_preview_v2_sha256: str
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


def build_body_sway_runtime_capture_v2_bundle(
    capture: BodySwayRuntimeCaptureV2,
) -> BodySwayRuntimeCaptureV2Bundle:
    """Validate and freeze the only manifest-plus-PNG inventory."""

    try:
        if type(capture) is not BodySwayRuntimeCaptureV2:
            raise BodySwayRuntimeCaptureV2BundleError(
                "Runtime capture v2 bundle requires an exact value"
            )
        document, captures = capture.document, capture.capture_bytes
        require_body_sway_runtime_capture_v2(document, captures)
        manifest = capture.canonical_bytes
        if manifest != _canonical(document) \
                or not 0 < len(manifest) <= MAX_CAPTURE_DOCUMENT_BYTES:
            raise BodySwayRuntimeCaptureV2BundleError(
                "Runtime capture v2 manifest is non-canonical or unbounded"
            )
        paths = tuple(row["path"] for row in document["artifacts"]["files"])
        if len(paths) != len(set(paths)) or set(paths) != set(captures):
            raise BodySwayRuntimeCaptureV2BundleError(
                "Runtime capture v2 PNG inventory is not exact"
            )
        items = ((MANIFEST_NAME, manifest),) + tuple(
            (path, captures[path]) for path in paths
        )
        return BodySwayRuntimeCaptureV2Bundle(
            document["project_id"],
            document["source"]["temporary_preview_v2_sha256"],
            hashlib.sha256(manifest).hexdigest(),
            document["artifacts"]["artifact_set_sha256"],
            body_sway_runtime_capture_v2_bundle_sha256(manifest, items[1:]),
            items,
        )
    except BodySwayRuntimeCaptureV2BundleError:
        raise
    except (
        KeyError, OverflowError, TypeError, UnicodeError, ValueError,
    ) as exc:
        raise BodySwayRuntimeCaptureV2BundleError(
            f"Runtime capture v2 bundle compilation failed: {exc}"
        ) from exc


def body_sway_runtime_capture_v2_bundle_sha256(
    manifest: bytes, ordered_capture_items: tuple[tuple[str, bytes], ...],
) -> str:
    """Hash the independent v2 domain and length-frame every byte field."""

    items = tuple(ordered_capture_items)
    if type(manifest) is not bytes \
            or not 0 < len(manifest) <= MAX_CAPTURE_DOCUMENT_BYTES \
            or not 3 <= len(items) <= MAX_CAPTURE_ARTIFACTS:
        raise BodySwayRuntimeCaptureV2BundleError(
            "Runtime capture v2 bundle inventory is unbounded"
        )
    digest = hashlib.sha256()
    _frame(digest, BUNDLE_ADDRESS_DOMAIN)
    _frame(digest, manifest)
    _frame(digest, len(items).to_bytes(8, "big"))
    folded, total = set(), 0
    for path, payload in items:
        if type(path) is not str or not path.startswith("captures/") \
                or path.count("/") != 1 or "\\" in path or "\x00" in path \
                or path.casefold() in folded or type(payload) is not bytes \
                or not 0 < len(payload) <= MAX_CAPTURE_BYTES:
            raise BodySwayRuntimeCaptureV2BundleError(
                "Runtime capture v2 bundle item is invalid"
            )
        folded.add(path.casefold())
        total += len(payload)
        if total > MAX_CAPTURE_TOTAL_BYTES:
            raise BodySwayRuntimeCaptureV2BundleError(
                "Runtime capture v2 bundle exceeds its byte limit"
            )
        _frame(digest, path.encode("utf-8"))
        _frame(digest, payload)
    return digest.hexdigest()


def _frame(digest, value: bytes) -> None:
    digest.update(len(value).to_bytes(8, "big"))
    digest.update(value)


def _canonical(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, allow_nan=False,
                      sort_keys=True, separators=(",", ":")).encode("utf-8")
