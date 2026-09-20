"""Retain uncertain secondary influences as same-chain depth intervals."""
import math
from .mesh_depth_proxy import vertex_depths

PROFILE = 'same-arm-secondary-influence-depth-envelope-v1-experiment'


def build(document, mesh, segments, *, axis_lengths=None):
    lengths=axis_lengths or {}
    exact=vertex_depths(document,mesh,segments,endpoint_caps=True,axis_lengths=lengths)
    bones={b['name']:b for b in document['bones']}; envelopes={}
    for side in ('l','r'):
        chain=['upperarm_'+side,'forearm_'+side,'hand_'+side]
        if not all(n in bones and n in segments for n in chain): continue
        if any(bones[b].get('parent')!=a for a,b in zip(chain,chain[1:])): continue
        if any(abs(segments[a][1]-segments[b][0])>1e-7 for a,b in zip(chain,chain[1:])): continue
        values=[v for n in chain for v in segments[n]]
        if not all(math.isfinite(v) for v in values): raise ValueError('depth_interval_source_nonfinite')
        envelopes[side]=(min(values),max(values))
    data=mesh['vertices']; cursor=0; intervals=[]; bounded=[]
    for vertex,value in enumerate(exact):
        count=data[cursor]; cursor+=1; weights=data[cursor:cursor+4*count]; cursor+=4*count
        if value is not None:
            intervals.append([value,value]); continue
        names={document['bones'][weights[i]]['name'] for i in range(0,len(weights),4) if weights[i+3]>0}
        side=next((s for s in envelopes if names <= {'upperarm_'+s,'forearm_'+s,'hand_'+s}),None)
        if side is None or abs(sum(weights[i+3] for i in range(0,len(weights),4))-1)>1e-6:
            intervals.append(None); continue
        low=high=known=0.; valid=True; uncertain=[]
        for i in range(0,len(weights),4):
            index,x,y,weight=weights[i:i+4]
            if weight==0: continue
            bone=document['bones'][index]; name=bone['name']; length=lengths.get(name,bone.get('length',0))
            if not math.isfinite(length) or length<=0:
                valid=False; break
            if -.25*length<=x<=1.25*length:
                a,b=segments[name]; z=a+(b-a)*min(length,max(0,x))/length
                low+=weight*z; high+=weight*z; known+=weight
            else:
                low+=weight*envelopes[side][0]; high+=weight*envelopes[side][1]
                uncertain.append(dict(bone=name,weight=weight,source_envelope=list(envelopes[side])))
        if not valid or known<=0:
            intervals.append(None); continue
        intervals.append([low,high])
        bounded.append(dict(vertex=vertex,known_weight=known,uncertain_influences=uncertain))
    return dict(profile=PROFILE,intervals=intervals,bounded_vertices=bounded,authority='none',selected=False,
                assumption='out_of_axis_secondary_influence_depth_lies_within_observed_same_arm_chain',
                scope='bounded_candidate_model_not_anatomical_surface_measurement')
