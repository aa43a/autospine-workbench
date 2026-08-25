"""Pure orchestration for one exact P3/P4/MotionIR retarget evidence chain."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
import re
from typing import Any

from .ik_bundle_reader import VerifiedIkBundleReader
from .ik_target_geometry import SOURCE_IDENTITY_FIELDS
from .mesh_bundle_reader import VerifiedMeshBundleReader
from .motion_bundle_reader import VerifiedMotionBundleReader
from .motion_instance_validation import require_motion_instance
from .motion_mesh_regression import (
    build_motion_mesh_regression,
    require_motion_mesh_regression,
)
from .motion_retarget_compiler import compile_motion_instance
from .motion_retarget_report import (
    build_motion_retarget_report,
    require_motion_retarget_report,
)
from .motion_retarget_run import require_retarget_run
from .motion_target_profile import compile_motion_target_profile
from .motion_target_validation import require_motion_target_profile
from .resolved_project import canonical_sha256


_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class VerifiedMotionRetargetPipelineError(RuntimeError):
    """Raised when an exact P5 retarget cannot pass every evidence gate."""


@dataclass(frozen=True, slots=True)
class VerifiedMotionRetargetPipelineResult:
    """Five isolated canonical documents and their complete SHA inventories."""

    project_id: str
    clip_id: str
    summary: str
    _target_json: str = field(repr=False)
    _instance_json: str = field(repr=False)
    _run_json: str = field(repr=False)
    _report_json: str = field(repr=False)
    _mesh_json: str = field(repr=False)
    _input_sha_json: str = field(repr=False)
    _output_sha_json: str = field(repr=False)

    @property
    def target_profile(self) -> dict[str, Any]:
        return json.loads(self._target_json)

    @property
    def motion_instance(self) -> dict[str, Any]:
        return json.loads(self._instance_json)

    @property
    def retarget_run(self) -> dict[str, Any]:
        return json.loads(self._run_json)

    @property
    def retarget_report(self) -> dict[str, Any]:
        return json.loads(self._report_json)

    @property
    def mesh_regression(self) -> dict[str, Any]:
        return json.loads(self._mesh_json)

    @property
    def input_sha256s(self) -> dict[str, str]:
        return json.loads(self._input_sha_json)

    @property
    def output_sha256s(self) -> dict[str, str]:
        return json.loads(self._output_sha_json)


@dataclass(frozen=True, slots=True)
class VerifiedMotionRetargetPipeline:
    """Read only explicit content addresses and produce no filesystem state."""

    state_root: Path

    def __post_init__(self) -> None:
        object.__setattr__(self, "state_root", Path(self.state_root))

    def build(
        self,
        project_id: str,
        p3_rig_sha256: str,
        p3_bundle_sha256: str,
        p4_profile_sha256: str,
        p4_bundle_sha256: str,
        motion_clip_sha256: str,
        motion_bundle_sha256: str,
    ) -> VerifiedMotionRetargetPipelineResult:
        """Strictly load, retarget, and gate one immutable motion/rig pair."""

        try:
            requested = _requested(
                project_id, p3_rig_sha256, p3_bundle_sha256,
                p4_profile_sha256, p4_bundle_sha256,
                motion_clip_sha256, motion_bundle_sha256,
            )
            mesh = VerifiedMeshBundleReader(self.state_root).load(
                requested["project_id"], requested["p3_rig_sha256"],
                requested["p3_bundle_sha256"],
            )
            ik = VerifiedIkBundleReader(self.state_root).load(
                requested["project_id"], requested["p4_profile_sha256"],
                requested["p4_bundle_sha256"],
            )
            motion = VerifiedMotionBundleReader(self.state_root).load(
                requested["motion_clip_sha256"],
                requested["motion_bundle_sha256"],
            )
            _require_addresses(requested, mesh, ik, motion)
            _require_p3_p4_chain(mesh, ik)

            target = compile_motion_target_profile(ik, mesh)
            require_motion_target_profile(
                target.document, verified_ik=ik, verified_mesh=mesh
            )
            retargeted = compile_motion_instance(motion, target)
            require_motion_instance(
                retargeted.instance, target_profile=target.document
            )
            require_retarget_run(retargeted.run, instance=retargeted.instance)
            report = build_motion_retarget_report(motion, target, retargeted)
            if report.document.get("status") != "passed":
                raise VerifiedMotionRetargetPipelineError(
                    "Motion retarget evidence did not pass"
                )
            require_motion_retarget_report(
                report.document, verified_motion=motion,
                target_profile=target, retargeted=retargeted,
            )
            mesh_report = build_motion_mesh_regression(
                retargeted.instance, target.document, mesh
            )
            if mesh_report.document.get("status") != "passed":
                raise VerifiedMotionRetargetPipelineError(
                    "Motion mesh regression rejected the clip"
                )
            require_motion_mesh_regression(
                mesh_report.document, instance=retargeted.instance,
                target_profile=target.document, verified_mesh=mesh,
            )
            inputs = _input_inventory(mesh, ik, motion)
            outputs = _output_inventory(
                target, retargeted, report, mesh_report
            )
            summary = (
                f"clip={motion.clip_id};tracks={len(retargeted.instance['tracks'])};"
                f"markers={len(retargeted.instance['markers'])};"
                f"mesh={mesh_report.document['summary']}"
            )
            return VerifiedMotionRetargetPipelineResult(
                project_id=requested["project_id"], clip_id=motion.clip_id,
                summary=summary, _target_json=_encode(target.document),
                _instance_json=_encode(retargeted.instance),
                _run_json=_encode(retargeted.run),
                _report_json=_encode(report.document),
                _mesh_json=_encode(mesh_report.document),
                _input_sha_json=_encode(inputs),
                _output_sha_json=_encode(outputs),
            )
        except VerifiedMotionRetargetPipelineError:
            raise
        except (
            AttributeError, KeyError, OverflowError, RuntimeError,
            TypeError, ValueError,
        ) as exc:
            raise VerifiedMotionRetargetPipelineError(
                f"Verified motion retarget pipeline failed: {exc}"
            ) from exc


def _requested(project, p3_rig, p3_bundle, p4_profile, p4_bundle,
               motion_clip, motion_bundle):
    return {
        "project_id": _identity(project, "project id", _SAFE_ID),
        "p3_rig_sha256": _identity(p3_rig, "P3 RigIR SHA", _SHA256),
        "p3_bundle_sha256": _identity(p3_bundle, "P3 bundle SHA", _SHA256),
        "p4_profile_sha256": _identity(p4_profile, "P4 profile SHA", _SHA256),
        "p4_bundle_sha256": _identity(p4_bundle, "P4 bundle SHA", _SHA256),
        "motion_clip_sha256": _identity(motion_clip, "motion clip SHA", _SHA256),
        "motion_bundle_sha256": _identity(
            motion_bundle, "motion bundle SHA", _SHA256
        ),
    }


def _require_addresses(requested, mesh, ik, motion):
    actual = {
        "project_id": mesh.project_id,
        "p3_rig_sha256": mesh.rig_sha256,
        "p3_bundle_sha256": mesh.bundle_sha256,
        "p4_profile_sha256": ik.profile_sha256,
        "p4_bundle_sha256": ik.bundle_sha256,
        "motion_clip_sha256": motion.clip_sha256,
        "motion_bundle_sha256": motion.bundle_sha256,
    }
    if actual != requested or ik.project_id != requested["project_id"]:
        raise VerifiedMotionRetargetPipelineError(
            "A verified result differs from its requested exact address"
        )


def _require_p3_p4_chain(mesh, ik):
    source = {field: getattr(mesh, field) for field in SOURCE_IDENTITY_FIELDS}
    if (
        ik.p3_rig_sha256 != mesh.rig_sha256
        or ik.p3_bundle_sha256 != mesh.bundle_sha256
        or ik.source_identities != source
    ):
        raise VerifiedMotionRetargetPipelineError(
            "Verified P4 and P3 source identity chains differ"
        )


def _input_inventory(mesh, ik, motion):
    p3 = {f"p3_{field}": getattr(mesh, field) for field in SOURCE_IDENTITY_FIELDS}
    return {
        **p3,
        "p4_profile_sha256": ik.profile_sha256,
        "p4_probes_sha256": ik.probes_sha256,
        "p4_bundle_sha256": ik.bundle_sha256,
        "motion_clip_sha256": motion.clip_sha256,
        "motion_run_sha256": motion.run_sha256,
        "motion_bundle_sha256": motion.bundle_sha256,
    }


def _output_inventory(target, retargeted, report, mesh_report):
    outputs = {
        "target_profile_sha256": target.sha256,
        "motion_instance_sha256": retargeted.instance_sha256,
        "retarget_run_identity_sha256": retargeted.run_identity_sha256,
        "retarget_run_document_sha256": retargeted.run_document_sha256,
        "retarget_report_sha256": report.sha256,
        "mesh_regression_sha256": mesh_report.sha256,
    }
    documents = {
        "target_profile_sha256": target.document,
        "motion_instance_sha256": retargeted.instance,
        "retarget_run_document_sha256": retargeted.run,
        "retarget_report_sha256": report.document,
        "mesh_regression_sha256": mesh_report.document,
    }
    if any(canonical_sha256(value) != outputs[key]
           for key, value in documents.items()):
        raise VerifiedMotionRetargetPipelineError(
            "P5 output document identity differs from canonical content"
        )
    return outputs


def _identity(value: Any, label: str, pattern: re.Pattern[str]) -> str:
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise VerifiedMotionRetargetPipelineError(f"{label} is invalid")
    return value


def _encode(value: Any) -> str:
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    )
