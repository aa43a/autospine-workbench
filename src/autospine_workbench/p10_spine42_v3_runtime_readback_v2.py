"""Exact local-address readback shared by live execution and recovery."""

from __future__ import annotations

import json
from pathlib import Path

from .spine42_v3_runtime_evidence_contract_v2 import MANIFEST_NAME
from .spine42_v3_runtime_reader_v2 import (
    Spine42V3RuntimeReaderV2Error,
    _require_issued_spine42_v3_runtime_reader_v2,
)


_RUNTIME_NAMESPACE = "spine42-v3-runtime-v2"


def require_p10_spine42_v3_runtime_readback_v2(
    reader, snapshot, state_root,
):
    """Return the exact address only for local reader-issued evidence."""

    source = snapshot.request.document["source"]
    address = snapshot.head["capture_address"]
    evidence = reader.load(
        address["project_id"], address["skeleton_json_sha256"],
        address["spine42_v3_bundle_sha256"],
        address["capture_bundle_sha256"],
    )
    path, bundle = _require_issued_spine42_v3_runtime_reader_v2(evidence)
    actual_address = {
        "project_id": bundle.project_id,
        "skeleton_json_sha256": bundle.skeleton_json_sha256,
        "spine42_v3_bundle_sha256": bundle.spine42_v3_bundle_sha256,
        "capture_bundle_sha256": bundle.bundle_sha256,
    }
    actual_source = {
        "project_id": bundle.project_id,
        "clip_id": bundle.clip_id,
        "skeleton_json_sha256": bundle.skeleton_json_sha256,
        "spine42_v3_bundle_sha256": bundle.spine42_v3_bundle_sha256,
    }
    if actual_address != address or actual_source != source \
            or not _same_execution_environment(bundle, snapshot.request) \
            or not _is_local_address(path, state_root, address):
        raise Spine42V3RuntimeReaderV2Error(
            "Runtime exact readback source differs")
    return dict(address)


def _same_execution_environment(bundle, request):
    try:
        manifest = json.loads(dict(bundle.file_items)[MANIFEST_NAME])
        expected_runtime = request.document["runtime"]
        actual_runtime = manifest["runtime"]
        runtime_fields = (
            "package", "version", "javascript_sha256",
            "stylesheet_sha256", "package_json_sha256", "license_sha256",
            "license_file_presence_is_authorization",
        )
        return all(actual_runtime[name] == expected_runtime[name]
                   for name in runtime_fields) \
            and actual_runtime["license_acknowledged"] is True \
            and manifest["browser"] == request.document["browser"]
    except (KeyError, TypeError, UnicodeError, ValueError):
        return False


def _is_local_address(path, state_root, address):
    try:
        root = Path(state_root).resolve(strict=True)
        expected = root.joinpath(
            "builds", address["project_id"], _RUNTIME_NAMESPACE,
            address["skeleton_json_sha256"],
            address["spine42_v3_bundle_sha256"],
            address["capture_bundle_sha256"],
        )
        return Path(path).resolve(strict=True) == expected.resolve(strict=True)
    except (OSError, RuntimeError, TypeError, ValueError):
        return False


__all__ = ["require_p10_spine42_v3_runtime_readback_v2"]
