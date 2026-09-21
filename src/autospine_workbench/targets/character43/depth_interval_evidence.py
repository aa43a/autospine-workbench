"""Match each held-order visibility sample to depth evidence at the same time."""
from .order_conflict import first_overlap
import math


class IntervalEvidenceError(ValueError):
    def __init__(self, reason, details):
        super().__init__(reason)
        self.details = details


def requests(pair, row, times, probe, *, strict=False):
    arm, body = pair['arm_slot'], pair['torso_slot']
    if not strict:
        visible = first_overlap(probe, arm, body, times)
        samples = [(row, visible)] if visible else []
    else:
        if (len(times) not in (1,2) or any(type(t) not in (int,float) or not math.isfinite(t) for t in times)
                or any(b<=a for a,b in zip(times,times[1:]))):raise ValueError('held_interval_sample_times_invalid')
        evidence = [row] + ([row.get('interval_sample')] if len(times)>1 else [])
        samples = []
        for time, sample in zip(times, evidence):
            tick=None if sample is None else sample.get('tick')
            if type(tick) not in (int,float) or not math.isfinite(tick) or abs(tick/1e6-time)>1e-12:
                raise IntervalEvidenceError('held_interval_depth_missing', dict(pair=[arm,body],sample_time=time))
            visible = first_overlap(probe, arm, body, [time])
            if visible:
                samples.append((sample, visible))
    output = []
    for sample, visible in samples:
        if sample['ambiguous'] or (strict and sample.get('support')=='no_overlap'):
            raise IntervalEvidenceError('visible_depth_straddle', dict(pair=[arm,body],overlap=visible))
        front=sample['current_front_slot']
        if front not in (arm,body):raise ValueError('depth_front_slot_invalid')
        output.append((body if front==arm else arm, front, visible))
    if len({(a,b) for a,b,_ in output})>1:
        raise IntervalEvidenceError('visible_depth_order_changes_within_interval',
                                    dict(pair=[arm,body],samples=[dict(back=a,front=b,overlap=v,
                                         evidence_states=sample.get('evidence_states'))
                                         for (a,b,v),(sample,_) in zip(output,samples)]))
    return output
