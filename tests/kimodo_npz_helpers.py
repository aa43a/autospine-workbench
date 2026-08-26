"""Shared explicit Kimodo NPZ sidecar and map fixtures."""

from __future__ import annotations

import hashlib

from autospine_workbench.kimodo_npz_source import COORDINATE_SYSTEM
from autospine_workbench.kimodo_soma77 import (
    PROFILE_ID,
    SOMA77_DEFINITION_SHA256,
)


ROLE_JOINT_AIM = (
    ("humanoid.root", "Hips", "Spine1"),
    ("humanoid.spine.lower", "Spine1", "Spine2"),
    ("humanoid.spine.upper", "Spine2", "Chest"),
    ("humanoid.neck", "Neck1", "Neck2"),
    ("humanoid.head", "Head", "HeadEnd"),
    ("humanoid.clavicle.left", "LeftShoulder", "LeftArm"),
    ("humanoid.arm.upper.left", "LeftArm", "LeftForeArm"),
    ("humanoid.arm.lower.left", "LeftForeArm", "LeftHand"),
    ("humanoid.leg.upper.left", "LeftLeg", "LeftShin"),
    ("humanoid.leg.lower.left", "LeftShin", "LeftFoot"),
    ("humanoid.clavicle.right", "RightShoulder", "RightArm"),
    ("humanoid.arm.upper.right", "RightArm", "RightForeArm"),
    ("humanoid.arm.lower.right", "RightForeArm", "RightHand"),
    ("humanoid.leg.upper.right", "RightLeg", "RightShin"),
    ("humanoid.leg.lower.right", "RightShin", "RightFoot"),
)


def source_document(
    raw: bytes = b"synthetic-npz",
    *,
    frames: int = 3,
    inventory: str = "complete-v1",
    contact_layout: str = "left-heel-toe-right-heel-toe-v1",
    recorded: bool = False,
) -> dict:
    producer = {
        "status": "unavailable",
        "implementation": "nv-tlabs/kimodo",
        "reason_code": "external_export",
    }
    if recorded:
        producer = {
            "status": "recorded",
            "implementation": "nv-tlabs/kimodo",
            "repository_revision": "1" * 40,
            "model_id": "Kimodo-SOMA-RP-v1.1",
            "checkpoint_revision": "2" * 40,
            "checkpoint_manifest_sha256": "3" * 64,
            "generation_request_sha256": "4" * 64,
            "seed": 42,
            "sample_index": 0,
        }
    return {
        "format": "autospine-kimodo-npz-source",
        "format_version": 1,
        "source_id": "kimodo.soma77.synthetic-v1",
        "raw_npz": {
            "sha256": hashlib.sha256(raw).hexdigest(),
            "byte_length": len(raw),
            "frame_count": frames,
            "frames_per_second": {"numerator": 30, "denominator": 1},
        },
        "producer": producer,
        "skeleton": {
            "profile_id": PROFILE_ID,
            "joint_count": 77,
            "definition_sha256": SOMA77_DEFINITION_SHA256,
            "definition_scope": "joint_names_and_parents",
            "rest_geometry_policy": "source_frame0_unverified",
        },
        "coordinate_system": dict(COORDINATE_SYSTEM),
        "array_profile": {
            "inventory": inventory,
            "float_dtype": "<f4",
            "contact_dtype": "|b1",
            "contact_layout": contact_layout,
        },
    }


def map_document(
    *,
    contact_layout: str = "left-heel-toe-right-heel-toe-v1",
    contact_enabled: bool = True,
) -> dict:
    contact = {
        "enabled": False,
        "mode": "annotation_only",
        "interval": "half_open",
    }
    if contact_enabled:
        points = (
            (("leg.left", "heel"), ("leg.left", "toe"),
             ("leg.right", "heel"), ("leg.right", "toe"))
            if contact_layout == "left-heel-toe-right-heel-toe-v1"
            else (("leg.left", "heel"), ("leg.left", "toe"),
                  ("leg.left", "toe_end"), ("leg.right", "heel"),
                  ("leg.right", "toe"), ("leg.right", "toe_end"))
        )
        contact = {
            "enabled": True,
            "source": "foot_contacts",
            "layout": contact_layout,
            "channels": [
                {"index": index, "limb": limb, "point": point}
                for index, (limb, point) in enumerate(points)
            ],
            "reduction_policy": "any_true_per_limb",
            "mode": "annotation_only",
            "interval": "half_open",
        }
    return {
        "format": "autospine-kimodo-npz-map",
        "format_version": 1,
        "map_id": "kimodo.soma77.front-v1",
        "clip": {"clip_id": "kimodo.soma77.synthetic", "loop": False},
        "basis": {
            "screen_x": "+X",
            "screen_y": "-Y",
            "depth": "+Z",
            "rotation_convention": "validated_matrix_fk_projected_segment",
        },
        "root": {
            "joint_name": "Hips",
            "position_source": "root_positions",
            "reference_length_meters": 1.0,
            "translation_policy":
                "projected_frame0_delta_normalized_reference_length",
            "baseline_policy": "source_frame0",
        },
        "bones": [
            {
                "role": role,
                "joint_name": joint,
                "aim_joint_name": aim,
                "rotation_policy":
                    "projected_setup_local_delta_from_validated_fk",
            }
            for role, joint, aim in ROLE_JOINT_AIM
        ],
        "contact": contact,
    }
