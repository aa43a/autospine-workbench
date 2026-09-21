"""Measured solver headroom; independent acceptance floors are unchanged."""
from copy import deepcopy
import math
from .area_preservation import minimum_ratios

LIMIT=.02


def targets(context):
    floors=minimum_ratios(context)
    margins=context.get('solver_margins')
    if margins is None:return floors
    if len(margins)!=len(floors) or any(not math.isfinite(m) or not 0<=m<=LIMIT for m in margins):
        raise ValueError('area_solver_margins_invalid')
    return [f+m for f,m in zip(floors,margins)]


def update(document,checked,previous):
    result=deepcopy(previous)
    for row in checked['failures']:
        if row['at_key']:continue
        slot=row['slot'];count=len(document['skins'][0]['attachments'][slot][slot]['triangles'])//3
        for failure in row.get('preservation_failures',[]):
            i=failure['triangle'];deficit=failure['minimum']-failure['ratio']
            if not 0<=i<count or not math.isfinite(deficit) or deficit<=0:raise ValueError('area_margin_evidence_invalid')
            values=result.setdefault(slot,[0.]*count)
            values[i]=min(LIMIT,max(values[i],previous.get(slot,[0.]*count)[i]+2*deficit+1e-6))
    return result
