"""Project-level, reproducible P3 mesh deformation probe reports."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import json
import re
from typing import Any

from .mesh_action_probe import (
    BEND_STEP_DEGREES,
    MAX_AREA_RATIO,
    MAX_BEND_DEGREES,
    MAX_EDGE_STRETCH,
    MIN_AREA_RATIO,
    MeshActionProbeError,
    run_mesh_action_probe,
)
from .mesh_contract import MeshContractError, require_mesh_compile_run
from .mesh_eligibility import HingeTarget
from .resolved_project import canonical_sha256
from .rig_validation import RigSemanticValidationError, RigSemanticValidator


PROBER_ID = "mesh-action-prober"
PROBER_VERSION = "1.0.0"
MINIMUM_USABLE_BEND_DEG = 30
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class MeshProbeReportError(ValueError):
    """Raised when a project probe report cannot be generated or trusted."""


@dataclass(frozen=True, slots=True)
class MeshProbeReport:
    """Frozen canonical JSON; document access always returns an isolated value."""

    _json: str

    @property
    def document(self) -> dict[str, Any]:
        return json.loads(self._json)

    def to_json(self) -> str:
        return self._json


def build_mesh_probe_report(
    rig: Mapping[str, Any],
    run: Mapping[str, Any],
    targets: Sequence[HingeTarget],
) -> MeshProbeReport:
    """Recompute every target probe and aggregate the minimum usable bend gate."""

    try:
        identity = _identity(rig, run)
        ordered_targets = _targets(targets)
        attachments = _mesh_attachments(rig, ordered_targets)
        bones = rig.get("bones")
        entries = [
            _probe_entry(bones, attachments[target.attachment_id], target)
            for target in ordered_targets
        ]
        status = (
            "rejected"
            if any(item["gate"]["status"] == "rejected" for item in entries)
            else "passed"
        )
        document = {
            "format": "autospine-mesh-action-probes",
            "format_version": 1,
            "project_id": identity["project_id"],
            "source": identity["source"],
            "prober": {
                "id": PROBER_ID,
                "version": PROBER_VERSION,
                "config": probe_config(),
            },
            "status": status,
            "summary": (
                f"converted={len(entries)}" if entries else "reviewed-noop"
            ),
            "attachments": entries,
        }
        encoded = json.dumps(
            document, ensure_ascii=False, allow_nan=False,
            sort_keys=True, separators=(",", ":"),
        )
        return MeshProbeReport(encoded)
    except MeshProbeReportError:
        raise
    except (
        MeshActionProbeError,
        MeshContractError,
        RigSemanticValidationError,
        TypeError,
        ValueError,
    ) as exc:
        raise MeshProbeReportError(f"mesh action probe report failed: {exc}") from exc


def require_mesh_probe_report(
    document: Mapping[str, Any],
    *,
    rig: Mapping[str, Any],
    run: Mapping[str, Any],
    targets: Sequence[HingeTarget],
) -> None:
    """Re-run every probe and require canonical equality with the claimed report."""

    if not isinstance(document, Mapping):
        raise MeshProbeReportError("mesh action probe report must be an object")
    expected = build_mesh_probe_report(rig, run, targets).document
    try:
        matches = canonical_sha256(document) == canonical_sha256(expected)
    except (TypeError, ValueError) as exc:
        raise MeshProbeReportError(
            "mesh action probe report is not canonical JSON"
        ) from exc
    if not matches:
        raise MeshProbeReportError(
            "mesh action probe report differs from recomputed evidence"
        )


def probe_config() -> dict[str, int | float]:
    return {
        "bend_step_degrees": BEND_STEP_DEGREES,
        "maximum_bend_degrees": MAX_BEND_DEGREES,
        "min_area_ratio": MIN_AREA_RATIO,
        "max_area_ratio": MAX_AREA_RATIO,
        "max_edge_stretch": MAX_EDGE_STRETCH,
        "minimum_usable_bend_deg": MINIMUM_USABLE_BEND_DEG,
    }


def _identity(rig, run) -> dict[str, Any]:
    if not isinstance(rig, Mapping) or not isinstance(run, Mapping):
        raise MeshProbeReportError("mesh RigIR and compile run must be objects")
    require_mesh_compile_run(run)
    RigSemanticValidator(max_influences=2).raise_for_errors(rig)
    source = rig.get("source")
    if not isinstance(source, Mapping):
        raise MeshProbeReportError("mesh RigIR source must be an object")
    try:
        rig_sha, run_sha = canonical_sha256(rig), canonical_sha256(run)
    except (TypeError, ValueError) as exc:
        raise MeshProbeReportError("mesh RigIR inputs are not canonical JSON") from exc
    if source.get("run_manifest_sha256") != run_sha:
        raise MeshProbeReportError("mesh RigIR run manifest binding is invalid")
    inputs = run["inputs"]
    return {
        "project_id": run["project_id"],
        "source": {
            "rig_sha256": rig_sha,
            "run_manifest_sha256": run_sha,
            "base_rig_sha256": inputs["base_rig_sha256"],
            "base_bundle_sha256": inputs["base_bundle_sha256"],
            "layer_manifest_sha256": inputs["layer_manifest_sha256"],
            "resolved_project_sha256": inputs["resolved_project_sha256"],
        },
    }


def _targets(value: Any) -> tuple[HingeTarget, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise MeshProbeReportError("mesh targets must be an array")
    result: list[HingeTarget] = []
    attachment_ids, source_ids = set(), set()
    for item in value:
        if not isinstance(item, HingeTarget):
            raise MeshProbeReportError("mesh targets must be HingeTarget values")
        identifiers = (
            item.attachment_id,
            item.source_layer_id,
            item.proximal_bone_id,
            item.distal_bone_id,
        )
        if any(not isinstance(value, str) or not _SAFE_ID.fullmatch(value) for value in identifiers):
            raise MeshProbeReportError("mesh target identifiers are invalid")
        if (
            item.side not in {"left", "right"}
            or item.proximal_bone_id != f"thigh.{item.side}"
            or item.distal_bone_id != f"calf.{item.side}"
        ):
            raise MeshProbeReportError("mesh target differs from profile-v1 bone semantics")
        if item.attachment_id in attachment_ids or item.source_layer_id in source_ids:
            raise MeshProbeReportError("mesh targets must be unique")
        attachment_ids.add(item.attachment_id)
        source_ids.add(item.source_layer_id)
        result.append(item)
    return tuple(sorted(result, key=lambda item: item.attachment_id))


def _mesh_attachments(rig, targets) -> dict[str, Mapping[str, Any]]:
    value = rig.get("attachments")
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise MeshProbeReportError("mesh RigIR attachments must be an array")
    indexed: dict[str, Mapping[str, Any]] = {}
    mesh_ids: set[str] = set()
    for raw in value:
        if not isinstance(raw, Mapping):
            raise MeshProbeReportError("mesh RigIR attachments must be objects")
        attachment_id = raw.get("id")
        if not isinstance(attachment_id, str) or not attachment_id or attachment_id in indexed:
            raise MeshProbeReportError("mesh RigIR attachment ids must be unique")
        indexed[attachment_id] = raw
        if raw.get("type") == "mesh":
            mesh_ids.add(attachment_id)
    expected = {target.attachment_id for target in targets}
    if mesh_ids != expected:
        raise MeshProbeReportError("mesh attachment set differs from probe targets")
    return indexed


def _probe_entry(bones, attachment, target: HingeTarget) -> dict[str, Any]:
    if (
        attachment.get("source_layer_ids") != [target.source_layer_id]
        or attachment.get("slot") != target.attachment_id
    ):
        raise MeshProbeReportError(
            f"mesh attachment {target.attachment_id} target binding is invalid"
        )
    probe = run_mesh_action_probe(
        bones, attachment,
        proximal_bone_id=target.proximal_bone_id,
        distal_bone_id=target.distal_bone_id,
    )
    negative = probe.distal_negative.max_contiguous_magnitude_deg
    positive = probe.distal_positive.max_contiguous_magnitude_deg
    magnitude = max(negative, positive)
    direction = "either" if negative == positive else (
        "negative" if negative > positive else "positive"
    )
    return {
        "attachment_id": target.attachment_id,
        "source_layer_id": target.source_layer_id,
        "side": target.side,
        "proximal_bone_id": target.proximal_bone_id,
        "distal_bone_id": target.distal_bone_id,
        "action_probe": probe.to_dict(),
        "widest_safe_bend": {
            "direction": direction,
            "magnitude_deg": magnitude,
        },
        "gate": {
            "status": "passed" if magnitude >= MINIMUM_USABLE_BEND_DEG else "rejected"
        },
    }
