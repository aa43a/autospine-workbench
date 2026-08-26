"""Deterministic bulk-evidence seals for BodySwayProbeReport compilation.

These digests are compiler seals over every sampled row.  They intentionally
do not claim that a standalone report embeds enough data to replay the probe.
"""

from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
from typing import Any

from .body_sway_probe_geometry import BodySwayGeometrySample
from .body_sway_probe_math import BodySwayLoopAudit
from .resolved_project import canonical_sha256


SCHEDULE_HASH_DOMAIN = "autospine-body-sway-tick-schedule/v1"
STREAM_HASH_DOMAIN = "autospine-body-sway-sample-stream/v1"
CHECK_HASH_DOMAIN = "autospine-body-sway-check-evidence/v1"
CHECK_SAMPLE_HASH_DOMAIN = "autospine-body-sway-check-sample/v1"
_STRUCTURAL_CHECKS = (
    "fk_finite",
    "sampled_mesh_deformation",
    "sampled_canvas_containment",
    "shared_index_internal_continuity",
)

class BodySwayProbeReportEvidenceError(ValueError):
    """Raised when compiler evidence is incomplete or cross-wired."""


def tick_schedule_sha256(ticks: tuple[int, ...]) -> str:
    """Seal the complete ordered tick schedule under a pinned domain."""

    if len(ticks) < 2 or ticks[0] != 0 \
            or any(type(tick) is not int for tick in ticks) \
            or any(left >= right for left, right in zip(ticks, ticks[1:])):
        raise BodySwayProbeReportEvidenceError("Tick schedule is invalid")
    return canonical_sha256({"domain": SCHEDULE_HASH_DOMAIN, "ticks": list(ticks)})


class SampleStreamSealer:
    """Incrementally seal inventories and every full sampled-pose digest."""

    def __init__(
        self, *, rig_bone_ids: tuple[str, ...],
        rotation_bone_ids: tuple[str, ...],
        overlay_bone_ids: tuple[str, ...],
        attachments: tuple[tuple[str, str], ...],
    ) -> None:
        self._digest = _seed(STREAM_HASH_DOMAIN, {
            "rig_bone_ids": list(rig_bone_ids),
            "rotation_bone_ids": list(rotation_bone_ids),
            "overlay_bone_ids": list(overlay_bone_ids),
            "attachments": [
                {"attachment_id": identifier, "type": kind}
                for identifier, kind in attachments
            ],
        })
        self._previous_tick = -1
        self._count = 0

    def observe(self, tick: int, pose_sha256: str) -> None:
        if type(tick) is not int or tick <= self._previous_tick \
                or not _is_digest(pose_sha256):
            raise BodySwayProbeReportEvidenceError(
                "Sample-stream pose evidence is invalid"
            )
        _chain(self._digest, {
            "domain": STREAM_HASH_DOMAIN,
            "index": self._count,
            "tick": tick,
            "full_pose_sha256": pose_sha256,
        })
        self._previous_tick = tick
        self._count += 1

    def finish(self, expected_count: int) -> str:
        if type(expected_count) is not int or self._count != expected_count:
            raise BodySwayProbeReportEvidenceError(
                "Sample-stream evidence count differs from the schedule"
            )
        return self._digest.hexdigest()


class StructuralEvidenceAccumulator:
    """Aggregate all public geometry results without retaining full poses."""

    def __init__(
        self, *, rig_bone_ids: tuple[str, ...],
        attachments: tuple[tuple[str, str], ...],
    ) -> None:
        self.rig_bone_ids = _sorted_unique(rig_bone_ids, "rig bones", nonempty=True)
        self.attachments = _attachments(attachments)
        self.mesh_ids = tuple(row[0] for row in self.attachments if row[1] == "mesh")
        self._digests = {
            check_id: _seed(CHECK_HASH_DOMAIN, {"check_id": check_id})
            for check_id in _STRUCTURAL_CHECKS
        }
        self._failures = {check_id: set() for check_id in _STRUCTURAL_CHECKS}
        self._previous_tick = -1
        self._count = 0

    def observe(self, result: BodySwayGeometrySample) -> None:
        if type(result) is not BodySwayGeometrySample \
                or result.tick <= self._previous_tick:
            raise BodySwayProbeReportEvidenceError(
                "Geometry evidence must be exact and tick ordered"
            )
        bone_ids = tuple(row.bone_id for row in result.bones)
        kinds = tuple((row.attachment_id, row.attachment_type)
                      for row in result.attachments)
        if bone_ids != self.rig_bone_ids or kinds != self.attachments:
            raise BodySwayProbeReportEvidenceError(
                "Geometry evidence inventory differs from the admitted rig"
            )
        payloads, failures = _sample_evidence(result)
        for check_id in _STRUCTURAL_CHECKS:
            _chain(self._digests[check_id], {
                "domain": CHECK_SAMPLE_HASH_DOMAIN,
                "check_id": check_id,
                "tick": result.tick,
                "evidence": payloads[check_id],
            })
            if failures[check_id]:
                self._failures[check_id].add(result.tick)
        self._previous_tick = result.tick
        self._count += 1

    def checks(
        self, *, loop_audit: BodySwayLoopAudit,
        start_pose_state_sha256: str, end_pose_state_sha256: str,
        expected_sample_count: int,
    ) -> list[dict[str, Any]]:
        if type(loop_audit) is not BodySwayLoopAudit \
                or not _is_digest(start_pose_state_sha256) \
                or not _is_digest(end_pose_state_sha256) \
                or self._count != expected_sample_count:
            raise BodySwayProbeReportEvidenceError(
                "Structural evidence is incomplete"
            )
        loop = _loop_check(
            loop_audit, start_pose_state_sha256, end_pose_state_sha256
        )
        rows = [loop]
        rows.append(self._computed("fk_finite", len(self.rig_bone_ids)))
        rows.append(self._computed("sampled_mesh_deformation", len(self.mesh_ids)))
        rows.append(self._computed("sampled_canvas_containment", len(self.attachments)))
        rows.append(self._computed(
            "shared_index_internal_continuity", len(self.mesh_ids)
        ))
        rows.extend((
            _unobservable("inter_attachment_seams", "reviewed_seam_anchors_missing"),
            _unobservable("visual_quality", "manual_runtime_preview_required"),
        ))
        return rows

    def _computed(self, check_id: str, subject_count: int) -> dict[str, Any]:
        if subject_count == 0:
            return _not_applicable(check_id, "reviewed_noop")
        failures = len(self._failures[check_id])
        status = "rejected" if failures else "passed"
        return {
            "check_id": check_id,
            "status": status,
            "reason_code": f"sampled_check_{status}",
            "subject_count": subject_count,
            "sample_count": self._count,
            "failure_count": failures,
            "evidence_sha256": self._digests[check_id].hexdigest(),
        }


