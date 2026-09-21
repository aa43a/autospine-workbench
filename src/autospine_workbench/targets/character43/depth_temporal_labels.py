"""Bounded joint temporal stabilization; only ambiguous labels may change."""
from .depth_binary_cut import solve
from .depth_temporal_graph import build
from .depth_coherent_frame import adjacency
from .depth_block_cut import solve_blocks

PROFILE='ambiguous-space-time-potts8-prior1-v1-experiment'


def stabilize(mesh,models,checks,arm,setup):
    nodes,unary,edges=build(mesh,models,checks,arm)
    initial={node:models[body][j]['labels'][i] for (body,j,i),node in nodes.items()}
    neighbours=[set() for _ in unary]
    for a,b,_ in edges:neighbours[a].add(b);neighbours[b].add(a)
    unseen=set(range(len(nodes)));records=[];values={}
    while unseen:
        stack=[min(unseen)];component=set(stack);unseen.remove(stack[0])
        while stack:
            for b in neighbours[stack.pop()]:
                if b in unseen:unseen.remove(b);component.add(b);stack.append(b)
        ordered=sorted(component);indices={v:i for i,v in enumerate(ordered)}
        selected=[(indices[a],indices[b],w) for a,b,w in edges if a in component]
        record=dict(nodes=len(ordered),edges=len(selected),status='held_resource_limit')
        if len(ordered)<=4096 and len(selected)<=16384:
            result=solve([unary[i] for i in ordered],selected)
            values.update(zip(ordered,result['labels']))
            record.update(status='solved',energy=result['energy'])
        else:
            try:result=solve_blocks([unary[i] for i in ordered],selected,[initial[i] for i in ordered])
            except ValueError as exc:
                if str(exc)!='depth_cut_resource_limit':raise
                result=dict(status='held_resource_limit')
            record.update({k:v for k,v in result.items() if k!='labels'})
            if result['status']=='locally_stable':values.update(zip(ordered,result['labels']))
        records.append(record)
    changed=0;adjacent=adjacency(mesh)
    for rows in models.values():
        for row in rows:row['pre_temporal_labels']=list(row['labels'])
    for (body,j,i),node in nodes.items():
        if node in values:
            row=models[body][j];changed+=row['labels'][i]!=values[node];row['labels'][i]=values[node]
    for body,rows in models.items():
        prior=[int(setup[body])]*(len(mesh['triangles'])//3)
        for row in rows:
            if 'energy' in row:row['pre_temporal_energy']=row.pop('energy')
            row['pre_temporal_transition_count']=row.get('transition_count',0)
            row['transition_count']=sum(a!=b for a,b in zip(prior,row['labels']));prior=row['labels']
            row['spatial_cuts']=sum(row['labels'][a]!=row['labels'][b] for a,b in adjacent
                                   if row['observed_states'][a]!='N' and row['observed_states'][b]!='N')
            row['temporal_profile']=PROFILE
    return dict(profile=PROFILE,ambiguous_nodes=len(nodes),changed_labels=changed,components=records,
                authority='none',selected=False,scope='regularized_inference_not_observed_depth')
