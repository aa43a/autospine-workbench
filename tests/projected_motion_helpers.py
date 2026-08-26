"""Shared deterministic ProjectedMotionIR fixtures."""

from __future__ import annotations


def projected_motion_document(
    *, loop: bool = False, collapsed: bool = False,
    include_child: bool = False,
) -> dict:
    """Build a minimal internally consistent two-frame document."""

    if collapsed:
        vector = [0.0, 0.0]
        projected = 0.0
        ratio = 0.0
        cosine = 1.0
        end_depth = 1.0
        midpoint = 0.5
        state = "collapsed"
    else:
        vector = [1.0, 0.0]
        projected = 1.0
        ratio = 1.0
        cosine = 0.0
        end_depth = 0.0
        midpoint = 0.0
        state = "observable"
    samples = [
        {
            "source_frame_index": index,
            "tick": index * 33333,
            "projected_vector_normalized": list(vector),
            "source_length_normalized": 1.0,
            "projected_length_normalized": projected,
            "foreshortening_ratio": ratio,
            "depth_cosine": cosine,
            "projected_world_angle_deg": 0.0,
            "start_depth_root_relative_normalized": 0.0,
            "end_depth_root_relative_normalized": end_depth,
            "midpoint_depth_root_relative_normalized": midpoint,
            "projection_state": state,
        }
        for index in range(2)
    ]
    tracks = [{
        "role": "humanoid.root",
        "source_joint_name": "Hips",
        "aim_joint_name": "Spine1",
        "delta_parent_role": None,
        "setup_source_length_normalized": 1.0,
        "setup_projected_length_normalized": projected,
        "samples": samples,
    }]
    if include_child:
        tracks.append({
            "role": "humanoid.spine.lower",
            "source_joint_name": "Spine1",
            "aim_joint_name": "Spine2",
            "delta_parent_role": "humanoid.root",
            "setup_source_length_normalized": 1.0,
            "setup_projected_length_normalized": projected,
            "samples": [dict(sample) for sample in samples],
        })
    return {
        "format": "autospine-projected-motion-ir",
        "format_version": 1,
        "clip_id": "kimodo.synthetic.front",
        "timing": {
            "ticks_per_second": 1_000_000,
            "duration_ticks": 33333,
            "loop": loop,
            "frame_count": 2,
        },
        "source": {
            "kind": "kimodo_npz",
            "motion_ir_sha256": "1" * 64,
            "motion_bundle_sha256": "2" * 64,
            "motion_run_sha256": "3" * 64,
            "raw_npz_sha256": "4" * 64,
            "source_sha256": "5" * 64,
            "map_sha256": "6" * 64,
            "array_inventory_sha256": "7" * 64,
        },
        "camera_sha256": "8" * 64,
        "frames": [
            {"source_frame_index": 0, "tick": 0},
            {"source_frame_index": 1, "tick": 33333},
        ],
        "root_samples": [
            {
                "source_frame_index": index,
                "tick": index * 33333,
                "screen_translation_normalized": [0.0, 0.0],
                "depth_translation_normalized": 0.0,
            }
            for index in range(2)
        ],
        "segment_tracks": tracks,
        "markers": [],
    }
