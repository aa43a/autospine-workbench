"""URL-bound exact P10.6b v2 inputs for automatic P10.7a v2 jobs."""

from __future__ import annotations

from dataclasses import dataclass
import re

from .manifest_artifacts import require_safe_token
from .motion_instance_v3_bundle_contract_v2 import DOCUMENT_NAMES
from .motion_instance_v3_bundle_reader_v2 import (
    MotionInstanceV3BundleReaderV2,
    VerifiedMotionInstanceV3BundleV2,
)
from .p10_motion_instance_v3_job_v2 import P10MotionInstanceV3JobStoreV2


_SHA = re.compile(r"^[0-9a-f]{64}$")


class P10Spine42V3AutoInputsV2Error(RuntimeError):
    """Raised when the URL-bound P10.6b v2 result cannot be admitted."""

    def __init__(self, message, *, failure_code="invalid_upstream",
                 terminal=True):
        super().__init__(message)
        self.failure_code, self.terminal = failure_code, terminal


@dataclass(frozen=True, slots=True)
class P10Spine42V3AutoInputsV2:
    job_id: str
    safety_run_id: str
    dynamic_run_id: str
    motion_run_id: str
    project_id: str
    motion_instance_v3_sha256: str
    motion_instance_v3_bundle_sha256: str

    @property
    def identity(self):
        return {
            key: getattr(self, key) for key in (
                "job_id", "safety_run_id", "dynamic_run_id",
                "motion_run_id", "project_id",
                "motion_instance_v3_sha256",
                "motion_instance_v3_bundle_sha256",
            )
        }


def resolve_p10_spine42_v3_auto_inputs_v2(
    state_root, job_id: str, safety_run_id: str, dynamic_run_id: str,
    motion_run_id: str,
) -> P10Spine42V3AutoInputsV2:
    """Read one sealed P10.6b journal receipt; never replay its bundle."""

    try:
        row = P10MotionInstanceV3JobStoreV2(state_root).load(motion_run_id)
        return _inputs_from_completed_row(
            row, job_id, safety_run_id, dynamic_run_id, motion_run_id,
        )
    except P10Spine42V3AutoInputsV2Error:
        raise
    except OSError as exc:
        raise P10Spine42V3AutoInputsV2Error(
            "Automatic P10.7a v2 inputs are temporarily unavailable",
            failure_code="source_unavailable", terminal=False,
        ) from exc
    except Exception as exc:
        raise P10Spine42V3AutoInputsV2Error(
            "Automatic P10.7a v2 inputs failed closed"
        ) from exc


def load_verified_p10_spine42_v3_motion_v2(
    state_root, inputs: P10Spine42V3AutoInputsV2,
) -> VerifiedMotionInstanceV3BundleV2:
    """Exact-read P10.6b once and bind it to the sealed journal receipt."""

    try:
        if type(inputs) is not P10Spine42V3AutoInputsV2:
            raise P10Spine42V3AutoInputsV2Error(
                "P10.7a v2 exact source request is invalid"
            )
        row = P10MotionInstanceV3JobStoreV2(state_root).load(
            inputs.motion_run_id
        )
        current = _inputs_from_completed_row(
            row, inputs.job_id, inputs.safety_run_id,
            inputs.dynamic_run_id, inputs.motion_run_id,
        )
        if current != inputs:
            raise P10Spine42V3AutoInputsV2Error(
                "P10.6b v2 sealed source receipt drifted"
            )
        verified = MotionInstanceV3BundleReaderV2(state_root).load(
            inputs.project_id, inputs.motion_instance_v3_sha256,
            inputs.motion_instance_v3_bundle_sha256,
        )
        _require_verified_matches_receipt(
            verified, row.events[-1]["result"], inputs,
        )
        return verified
    except P10Spine42V3AutoInputsV2Error:
        raise
    except OSError as exc:
        raise P10Spine42V3AutoInputsV2Error(
            "Automatic P10.7a v2 exact source is temporarily unavailable",
            failure_code="source_unavailable", terminal=False,
        ) from exc
    except Exception as exc:
        raise P10Spine42V3AutoInputsV2Error(
            "Automatic P10.7a v2 exact source failed closed"
        ) from exc


def _inputs_from_completed_row(row, job, safety, dynamic, motion):
    if getattr(row, "run_id", None) != motion:
        raise P10Spine42V3AutoInputsV2Error(
            "P10.6b v2 journal address differs"
        )
    if any(row.request.get(key) != value for key, value in (
        ("job_id", job), ("safety_run_id", safety),
        ("dynamic_run_id", dynamic),
    )):
        raise P10Spine42V3AutoInputsV2Error(
            "P10.6b v2 run belongs to another upstream chain"
        )
    if row.status != "completed":
        raise P10Spine42V3AutoInputsV2Error(
            "P10.6b v2 run is not complete",
            failure_code="source_not_ready", terminal=False,
        )
    events = getattr(row, "events", ())
    result = events[-1].get("result") if events else None
    _require_completed_receipt(result, row.request)
    return P10Spine42V3AutoInputsV2(
        job, safety, dynamic, motion, result["project_id"],
        result["motion_instance_v3_sha256"], result["bundle_sha256"],
    )


def _require_completed_receipt(result, request):
    fields = {
        "project_id", "clip_id", "motion_instance_v3_sha256",
        "bundle_sha256", "run_sha256", "inventory", "reused",
    }
    valid = type(result) is dict and set(result) == fields \
        and result.get("project_id") == request.get("project_id") \
        and all(_SHA.fullmatch(str(result.get(key))) for key in (
            "motion_instance_v3_sha256", "bundle_sha256", "run_sha256",
        )) and result.get("inventory") == list(DOCUMENT_NAMES) \
        and type(result.get("reused")) is bool
    try:
        if valid:
            require_safe_token(result["project_id"], "P10.6b project")
            require_safe_token(result["clip_id"], "P10.6b clip")
    except Exception:
        valid = False
    if not valid:
        raise P10Spine42V3AutoInputsV2Error(
            "P10.6b v2 sealed completed receipt is invalid"
        )


def _require_verified_matches_receipt(verified, result, inputs):
    if type(verified) is not VerifiedMotionInstanceV3BundleV2 \
            or verified.project_id != inputs.project_id \
            or verified.clip_id != result["clip_id"] \
            or verified.motion_instance_v3_sha256 \
                != inputs.motion_instance_v3_sha256 \
            or verified.bundle_sha256 \
                != inputs.motion_instance_v3_bundle_sha256 \
            or verified.run_sha256 != result["run_sha256"] \
            or list(verified.inventory) != result["inventory"]:
        raise P10Spine42V3AutoInputsV2Error(
            "P10.6b v2 exact bundle differs from its sealed receipt"
        )


__all__ = [
    "P10Spine42V3AutoInputsV2", "P10Spine42V3AutoInputsV2Error",
    "load_verified_p10_spine42_v3_motion_v2",
    "resolve_p10_spine42_v3_auto_inputs_v2",
]
