"""Pinned numeric profile for P10.2 body-sway structural probes."""

from __future__ import annotations

from typing import Any

from .mesh_action_probe import (
    MAX_AREA_RATIO,
    MAX_EDGE_STRETCH,
    MIN_AREA_RATIO,
)


PROFILE_ID = "body-sway-structural-probe"
PROFILE_VERSION = "1.0.0"
FIXED_SAMPLE_STEP_TICKS = 50_000
UNIFORM_SAMPLES_PER_CYCLE = 32
MAX_SAMPLE_COUNT = 65_536
NUMERIC_PRECISION_DECIMALS = 9
MAX_CYCLES = 64


def body_sway_probe_profile() -> dict[str, Any]:
    """Return the sole detached P10.2 profile; callers cannot configure it."""

    return {
        "id": PROFILE_ID,
        "version": PROFILE_VERSION,
        "config": {
            "fixed_sample_step_ticks": FIXED_SAMPLE_STEP_TICKS,
            "uniform_samples_per_cycle": UNIFORM_SAMPLES_PER_CYCLE,
            "max_sample_count": MAX_SAMPLE_COUNT,
            "numeric_precision_decimals": NUMERIC_PRECISION_DECIMALS,
            "mesh_thresholds": {
                "min_signed_area_ratio": MIN_AREA_RATIO,
                "max_signed_area_ratio": MAX_AREA_RATIO,
                "max_edge_stretch_ratio": MAX_EDGE_STRETCH,
            },
        },
    }
