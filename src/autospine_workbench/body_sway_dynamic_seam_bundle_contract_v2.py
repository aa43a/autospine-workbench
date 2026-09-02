"""Fixed three-document contract for P10.5d v2 immutable bundles."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
import hashlib
import json

from .body_sway_dynamic_seam_probe_validation_v2 import (
    MAX_DOCUMENT_BYTES as MAX_PROBE_BYTES,
    body_sway_dynamic_seam_probe_sha256_v2,
)
from .body_sway_dynamic_seam_profile_v2 import MAX_SOURCE_BYTES
from .body_sway_dynamic_seam_validation_v2 import (
    require_body_sway_dynamic_seam_source_v2,
)
from .immutable_bundle_fs import framed_bundle_sha256
from .seam_anchor_review_json import canonical_json_bytes


BUNDLE_ADDRESS_DOMAIN = "autospine-body-sway-dynamic-seam-bundle/v2"
DOCUMENT_NAMES = (
    "body-sway-dynamic-seam-source-v2.json",
    "body-sway-dynamic-seam-probe-v2.json",
    "bundle-manifest.json",
)
MANIFEST_MAX_BYTES = 64 * 1024
MAX_FILE_BYTES = max(MAX_SOURCE_BYTES, MAX_PROBE_BYTES, MANIFEST_MAX_BYTES)
MAX_TOTAL_BYTES = MAX_SOURCE_BYTES + MAX_PROBE_BYTES + MANIFEST_MAX_BYTES


class BodySwayDynamicSeamBundleContractV2Error(ValueError):
    """Raised when exact source and probe bytes cannot form one bundle."""


@dataclass(frozen=True, slots=True)
class BodySwayDynamicSeamBundleContractV2:
    project_id: str
    clip_id: str
    source_set_sha256: str
    source_document_sha256: str
    probe_sha256: str
    bundle_sha256: str
    _documents: tuple[tuple[str, bytes], ...] = field(repr=False)

    @property
    def document_bytes(self) -> dict[str, bytes]:
        return dict(self._documents)

    @property
    def manifest(self) -> dict:
        return json.loads(dict(self._documents)[DOCUMENT_NAMES[2]])


def build_body_sway_dynamic_seam_bundle_contract_v2(
    source: Mapping,
    probe: Mapping,
) -> BodySwayDynamicSeamBundleContractV2:
    """Fully replay source and probe, then frame their exact inventory."""

    try:
        admitted = require_body_sway_dynamic_seam_source_v2(source)
        source_bytes = canonical_json_bytes(admitted)
        probe_sha = body_sway_dynamic_seam_probe_sha256_v2(probe)
        probe_bytes = canonical_json_bytes(probe)
        if canonical_json_bytes(probe["source"]) != source_bytes:
            raise BodySwayDynamicSeamBundleContractV2Error(
                "Dynamic seam v2 probe source differs from bundle source"
            )
        source_sha = hashlib.sha256(source_bytes).hexdigest()
        project_id, clip_id = admitted["project_id"], admitted["clip_id"]
        manifest = {
            "format": "autospine-body-sway-dynamic-seam-bundle-manifest",
            "format_version": 2,
            "project_id": project_id,
            "clip_id": clip_id,
            "source_set_sha256": admitted["source_set_sha256"],
            "source_document_sha256": source_sha,
            "probe_sha256": probe_sha,
            "authority_scope": "historical_exact_bytes_only",
            "documents": [
                _entry(DOCUMENT_NAMES[0], source_bytes, source_sha),
                _entry(DOCUMENT_NAMES[1], probe_bytes, probe_sha),
            ],
            "claims": {
                "current_head_authority": False,
                "official_runtime_equivalence": False,
                "raster_visual_quality": False,
                "release_authority": False,
            },
        }
        manifest_bytes = canonical_json_bytes(manifest)
        if len(manifest_bytes) > MANIFEST_MAX_BYTES:
            raise BodySwayDynamicSeamBundleContractV2Error(
                "Dynamic seam v2 bundle manifest exceeds its byte limit"
            )
        files = {
            DOCUMENT_NAMES[0]: source_bytes,
            DOCUMENT_NAMES[1]: probe_bytes,
            DOCUMENT_NAMES[2]: manifest_bytes,
        }
        if sum(map(len, files.values())) > MAX_TOTAL_BYTES:
            raise BodySwayDynamicSeamBundleContractV2Error(
                "Dynamic seam v2 bundle exceeds its total byte limit"
            )
        bundle_sha = framed_bundle_sha256(
            BUNDLE_ADDRESS_DOMAIN, DOCUMENT_NAMES, files,
        )
        return BodySwayDynamicSeamBundleContractV2(
            project_id, clip_id, admitted["source_set_sha256"],
            source_sha, probe_sha, bundle_sha,
            tuple((name, files[name]) for name in DOCUMENT_NAMES),
        )
    except BodySwayDynamicSeamBundleContractV2Error:
        raise
    except (
        AttributeError, KeyError, OverflowError, RecursionError,
        RuntimeError, TypeError, UnicodeError, ValueError,
    ) as exc:
        raise BodySwayDynamicSeamBundleContractV2Error(
            "Dynamic seam v2 bundle contract failed"
        ) from exc


def _entry(name, data, digest):
    return {"name": name, "sha256": digest, "size_bytes": len(data)}


__all__ = [
    "BUNDLE_ADDRESS_DOMAIN", "DOCUMENT_NAMES", "MAX_FILE_BYTES",
    "MAX_TOTAL_BYTES", "BodySwayDynamicSeamBundleContractV2",
    "BodySwayDynamicSeamBundleContractV2Error",
    "build_body_sway_dynamic_seam_bundle_contract_v2",
]
