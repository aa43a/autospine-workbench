"""Bounded startup and bind-failure lifecycle for workbench managers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from .p10_capture_job_manager import P10CaptureJobManagerError
from .p10_dynamic_seam_manager_v2 import P10DynamicSeamManagerV2Error
from .p10_motion_instance_v3_manager_v2 import (
    P10MotionInstanceV3ManagerV2Error,
)
from .p10_safety_analysis_manager_v2 import (
    P10SafetyAnalysisManagerV2Error,
)
from .p10_spine42_v3_manager_v2 import P10Spine42V3ManagerV2Error
from .p10_spine42_v3_runtime_manager_v2 import (
    P10Spine42V3RuntimeManagerV2Error,
)


Factory = Callable[..., Any]


@dataclass(frozen=True, slots=True)
class WorkbenchManagerSet:
    capture: Any
    safety_analysis_v2: Any
    dynamic_seam_v2: Any
    motion_instance_v3_v2: Any
    spine42_v3_v2: Any
    spine42_v3_runtime_v2: Any

    def close_after_bind_failure(self) -> None:
        _close_in_order(
            self.spine42_v3_runtime_v2,
            self.spine42_v3_v2,
            self.motion_instance_v3_v2,
            self.dynamic_seam_v2,
            self.safety_analysis_v2,
            self.capture,
        )


def start_workbench_managers(
    store: Any,
    capture_factory: Factory,
    safety_factory: Factory,
    dynamic_seam_factory: Factory,
    motion_instance_factory: Factory,
    spine42_factory: Factory,
    spine42_runtime_factory: Factory,
) -> WorkbenchManagerSet:
    """Start managers in dependency order and close predecessors on failure."""

    try:
        capture = capture_factory(store)
    except P10CaptureJobManagerError as exc:
        raise OSError(
            "P10 Runtime capture manager could not start."
        ) from exc
    try:
        safety = safety_factory(capture, store)
    except P10SafetyAnalysisManagerV2Error as exc:
        _close_in_order(capture)
        raise OSError(
            "P10.4b v2 safety manager could not start."
        ) from exc
    try:
        dynamic_seam = dynamic_seam_factory(store)
    except P10DynamicSeamManagerV2Error as exc:
        _close_in_order(safety, capture)
        raise OSError(
            "P10.5d v2 dynamic seam manager could not start."
        ) from exc
    try:
        motion_instance = motion_instance_factory(store)
    except P10MotionInstanceV3ManagerV2Error as exc:
        _close_in_order(dynamic_seam, safety, capture)
        raise OSError(
            "P10.6b v2 MotionInstance manager could not start."
        ) from exc
    try:
        spine42 = spine42_factory(store)
    except P10Spine42V3ManagerV2Error as exc:
        _close_in_order(motion_instance, dynamic_seam, safety, capture)
        raise OSError(
            "P10.7a v2 Spine adapter manager could not start."
        ) from exc
    try:
        spine42_runtime = spine42_runtime_factory(store)
    except P10Spine42V3RuntimeManagerV2Error as exc:
        _close_in_order(
            spine42, motion_instance, dynamic_seam, safety, capture,
        )
        raise OSError(
            "P10.7b v2 Runtime manager could not start."
        ) from exc
    return WorkbenchManagerSet(
        capture=capture,
        safety_analysis_v2=safety,
        dynamic_seam_v2=dynamic_seam,
        motion_instance_v3_v2=motion_instance,
        spine42_v3_v2=spine42,
        spine42_v3_runtime_v2=spine42_runtime,
    )


def _close_in_order(*managers: Any) -> None:
    for manager in managers:
        try:
            manager.close()
        except Exception:
            # Startup must preserve the original failure while still giving
            # every already-started manager one bounded close attempt.
            continue


__all__ = ["WorkbenchManagerSet", "start_workbench_managers"]
