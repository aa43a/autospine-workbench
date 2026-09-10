"""Preserve structural blockers instead of misreporting missing tracks as bad geometry."""


def blocking_reason(row):
    tracks = row.get('tracks')
    if not tracks:
        reasons = row.get('reason_codes', [])
        return reasons[0] if reasons else 'motion_envelope_not_evaluated'
    if any(track['failed_ticks'] for track in tracks):
        return 'motion_envelope_geometry_failure'
    return None
