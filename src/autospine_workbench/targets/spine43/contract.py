"""Pinned 4.3.26 target for the audited common region/mesh/P5 subset."""
from collections.abc import Mapping
import hashlib
import json

from ...spine42_contract import require_spine42_inputs

SPINE_MAJOR_MINOR = "4.3"
SPINE_JSON_VERSION = "4.3.26"
SPINE_RUNTIME_PACKAGE = "@esotericsoftware/spine-player"
SPINE_RUNTIME_VERSION = "4.3.13"
ADAPTER_ID = "autospine-spine43-json-adapter"
ADAPTER_VERSION = "1.0.0"


class Spine43ContractError(ValueError):
    def __init__(self, reason_code="spine43_input_unsupported"):
        self.reason_code = reason_code
        super().__init__(reason_code)


def spine43_target_profile():
    """Editor JSON version and independently versioned runtime package pin."""
    return {
        "adapter": {"id": ADAPTER_ID, "version": ADAPTER_VERSION},
        "skeleton_format": "json", "spine_major_minor": SPINE_MAJOR_MINOR,
        "skeleton_json_version": SPINE_JSON_VERSION,
        "runtime": {"package": SPINE_RUNTIME_PACKAGE, "version": SPINE_RUNTIME_VERSION},
        "supported_subset": "reviewed_region_weighted_mesh_p5_bone_motion",
        "constraints": "unsupported", "runtime_verification": "not_run",
    }


def require_spine43_inputs(rig, *, motion_instance=None, target_profile=None):
    """Reuse existing neutral RigIR/P5 safety checks, not 4.2 output identity.

    The common input subset excludes all constraints and embedded animation.
    4.3 constraints use a different JSON structure and cannot be passed through.
    """
    try:
        require_spine42_inputs(rig, motion_instance=motion_instance, target_profile=target_profile)
    except (KeyError, TypeError, ValueError, RuntimeError, OverflowError) as exc:
        raise Spine43ContractError() from exc


def canonical_spine43_json(document):
    if not isinstance(document, Mapping):
        raise Spine43ContractError("spine43_document_invalid")
    try:
        return json.dumps(dict(document), ensure_ascii=False, allow_nan=False,
                          sort_keys=True, separators=(",", ":")).encode("utf-8")
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise Spine43ContractError("spine43_document_invalid") from exc


def spine43_json_sha256(document):
    return hashlib.sha256(canonical_spine43_json(document)).hexdigest()
