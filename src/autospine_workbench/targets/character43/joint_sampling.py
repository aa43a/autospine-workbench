"""Preflight the existing immutable probes plus the common M5 key grid."""
import struct
from .joint_spring import grid

LIMIT = 4097


def preflight(old_times):
    duration = old_times[-1]
    samples = {struct.pack('<f', t) for t in [*old_times, *grid(duration, 120)]}
    return dict(minimum_samples=len(samples), sample_limit=LIMIT,
                supported=len(samples) <= LIMIT,
                scope='minimum_grid_before_additional_transition_keys')
