"""Small, version-neutral preview clips; never a production motion decision."""

import math

from .pipeline_run import PipelineRunError

PROFILE = "workbench-limb-preview-v1"
CLIPS = (
    {"id": "limb-flex-15", "label": "轻柔屈伸 · 15°候选", "amplitude": 15},
    {"id": "limb-flex-30", "label": "屈伸检查 · 30°候选", "amplitude": 30},
)


def build_motion(clip, joints):
    selected = next((row for row in CLIPS if row["id"] == clip), None)
    if selected is None:
        raise PipelineRunError("animated_clip_unsupported")
    if not isinstance(joints, list) or len(joints) != len(set(joints)) or any(
        name not in {"forearm_l", "forearm_r", "calf_l", "calf_r"} for name in joints
    ):
        raise PipelineRunError("animated_motion_joint_unsupported")
    angles = [0 if frame in (0, 30, 60) else round(
        selected["amplitude"] * math.sin(frame * math.pi / 30), 10
    ) for frame in range(61)]
    return {
        "schema": "autospine.workbench-preview-motion/v1", "profile": PROFILE,
        "authority": "none", "clip": clip, "fps": 30, "duration": 2,
        "scope": "limited_limb_rotation_preview", "production_authorized": False,
        "bones": {name: {"rotation": [
            {"time": frame / 30, "degrees": angle} for frame, angle in enumerate(angles)
        ]} for name in sorted(joints)},
    }
