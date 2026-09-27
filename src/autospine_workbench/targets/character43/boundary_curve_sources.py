"""Validate refined compensation identity and transport bounded solver targets."""
from hashlib import sha256
import json
import math
from .deform_addition import value
from .interpolation_area_margin import LIMIT
from .parent_pose_area_repair import verify_source


def read_compensation(parent, raw, report, artifact, slot, name):
    if (report.get('parent_artifact_sha256')!=artifact or report.get('slot')!=slot or
            report.get('profile')!='fixed-surface-adaptive-sampling-v1-experiment' or
            report.get('status')!='sampled_fixed_floors_passed' or
            report.get('skeleton_sha256')!=sha256(raw).hexdigest() or
            not report.get('history') or report['history'][-1]['failures']):
        raise ValueError('boundary_compensation_source_identity')
    candidate=json.loads(raw);verify_source(parent,candidate,name,slot)
    return candidate


def resample_margins(margins, source_times, target_times, size):
    if (not source_times or not target_times or type(size) is not int or size<1 or
            any(not math.isfinite(t) for t in source_times+target_times) or
            any(a>=b for times in (source_times,target_times) for a,b in zip(times,times[1:])) or
            target_times[0]<source_times[0] or target_times[-1]>source_times[-1] or
            any(t not in source_times for t in margins)):
        raise ValueError('boundary_margin_resampling_times')
    if any(len(row)!=size or any(not math.isfinite(v) or not 0<=v<=LIMIT for v in row) for row in margins.values()):
        raise ValueError('boundary_margin_resampling_values')
    keys=[dict(time=t,vertices=margins.get(t,[0.]*size)) for t in source_times]
    return {t:value(keys,t,size) for t in target_times}
