"""Bounded processing budgets; solver activity is not a promise of completion."""


def limit(kind):
    return 3600 if kind in ('adapt', 'generate') else 240


def timeout_reason(kind, elapsed, idle):
    if elapsed > limit(kind):
        return 'motion_target_timeout' if kind == 'adapt' else 'motion_decode_timeout'
    if kind == 'adapt' and idle > 900:
        return 'motion_target_stalled'
    return None
