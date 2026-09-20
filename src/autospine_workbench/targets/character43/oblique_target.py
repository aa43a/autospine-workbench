"""Target preparation for an explicitly versioned constant-yaw candidate."""
import math

from .oblique_motion import PROFILE, compile_candidate
from .oblique_source import extract
from .motion_clip import selected_ratios
from .motionir_candidate import ROLES
from .projected_lengths import apply_ratios
from ...resolved_project import canonical_sha256


def validate(value):
    if (not isinstance(value,dict) or set(value)!={'profile','yaw_degrees'} or value['profile']!=PROFILE
            or type(value['yaw_degrees']) not in (int,float) or not math.isfinite(value['yaw_degrees'])
            or not -90 <= value['yaw_degrees'] <= 90):
        raise ValueError('motion_oblique_projection_invalid')
    return dict(value)


def prepare(bundle, selection):
    selection=validate(selection)
    return compile_candidate(bundle.motion,*extract(bundle),selection['yaw_degrees'],
                             precision=5 if bundle.source_kind=='kimodo_npz' else 12)


def lengths(document,name,receipt,*,time_range=None):
    ratios={}; summary=[]; diagnostic=receipt['projection']
    for row in diagnostic['records']:
        values,times=selected_ratios(row['visibility'],diagnostic['times'],time_range)
        bone=ROLES[row['role']]; ratios[bone]=values
        summary.append(dict(role=row['role'],bone=bone,min_ratio=min(values),max_ratio=max(values)))
    result,evidence=apply_ratios(document,name,ratios,summary,times,
                                 receipt['spatial_input_sha256'],canonical_sha256(receipt))
    evidence.update(projection_profile=PROFILE,yaw_degrees=receipt['yaw_degrees'],
                    source_identity_kind='verified_spatial_input')
    return result,evidence
