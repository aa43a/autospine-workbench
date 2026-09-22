"""Compile only overlap-supported orders without crossing unknown visible parts."""
from copy import deepcopy
import heapq
import math
from .order_conflict import first_overlap, witness
from .depth_interval_evidence import requests as interval_requests

PROFILE = 'external-overlap-guarded-draw-order-v1'


def _crossing_ranges(requests):
    ranges={}
    for arm,lo,hi in requests:
        # Every interval includes this arm's setup index; their union has no gaps.
        a,b=ranges.get(arm,(lo,hi));ranges[arm]=(min(a,lo),max(b,hi))
    return ranges


def _crosses(a,b,indices,ranges):
    x,y=ranges.get(a),ranges.get(b)
    return bool((x and x[0]<=indices[b]<=x[1]) or (y and y[0]<=indices[a]<=y[1]))


def _sort(slots, edges):
    rank={name:i for i,name in enumerate(slots)}
    following={name:[] for name in slots};incoming=dict.fromkeys(slots,0)
    for back,front in edges:
        following[back].append(front);incoming[front]+=1
    ready=[rank[name] for name in slots if not incoming[name]]
    heapq.heapify(ready);output=[]
    while ready:
        name=slots[heapq.heappop(ready)];output.append(name)
        for front in following[name]:
            incoming[front]-=1
            if not incoming[front]:heapq.heappush(ready,rank[front])
    if len(output)!=len(slots):return None
    return output


def build(document, animation, depth, probe, *, refine_cycles=False, evaluation_ticks=None):
    slots = [s['name'] for s in document['slots']]
    indices = {s: i for i, s in enumerate(slots)}
    report = dict(profile=PROFILE, selected=False, authority='none', status='blocked',
                  reason_codes=[], failures=[], frames=[], scope='sampled_order_constraints_not_visual_acceptance')
    if depth.get('strict_interval_evidence'):
        report['interval_evidence_policy']='same-time-source-and-held-midpoint-v1'
    if refine_cycles:
        report.update(profile='external-overlap-guarded-draw-order-v2-experiment', cycle_refinements=[])
    if document['animations'][animation].get('drawOrder'):
        report['reason_codes'] = ['existing_draw_order_preserved']
        return None, report
    by_tick = {}
    for pair in depth['pairs']:
        for sample in pair['samples']:
            by_tick.setdefault(sample['tick'], []).append((pair, sample))
    if evaluation_ticks is not None:
        if (not evaluation_ticks or len(evaluation_ticks)>2049 or
                any(type(t) not in (int,float) or not math.isfinite(t) or t<0 for t in evaluation_ticks) or
                any(b<=a for a,b in zip(evaluation_ticks,evaluation_ticks[1:])) or
                not set(by_tick)<=set(evaluation_ticks)):
            raise ValueError('order_evaluation_ticks_invalid')
        for tick in evaluation_ticks:by_tick.setdefault(tick,[])
        report['scope']='explicit_schedule_partial_constraints_not_full_depth_or_visual_acceptance'
    ticks = sorted(by_tick)
    if not ticks:
        report['reason_codes'] = ['depth_pairs_unavailable']
        return None, report
    previous = slots; keys = []
    for index, tick in enumerate(ticks):
        time = tick/1e6
        # Guard the held order at the next midpoint as well as the source frame.
        times = [time] + ([(tick+ticks[index+1])/2e6] if index+1 < len(ticks) else [])
        edges = set(); requests = []; evidence = {}; details = {}
        try:
            for pair, row in by_tick[tick]:
                arm, torso = pair['arm_slot'], pair['torso_slot']
                for back, front, visible in interval_requests(pair,row,times,probe,
                        strict=depth.get('strict_interval_evidence',False)):
                    fresh=(back,front) not in edges
                    edges.add((back, front))
                    if depth.get('strict_interval_evidence'):
                        evidence.setdefault((back,front),dict(source=pair.get('evidence_source','source_depth'),overlap=visible))
                        evidence[back,front].setdefault('interval_overlaps',[]).append(visible)
                    else:
                        evidence[back,front]=dict(source=pair.get('evidence_source','source_depth'),overlap=visible)
                    if fresh and indices[back] > indices[front]:
                        requests.append((arm, min(indices[arm], indices[torso]), max(indices[arm], indices[torso])))
            crossing_ranges=_crossing_ranges(requests)
            for i, a in enumerate(slots):
                for b in slots[i+1:]:
                    if (a, b) in edges or (b, a) in edges:
                        continue
                    crossing = _crosses(a,b,indices,crossing_ranges)
                    overlap = first_overlap(probe, a, b, times) if crossing else None
                    if crossing and not overlap:
                        continue
                    edges.add((a, b))
                    evidence[a, b] = dict(source='visible_setup_order' if crossing else 'preserved_setup_order')
                    if overlap:
                        evidence[a, b]['overlap'] = overlap
            order = _sort(slots, edges)
            if order is None and refine_cycles:
                from .order_cycle_refine import resolve
                order, audit = resolve(slots, edges, evidence, probe, times, _sort)
                report['cycle_refinements'].append(dict(time=time, **audit))
                if order is None:
                    details = dict(conflict=audit.get('conflict'))
                    raise ValueError(audit['reason_code'])
            if order is None:
                details = dict(conflict=witness(slots, evidence))
                raise ValueError('visible_unmapped_order_conflict')
        except ValueError as exc:
            if getattr(exc,'details',None): details.update(exc.details)
            if getattr(exc,'diagnostic',None): details['raster_budget']=exc.diagnostic
            report['failures'].append(dict(time=time, reason_code=str(exc), **details))
            continue
        if order != previous:
            keys.append(dict(time=time, offsets=[dict(slot=s, offset=order.index(s)-i) for i, s in enumerate(slots)]))
            report['frames'].append(dict(time=time, order=order))
            previous = order
    if report['failures']:
        report['reason_codes'] = sorted({f['reason_code'] for f in report['failures']})
        return None, report
    candidate = deepcopy(document)
    if keys:
        candidate['animations'][animation]['drawOrder'] = keys
    report['status'] = 'candidate' if keys else 'no_visible_order_change'
    return candidate, report
