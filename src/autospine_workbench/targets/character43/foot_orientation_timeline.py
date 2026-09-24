"""Bounded temporal refinement of affine foot cancellation; no sole-contact claim."""
from bisect import bisect_right
from copy import deepcopy
import math

from .affine_pose import matrices
from ...resolved_project import canonical_sha256

TOLERANCE = 1e-3  # Matrix coefficient error relative to the setup foot frame.
MAX_KEYS = 4097
MAX_PASSES = 8


def angle_at(times, values, time):
    index = min(len(times)-2, max(0, bisect_right(times, time)-1))
    fraction = (time-times[index])/(times[index+1]-times[index])
    return values[index] + fraction*(values[index+1]-values[index])


def refine(document, name, observations, fit_samples):
    result, report = fit_samples(document, name, observations)  # Validate before interpolation.
    original_times = observations['times']
    times = set(original_times)
    bones = {bone['name']:bone for bone in document['bones']}
    tracks = document['animations'][name].get('bones', {})
    # Contact correction may add parent keys between source observations.
    for foot in observations['tracks']:
        parent = bones[foot].get('parent')
        while parent is not None:
            for channel in ('rotate','scale','shear'):
                times.update(key.get('time',0) for key in tracks.get(parent,{}).get(channel,[])
                             if original_times[0] <= key.get('time',0) <= original_times[-1])
            parent = bones[parent].get('parent')
    times = sorted(times)
    if len(times) > MAX_KEYS:
        raise ValueError('foot_fit_timeline_sample_limit')
    setup = deepcopy(document)
    setup['animations'][name] = {'bones': {}}
    rest = matrices(setup, name, 0)
    def rebuild():
        refined = dict(observations, times=times, tracks={bone:[angle_at(original_times, values, t) for t in times]
            for bone, values in observations['tracks'].items()})
        return fit_samples(document, name, refined)
    if times != list(original_times):
        result, report = rebuild()
    for iteration in range(MAX_PASSES+1):
        failures = set()
        maximum = 0.
        # Quarter points catch extrema missed by midpoint-only cancellation checks.
        checked = [a+(b-a)*fraction for a,b in zip(times,times[1:]) for fraction in (.25,.5,.75)]
        for time in checked:
            actual = matrices(result, name, time)
            for bone, values in observations['tracks'].items():
                angle = math.radians(angle_at(original_times, values, time))
                co, si = math.cos(angle), math.sin(angle)
                r = rest[bone]
                wanted = (co*r[0]-si*r[2], co*r[1]-si*r[3],
                          si*r[0]+co*r[2], si*r[1]+co*r[3])
                error = max(abs(x-y) for x,y in zip(actual[bone][:4], wanted))/max(abs(v) for v in r[:4])
                maximum = max(maximum, error)
                if error > TOLERANCE:
                    failures.add(time)
        if not failures:
            report.update(profile='source-foot-world-frame-timeline-v2',
                input_sha256=canonical_sha256(dict(document=document,observations=observations)),
                timeline=dict(tolerance=TOLERANCE, maximum_relative_matrix_error=maximum,
                    original_key_count=len(original_times), fitted_key_count=len(times),
                    checked_sample_count=len(checked), refinement_passes=iteration,
                    scope='quarter_interval_samples_not_continuous_or_sole_contact_proof'))
            return result, report
        if iteration == MAX_PASSES or len(times)+len(failures) > MAX_KEYS:
            raise ValueError('foot_fit_timeline_budget_exceeded')
        times = sorted(set(times) | failures)
        result, report = rebuild()
