"""Automatic exact P10.5d v2 inputs for the P10.6b v2 job API."""

from __future__ import annotations

from dataclasses import dataclass

from .body_sway_dynamic_seam_evidence_profile_v2 import CERTIFIED_STATUS
from .p10_dynamic_seam_job_v2 import P10DynamicSeamJobStoreV2


class P10MotionInstanceV3AutoInputsV2Error(RuntimeError):
    """Raised when the URL-bound P10.5d result cannot be admitted."""

    def __init__(self, message, *, failure_code="invalid_upstream",
                 terminal=True):
        super().__init__(message)
        self.failure_code, self.terminal = failure_code, terminal


@dataclass(frozen=True, slots=True)
class P10MotionInstanceV3AutoInputsV2:
    job_id: str
    safety_run_id: str
    dynamic_run_id: str
    project_id: str
    dynamic_seam_probe_sha256: str
    dynamic_seam_bundle_sha256: str

    @property
    def identity(self):
        return {
            key: getattr(self, key) for key in (
                "job_id", "safety_run_id", "dynamic_run_id", "project_id",
                "dynamic_seam_probe_sha256",
                "dynamic_seam_bundle_sha256",
            )
        }


def resolve_p10_motion_instance_v3_auto_inputs_v2(
    state_root, job_id: str, safety_run_id: str, dynamic_run_id: str,
) -> P10MotionInstanceV3AutoInputsV2:
    """Read one immutable completed P10.5d run; never select a file or SHA."""

    try:
        row = P10DynamicSeamJobStoreV2(state_root).load(dynamic_run_id)
        request = row.request
        if request["job_id"] != job_id \
                or request["safety_run_id"] != safety_run_id:
            raise P10MotionInstanceV3AutoInputsV2Error(
                "P10.5d v2 run belongs to another upstream chain"
            )
        if row.status != "completed":
            raise P10MotionInstanceV3AutoInputsV2Error(
                "P10.5d v2 run is not complete",
                failure_code="source_not_ready", terminal=False,
            )
        result = row.events[-1]["result"]
        if result["probe_status"] != CERTIFIED_STATUS:
            raise P10MotionInstanceV3AutoInputsV2Error(
                "P10.5d v2 result is not structurally certified"
            )
        if result["project_id"] != request["project_id"]:
            raise P10MotionInstanceV3AutoInputsV2Error(
                "P10.5d v2 project identity differs"
            )
        return P10MotionInstanceV3AutoInputsV2(
            job_id, safety_run_id, dynamic_run_id, result["project_id"],
            result["probe_sha256"], result["bundle_sha256"],
        )
    except P10MotionInstanceV3AutoInputsV2Error:
        raise
    except OSError as exc:
        raise P10MotionInstanceV3AutoInputsV2Error(
            "Automatic P10.6b v2 inputs are temporarily unavailable",
            failure_code="source_unavailable", terminal=False,
        ) from exc
    except Exception as exc:
        raise P10MotionInstanceV3AutoInputsV2Error(
            "Automatic P10.6b v2 inputs failed closed"
        ) from exc


__all__ = [
    "P10MotionInstanceV3AutoInputsV2",
    "P10MotionInstanceV3AutoInputsV2Error",
    "resolve_p10_motion_instance_v3_auto_inputs_v2",
]
