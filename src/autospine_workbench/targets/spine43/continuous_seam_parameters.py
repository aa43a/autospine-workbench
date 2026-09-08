"""Bounded least-squares monotone arc parameters, without deform or adoption."""
import math
from .alpha_seam import embed,position
from .continuous_pose import world


def fit(values,length,sign,spacing=.1,budget=2.):
    if (not values or sign not in (-1,1) or spacing<=0 or budget<0 or length<=0
            or any(not math.isfinite(v) for v in [*values,length,spacing,budget])):
        raise ValueError('parameter_input_invalid')
    targets=[v if sign==1 else length-v for v in values];blocks=[]
    for i,value in enumerate(targets):
        lower=max(0.,value-budget)-i*spacing;upper=min(length,value+budget)-i*spacing
        if lower>upper:raise ValueError('parameter_infeasible')
        block={'start':i,'end':i+1,'sum':value-i*spacing,'low':lower,'high':upper}
        block['value']=min(upper,max(lower,block['sum']));blocks.append(block)
        while len(blocks)>1 and blocks[-2]['value']>blocks[-1]['value']:
            right=blocks.pop();left=blocks.pop()
            merged={'start':left['start'],'end':right['end'],'sum':left['sum']+right['sum'],
                    'low':max(left['low'],right['low']),'high':min(left['high'],right['high'])}
            if merged['low']>merged['high']+1e-10:raise ValueError('parameter_infeasible')
            merged['value']=min(merged['high'],max(merged['low'],merged['sum']/(merged['end']-merged['start'])))
            blocks.append(merged)
    fitted=[0.]*len(values)
    for block in blocks:
        for i in range(block['start'],block['end']):
            v=block['value']+i*spacing;fitted[i]=v if sign==1 else length-v
    if any(abs(a-b)>budget+1e-8 for a,b in zip(fitted,values)):raise ValueError('parameter_budget')
    return fitted


def sample(record,arc,value,attachment):
    if not math.isfinite(value) or not 0<=value<=len(arc['edges']):raise ValueError('parameter_sample_range')
    length=len(arc['edges']);index=min(int(value),length-1);t=value-index
    curve=record['curves'][arc['curve']];edge=arc['edges'][index];a,b=curve['points'][edge:edge+2]
    point=[a[k]+t*(b[k]-a[k]) for k in (0,1)];w,h=record['size']
    uv=list(zip(attachment['uvs'][::2],attachment['uvs'][1::2]));flat=attachment['triangles']
    binding=embed((point[0]/w,point[1]/h),uv,[flat[i:i+3] for i in range(0,len(flat),3)])
    return {'parameter':value,'pixel_xy':point,'embedding':binding}


def analyze(doc,curves,arcs,boundary):
    records={r['attachment']:r for r in curves['curves']['attachments']};setup=world(doc,0)
    attachments={n:s[n] for n,s in doc['skins'][0]['attachments'].items()};output=[]
    for ri,relation in enumerate(arcs['analysis']['relations']):
        driver,follower=relation['driver'],relation['follower'];groups=[]
        original=boundary['relations'][ri]
        if (original['driver'],original['follower'])!=(driver,follower):raise ValueError('parameter_relation_identity')
        for group in relation['groups']:
            row={k:group[k] for k in ('driver_arc','follower_arc','pairs')};groups.append(row)
            if len(group['pairs'])<3:
                row.update(status='blocked',reason_code='insufficient_arc_pairs');continue
            arc=arcs['analysis']['arcs'][follower][group['follower_arc']];record=records[follower]
            lookup={a['source_sample']:a for a in record['anchors']};values=[];references=[]
            for pi in group['pairs']:
                pair=original['pairs'][pi];options=lookup[pair['follower_sample']]['options']
                params=[arc['edges'].index(o['edge'])+.5 for o in options if o['curve']==arc['curve'] and o['edge'] in arc['edges']]
                if not params:raise ValueError('parameter_anchor_missing')
                values.append(sum(params)/len(params))
                references.append(position(boundary['boundaries'][follower]['samples'][pair['follower_sample']],setup[follower]))
            alternatives=[]
            for sign in (1,-1):
                try:fitted=fit(values,len(arc['edges']),sign)
                except ValueError:continue
                samples=[sample(record,arc,v,attachments[follower]) for v in fitted]
                if any(s['embedding'] is None for s in samples):continue
                points=[position(s['embedding'],setup[follower]) for s in samples]
                shift=max(math.dist(a,b) for a,b in zip(points,references))
                if shift>2.:continue
                alternatives.append({'direction':sign,'cost':sum((a-b)**2 for a,b in zip(values,fitted)),
                                     'samples':samples,'max_world_shift_px':shift})
            if not alternatives:
                row.update(status='blocked',reason_code='no_bounded_embedded_monotone_solution');continue
            alternatives.sort(key=lambda a:(a['cost'],a['direction']));best=alternatives[0]
            row.update(status='candidate_requires_review',reason_code='continuous_parameter_candidate',reference_parameters=values,
                       **best,orientation_margin=alternatives[1]['cost']-best['cost'] if len(alternatives)>1 else None)
        output.append({'driver':driver,'follower':follower,'source_pair_count':relation['source_pair_count'],
                       'groups':groups,'blocked_pairs':relation['blocked_pairs']})
    return {'profile':'bounded-isotonic-gap01-budget2-v1','relations':output,'spacing_edges':.1,
            'parameter_budget_edges':2.,'world_shift_budget_px':2.,'authority':'none','deform_solver':'not_run'}
