"""Pure orchestration for contract-shaped alpha geometry sections."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Mapping

from .limb_contact_evidence import analyze_limb_contacts
from .limb_evidence_layers import LimbEvidenceSet
from .limb_geometry_matching import geometry_config
from .limb_path_evidence import analyze_limb_paths
from .pose_observations import PoseObservationSet


@dataclass(frozen=True, slots=True)
class GeometrySections:
    paths: list[dict[str, Any]]
    contacts: list[dict[str, Any]]
    observability: dict[str, dict[str, Any]]
    qa_flags: list[str]

    def to_dict(self) -> dict[str, Any]:
        """Return an isolated JSON-compatible payload for the artifact builder."""

        return copy.deepcopy({
            "paths": self.paths,
            "contacts": self.contacts,
            "observability": self.observability,
            "qa_flags": self.qa_flags,
        })


def analyze_geometry_sections(
    evidence: LimbEvidenceSet,
    observations: PoseObservationSet,
    canvas_size: tuple[int, int],
    config: Mapping[str, Any],
) -> GeometrySections:
    """Analyze paths and contacts without constructing artifact provenance."""

    if (
        not isinstance(canvas_size, tuple)
        or len(canvas_size) != 2
        or any(not isinstance(value, int) or isinstance(value, bool) or value < 1 for value in canvas_size)
    ):
        raise ValueError("canvas_size must contain two positive integers")
    if observations.canvas_size != canvas_size:
        raise ValueError("pose observations do not match the geometry canvas")
    settings = geometry_config(config)
    paths = analyze_limb_paths(evidence, observations, canvas_size, settings)
    contacts = analyze_limb_contacts(evidence, observations, canvas_size, settings)
    observability: dict[str, dict[str, Any]] = {}
    all_joints = set(paths.joint_states) | set(contacts.joint_contact_ids) | set(contacts.joint_flags)
    for joint_id in sorted(all_joints):
        path_state = paths.joint_states.get(joint_id, {
            "status": "ambiguous", "path_ids": [], "flags": [],
        })
        flags = set(path_state["flags"]) | set(contacts.joint_flags.get(joint_id, ()))
        observability[joint_id] = {
            "status": path_state["status"],
            "path_ids": sorted(path_state["path_ids"]),
            "contact_ids": sorted(contacts.joint_contact_ids.get(joint_id, ())),
            "flags": sorted(flags),
        }
    qa_flags = (
        set(evidence.flags)
        | set(paths.qa_flags)
        | set(contacts.qa_flags)
        | {"MANUAL_REVIEW_REQUIRED"}
    )
    return GeometrySections(
        paths=sorted(paths.paths, key=lambda item: item["path_id"]),
        contacts=sorted(contacts.contacts, key=lambda item: item["contact_id"]),
        observability=observability,
        qa_flags=sorted(qa_flags),
    )
