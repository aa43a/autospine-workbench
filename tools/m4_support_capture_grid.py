"""Preserve every verified support sample in the final mesh capture grid."""
import math
from autospine_workbench.automation.motion_target_pose import final_times


def build(document, name, sequence):
    generated = final_times(document, name, [r['time'] for r in sequence['candidate_rows']])
    feedback = sequence.get('verification_time_grid', sequence.get('check_times', []))
    if any(not math.isfinite(t) or not generated[0] <= t <= generated[-1] for t in feedback):
        raise ValueError('support_capture_feedback_time_invalid')
    result = sorted(set(generated) | set(feedback))
    if len(result) > 4097:
        raise ValueError('support_capture_sample_limit')
    return result
