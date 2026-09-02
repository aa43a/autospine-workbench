"""Cheap exact-byte verification for an already verified P10.5d v2 bundle."""

from __future__ import annotations

import hashlib
import json

from .body_sway_dynamic_seam_bundle_contract_v2 import (
    BUNDLE_ADDRESS_DOMAIN,
    DOCUMENT_NAMES,
    MANIFEST_MAX_BYTES,
    MAX_PROBE_BYTES,
    MAX_SOURCE_BYTES as MAX_BUNDLE_SOURCE_BYTES,
    MAX_TOTAL_BYTES,
)
from .body_sway_dynamic_seam_bundle_reader_v2 import (
    VerifiedBodySwayDynamicSeamBundleV2,
)
from .body_sway_dynamic_seam_profile_v2 import (
    FORMAT as SOURCE_FORMAT,
    FORMAT_VERSION as SOURCE_FORMAT_VERSION,
    MAX_SOURCE_JSON_DEPTH,
    MAX_SOURCE_JSON_NODES,
    SOURCE_FIELDS,
    body_sway_dynamic_seam_source_sha256_v2,
)
from .body_sway_dynamic_seam_probe_validation_v2 import (
    MAX_DOCUMENT_JSON_DEPTH,
    MAX_DOCUMENT_JSON_NODES,
)
from .body_sway_dynamic_seam_evidence_profile_v2 import (
    FORMAT as PROBE_FORMAT,
    FORMAT_VERSION as PROBE_FORMAT_VERSION,
)
from .immutable_bundle_fs import framed_bundle_sha256
from .seam_anchor_review_json import (
    canonical_json_bytes,
    require_bounded_json_tree,
)


PROBE_FIELDS = {
    "format", "format_version", "project_id", "clip_id", "source",
    "problem", "segments", "analyzer", "claims", "status",
    "release_gate", "summary",
}
FILE_LIMITS = (MAX_BUNDLE_SOURCE_BYTES, MAX_PROBE_BYTES, MANIFEST_MAX_BYTES)


class BodySwayMotionConsumerDynamicBundleV2Error(ValueError):
    """Raised when a verified value's exact snapshot bytes are inconsistent."""


def require_exact_body_sway_dynamic_seam_bundle_v2(bundle):
    """Check canonical source/probe/manifest addresses without redoing proof."""

    try:
        if type(bundle) is not VerifiedBodySwayDynamicSeamBundleV2:
            raise BodySwayMotionConsumerDynamicBundleV2Error(
                "Motion consumer v2 requires a verified P10.5d v2 bundle"
            )
        items = bundle._documents
        if type(items) is not tuple or len(items) != len(DOCUMENT_NAMES) \
                or any(
                    type(item) is not tuple or len(item) != 2
                    or item[0] != DOCUMENT_NAMES[index]
                    or type(item[1]) is not bytes
                    or len(item[1]) > FILE_LIMITS[index]
                    for index, item in enumerate(items)
                ):
            raise BodySwayMotionConsumerDynamicBundleV2Error(
                "P10.5d v2 bundle inventory is invalid"
            )
        files = dict(items)
        if sum(map(len, files.values())) > MAX_TOTAL_BYTES:
            raise BodySwayMotionConsumerDynamicBundleV2Error(
                "P10.5d v2 bundle exceeds its total byte limit"
            )
        source, probe, manifest = tuple(
            _canonical_object(files[name], name) for name in DOCUMENT_NAMES
        )
        _require_documents(source, probe)
        require_bounded_json_tree(
            source, max_nodes=MAX_SOURCE_JSON_NODES,
            max_depth=MAX_SOURCE_JSON_DEPTH,
        )
        require_bounded_json_tree(
            probe, max_nodes=MAX_DOCUMENT_JSON_NODES,
            max_depth=MAX_DOCUMENT_JSON_DEPTH,
        )
        source_sha = hashlib.sha256(files[DOCUMENT_NAMES[0]]).hexdigest()
        probe_sha = hashlib.sha256(files[DOCUMENT_NAMES[1]]).hexdigest()
        expected_manifest = _manifest(
            source, source_sha, probe_sha,
            files[DOCUMENT_NAMES[0]], files[DOCUMENT_NAMES[1]],
        )
        bundle_sha = framed_bundle_sha256(
            BUNDLE_ADDRESS_DOMAIN, DOCUMENT_NAMES, files,
        )
        if canonical_json_bytes(manifest) != canonical_json_bytes(
            expected_manifest
        ) or (
            bundle.project_id, bundle.clip_id, bundle.source_set_sha256,
            bundle.source_document_sha256, bundle.probe_sha256,
            bundle.bundle_sha256,
        ) != (
            source["project_id"], source["clip_id"],
            source["source_set_sha256"], source_sha, probe_sha, bundle_sha,
        ):
            raise BodySwayMotionConsumerDynamicBundleV2Error(
                "P10.5d v2 bytes differ from their exact address"
            )
        return source, probe
    except BodySwayMotionConsumerDynamicBundleV2Error:
        raise
    except (
        AttributeError, KeyError, OverflowError, RecursionError,
        RuntimeError, TypeError, UnicodeError, ValueError,
    ) as exc:
        raise BodySwayMotionConsumerDynamicBundleV2Error(
            f"P10.5d v2 exact snapshot verification failed: {exc}"
        ) from exc


def _canonical_object(data, label):
    value = json.loads(data)
    if type(value) is not dict or canonical_json_bytes(value) != data:
        raise BodySwayMotionConsumerDynamicBundleV2Error(
            f"P10.5d v2 {label} bytes are not canonical"
        )
    return value


def _require_documents(source, probe):
    if set(source) != SOURCE_FIELDS \
            or source.get("format") != SOURCE_FORMAT \
            or source.get("format_version") != SOURCE_FORMAT_VERSION \
            or set(probe) != PROBE_FIELDS \
            or probe.get("format") != PROBE_FORMAT \
            or probe.get("format_version") != PROBE_FORMAT_VERSION \
            or probe.get("project_id") != source.get("project_id") \
            or probe.get("clip_id") != source.get("clip_id") \
            or canonical_json_bytes(probe.get("source")) \
                != canonical_json_bytes(source) \
            or body_sway_dynamic_seam_source_sha256_v2(source) \
                != source.get("source_set_sha256"):
        raise BodySwayMotionConsumerDynamicBundleV2Error(
            "P10.5d v2 source or probe closure is inconsistent"
        )


def _manifest(source, source_sha, probe_sha, source_bytes, probe_bytes):
    return {
        "format": "autospine-body-sway-dynamic-seam-bundle-manifest",
        "format_version": 2, "project_id": source["project_id"],
        "clip_id": source["clip_id"],
        "source_set_sha256": source["source_set_sha256"],
        "source_document_sha256": source_sha, "probe_sha256": probe_sha,
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


def _entry(name, data, digest):
    return {"name": name, "sha256": digest, "size_bytes": len(data)}


__all__ = [
    "BodySwayMotionConsumerDynamicBundleV2Error",
    "require_exact_body_sway_dynamic_seam_bundle_v2",
]
