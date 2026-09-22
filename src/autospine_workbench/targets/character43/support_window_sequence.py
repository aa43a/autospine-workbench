"""One bounded sweep of overlapping windows; rejected regions retain their rows."""
from copy import deepcopy
import math
from .support_window_optimizer import optimize


def build(document, name, rows, anchors, reference, *, progress=None, extra_times=()):
    if not 5 <= len(rows) <= 2048:
        raise ValueError('support_sequence_size_invalid')
    times = [r['time'] for r in rows]
    if any(not math.isfinite(t) for t in times) or any(b <= a for a,b in zip(times,times[1:])):
        raise ValueError('support_sequence_times_invalid')
    if len(extra_times)>4097 or any(not math.isfinite(t) or not times[0]<=t<=times[-1] for t in extra_times):
        raise ValueError('support_sequence_extra_times_invalid')
    result = deepcopy(rows); reports = []
    for start in range(0, len(rows)-4, 16):
        end = min(start+33, len(rows)); window = result[start:end]
        eligible = all(sum(a['limb']=='leg.'+side and a['start']<=window[0]['time']
                          and a['end']>window[-1]['time'] for a in anchors)==1 for side in ('left','right'))
        if not eligible:
            report = dict(start=window[0]['time'], end=window[-1]['time'], status='contact_transition_or_single_support_preserved')
        else:
            extras=[t for t in extra_times if window[0]['time']<=t<=window[-1]['time']]
            changed, report = optimize(document,name,window,anchors,reference,
                                      **(dict(extra_times=extras) if extras else {}))
            if report['status']=='candidate':
                if changed[0]!=window[0] or changed[-1]!=window[-1] or [r['time'] for r in changed]!=[r['time'] for r in window]:
                    raise ValueError('support_sequence_window_boundary_changed')
                result[start:end] = changed
        reports.append(report)
        if progress: progress(dict(window=len(reports), **report))
    accepted = sum(r['status']=='candidate' for r in reports)
    return result, dict(profile='source-axis-feedback-sweep-v1-experiment' if extra_times else 'source-axis-window-sweep-v1-experiment', authority='none', selected=False,
        status='partial_candidate' if accepted else 'original_preserved', accepted_windows=accepted,
        windows=reports, samples=len(rows), scope='one_sweep_bone_tracks_not_mesh_runtime_or_visual_acceptance')