def _sample_evidence(result: BodySwayGeometrySample):
    meshes = tuple(row for row in result.attachments
                   if row.attachment_type == "mesh")
    payloads = {
        "fk_finite": [asdict(row) for row in result.bones],
        "sampled_mesh_deformation": [
            {
                "attachment_id": row.attachment_id,
                "assessment": asdict(row.deformation) if row.deformation else None,
            }
            for row in meshes
        ],
        "sampled_canvas_containment": {
            "attachments": [
                {
                    "attachment_id": row.attachment_id,
                    "status": row.canvas_status,
                    "outside_vertex_indices": list(row.outside_vertex_indices),
                }
                for row in result.attachments
            ],
            "failures": [asdict(row) for row in result.canvas_failures],
        },
        "shared_index_internal_continuity": [
            {
                "attachment_id": row.attachment_id,
                "status": row.shared_index_topology_status,
            }
            for row in meshes
        ],
    }
    failures = {
        "fk_finite": result.fk_status != "passed",
        "sampled_mesh_deformation": any(
            row.deformation is None or row.deformation.status != "passed"
            for row in meshes
        ),
        "sampled_canvas_containment": any(
            row.canvas_status != "passed" for row in result.attachments
        ),
        "shared_index_internal_continuity": any(
            row.shared_index_topology_status != "passed" for row in meshes
        ),
    }
    return payloads, failures


def _loop_check(audit, start_pose_sha, end_pose_sha):
    if not audit.overlay_closed:
        raise BodySwayProbeReportEvidenceError("Loop overlay endpoints are open")
    if not audit.loop:
        return _not_applicable("loop_closure", "clip_not_looping")
    audit_closed = audit.status == "closed"
    visible_closed = start_pose_sha == end_pose_sha
    if audit.status not in {"closed", "rejected"} \
            or not audit.overlay_closed or audit_closed != visible_closed:
        raise BodySwayProbeReportEvidenceError(
            "Loop audit differs from its visible endpoint pose seals"
        )
    status = "passed" if audit_closed else "rejected"
    evidence = canonical_sha256({
        "domain": CHECK_HASH_DOMAIN,
        "check_id": "loop_closure",
        "audit": audit.to_dict(),
        "start_visible_pose_state_sha256": start_pose_sha,
        "end_visible_pose_state_sha256": end_pose_sha,
    })
    return {
        "check_id": "loop_closure", "status": status,
        "reason_code": f"sampled_check_{status}", "subject_count": 1,
        "sample_count": 2, "failure_count": int(status == "rejected"),
        "evidence_sha256": evidence,
    }


def _not_applicable(check_id, reason):
    return {"check_id": check_id, "status": "not_applicable",
            "reason_code": reason, "subject_count": 0, "sample_count": 0,
            "failure_count": 0, "evidence_sha256": None}


def _unobservable(check_id, reason):
    row = _not_applicable(check_id, reason)
    row["status"] = "unobservable"
    return row


def _seed(domain: str, payload: Any):
    digest = hashlib.sha256()
    digest.update(_canonical({"domain": domain, "header": payload}))
    return digest


def _chain(digest, payload: Any) -> None:
    digest.update(bytes.fromhex(canonical_sha256(payload)))


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, allow_nan=False,
                      sort_keys=True, separators=(",", ":")).encode("utf-8")


def _is_digest(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 \
        and all(character in "0123456789abcdef" for character in value)


def _sorted_unique(value, label, *, nonempty=False):
    if type(value) is not tuple or nonempty and not value \
            or any(not isinstance(item, str) or not item for item in value) \
            or value != tuple(sorted(value)) or len(value) != len(set(value)):
        raise BodySwayProbeReportEvidenceError(f"{label} inventory is invalid")
    return value


def _attachments(value):
    if type(value) is not tuple or any(
        type(row) is not tuple or len(row) != 2 or row[1] not in {"region", "mesh"}
        for row in value
    ):
        raise BodySwayProbeReportEvidenceError("Attachment inventory is invalid")
    identifiers = tuple(row[0] for row in value)
    _sorted_unique(identifiers, "attachment")
    return value
