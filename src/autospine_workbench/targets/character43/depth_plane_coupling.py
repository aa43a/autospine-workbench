"""Experimental soft agreement for ambiguous labels sharing an exact plane model."""
from collections import defaultdict
from itertools import combinations
import json
import math
from .depth_binary_cut import solve
from .depth_coherent_frame import adjacency

PROFILE = 'identical-plane-ambiguous-potts8-v1-experiment'


def couple(mesh, models, checks, arm, setup_front=None):
    """Mutate inferred A labels only; never turn inference into observed depth."""
    lookup = {}
    for check in checks:
        key = (check['arm'], check['body'], check['time'])
        if key in lookup:
            raise ValueError('plane_coupling_duplicate_check')
        lookup[key] = check
    n = len(mesh['triangles']) // 3
    adjacent = adjacency(mesh)
    by_time = defaultdict(dict)
    for body, frames in models.items():
        for frame in frames:
            by_time[frame['time']][body] = frame
    records = []
    previous = {} if setup_front is None else {b:[int(setup_front[b])]*n for b in models}
    for time, frames in sorted(by_time.items()):
        groups = defaultdict(list)
        for body, frame in frames.items():
            check = lookup.get((arm, body, time), {})
            plane = check.get('reference_plane')
            evidence = check.get('reference_plane_evidence', {})
            if (check.get('source_tick') != frame['source_tick'] or
                evidence.get('profile') != 'torso-anchored-planar-garment-depth-v1-experiment' or
                not isinstance(plane, list) or len(plane) != 3 or
                any(not isinstance(v, (int, float)) or not math.isfinite(v) for v in plane) or
                plane != evidence.get('coefficients')):
                continue
            groups[json.dumps(evidence, sort_keys=True)].append(body)
        for bodies in groups.values():
            bodies.sort()
            if len(bodies) < 2:
                continue
            links = [(a*n+i, b*n+i, 8) for a,b in combinations(range(len(bodies)),2)
                     for i in range(n) if all(frames[bodies[j]]['observed_states'][i]=='A' for j in (a,b))]
            if not links:
                continue
            unary, edges, fixed = [], list(links), {}
            for j, body in enumerate(bodies):
                frame = frames[body]; states = frame['observed_states']
                prior = previous.get(body, frame['labels'])
                unary.extend((int(v != 0), int(v != 1)) for v in prior)
                fixed.update({j*n+i: v for i,v in enumerate(frame['labels']) if states[i]!='A'})
                edges.extend((j*n+a,j*n+b,8) for a,b in adjacent if states[a]!='N' and states[b]!='N')
            result = solve(unary, edges, fixed)
            changed = 0
            for j, body in enumerate(bodies):
                frame = frames[body]; labels = result['labels'][j*n:(j+1)*n]
                changed += sum(a!=b for a,b in zip(frame['labels'],labels))
                frame['independent_labels'] = frame['labels']
                frame['labels'] = labels
                frame['independent_energy'] = frame.pop('energy')
                frame['coupling_profile'] = PROFILE
                frame['spatial_cuts'] = sum(labels[a]!=labels[b] for a,b in adjacent
                                            if frame['observed_states'][a]!='N' and frame['observed_states'][b]!='N')
            records.append(dict(time=time,bodies=bodies,soft_links=len(links),changed_labels=changed,
                                joint_energy=result['energy'],authority='none',selected=False))
        previous.update({b:list(f['labels']) for b,f in frames.items()})
    for body, frames in models.items():
        prior = None if setup_front is None else [int(setup_front[body])]*n
        for frame in frames:
            frame['independent_transition_count'] = frame.get('transition_count',0)
            frame['transition_count'] = 0 if prior is None else sum(a!=b for a,b in zip(prior,frame['labels']))
            prior = frame['labels']
    return records
