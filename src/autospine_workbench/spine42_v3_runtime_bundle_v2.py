"""Version-isolated immutable bundle contract for runtime evidence v2."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib

from .spine42_v3_runtime_evidence_v2 import (
    FIXED_NAMES, MAX_JSON_BYTES,
    Spine42V3RuntimeEvidenceV2,
    Spine42V3RuntimeEvidenceV2Error,
    _require_issued_spine42_v3_runtime_evidence_v2,
    replay_spine42_v3_runtime_evidence_v2,
)
from .spine42_v3_runtime_evidence_contract_v2 import safe_png
from .spine42_v3_runtime_capture_core import (
    MAX_CAPTURE_BYTES, MAX_CAPTURE_TOTAL_BYTES,
)
from .spine42_v3_runtime_profile_v2 import MAX_CAPTURE_ARTIFACTS


NAMESPACE = "spine42-v3-runtime-v2"
BUNDLE_ADDRESS_DOMAIN = b"autospine.spine42-v3-runtime-bundle/v2\x00"


class Spine42V3RuntimeBundleV2Error(ValueError):
    """Raised when v2 runtime evidence cannot form its exact bundle."""


@dataclass(frozen=True, slots=True)
class Spine42V3RuntimeBundleV2:
    project_id: str
    clip_id: str
    skeleton_json_sha256: str
    spine42_v3_bundle_sha256: str
    evidence_sha256: str
    bundle_sha256: str
    _file_items: tuple[tuple[str, bytes], ...] = field(repr=False)

    @property
    def file_items(self) -> tuple[tuple[str, bytes], ...]:
        return self._file_items


def build_spine42_v3_runtime_bundle_v2(
    evidence: Spine42V3RuntimeEvidenceV2,
) -> Spine42V3RuntimeBundleV2:
    """Accept only issued evidence and frame every exact name and payload."""

    try:
        upstream, items = _require_issued_spine42_v3_runtime_evidence_v2(
            evidence
        )
        replayed = replay_spine42_v3_runtime_bundle_v2(upstream, items)
        if replayed.evidence_sha256 != evidence.evidence_sha256:
            raise Spine42V3RuntimeBundleV2Error(
                "Runtime evidence v2 differs from exact replay"
            )
        return replayed
    except Spine42V3RuntimeBundleV2Error:
        raise
    except (Spine42V3RuntimeEvidenceV2Error, TypeError, ValueError) as exc:
        raise Spine42V3RuntimeBundleV2Error(
            "Runtime bundle v2 compilation failed"
        ) from exc


def replay_spine42_v3_runtime_bundle_v2(
    upstream,
    file_items: tuple[tuple[str, bytes], ...],
) -> Spine42V3RuntimeBundleV2:
    """Build a detached historical bundle without minting live authority."""

    try:
        evidence = replay_spine42_v3_runtime_evidence_v2(
            upstream, file_items,
        )
        return Spine42V3RuntimeBundleV2(
            evidence.project_id, evidence.clip_id,
            evidence.skeleton_json_sha256,
            evidence.spine42_v3_bundle_sha256, evidence.evidence_sha256,
            spine42_v3_runtime_bundle_sha256_v2(file_items), file_items,
        )
    except Spine42V3RuntimeBundleV2Error:
        raise
    except (Spine42V3RuntimeEvidenceV2Error, TypeError, ValueError) as exc:
        raise Spine42V3RuntimeBundleV2Error(
            "Runtime bundle v2 replay failed"
        ) from exc


def spine42_v3_runtime_bundle_sha256_v2(file_items) -> str:
    """Length-frame the v2 domain, ordered paths, and immutable bytes."""

    if type(file_items) is not tuple \
            or not len(FIXED_NAMES) + 4 <= len(file_items) <= \
            len(FIXED_NAMES) + MAX_CAPTURE_ARTIFACTS:
        raise Spine42V3RuntimeBundleV2Error("Bundle v2 inventory is invalid")
    digest = hashlib.sha256()
    _frame(digest, BUNDLE_ADDRESS_DOMAIN)
    _frame(digest, len(file_items).to_bytes(8, "big"))
    folded = set()
    total = 0
    for index, item in enumerate(file_items):
        if type(item) is not tuple or len(item) != 2:
            raise Spine42V3RuntimeBundleV2Error("Bundle v2 item is invalid")
        name, raw = item
        fixed = index < len(FIXED_NAMES)
        expected_name = FIXED_NAMES[index] if fixed else None
        capture_name = name.removeprefix("captures/") \
            if type(name) is str else None
        valid_name = name == expected_name if fixed else (
            name.startswith("captures/") and name.count("/") == 1
            and safe_png(capture_name)
        )
        limit = MAX_JSON_BYTES if fixed else MAX_CAPTURE_BYTES
        if not valid_name or type(raw) is not bytes \
                or not 0 < len(raw) <= limit or name.casefold() in folded:
            raise Spine42V3RuntimeBundleV2Error("Bundle v2 item is invalid")
        folded.add(name.casefold())
        if not fixed:
            total += len(raw)
        _frame(digest, name.encode("utf-8"))
        _frame(digest, raw)
    if total > MAX_CAPTURE_TOTAL_BYTES:
        raise Spine42V3RuntimeBundleV2Error("Bundle v2 PNG total is too large")
    return digest.hexdigest()


def _frame(digest, raw):
    digest.update(len(raw).to_bytes(8, "big"))
    digest.update(raw)


__all__ = [
    "BUNDLE_ADDRESS_DOMAIN", "NAMESPACE", "Spine42V3RuntimeBundleV2",
    "Spine42V3RuntimeBundleV2Error", "build_spine42_v3_runtime_bundle_v2",
    "replay_spine42_v3_runtime_bundle_v2",
    "spine42_v3_runtime_bundle_sha256_v2",
]
