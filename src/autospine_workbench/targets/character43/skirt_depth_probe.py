"""Measure actual leg/skirt overlap under an explicit, unadopted plane model."""
from .cloth_depth_plane import at
from .mesh_depth_proxy import overlap_support
from .motion_depth_overlap import Probe
from .weighted_depth_interval import build


def groups(document):
    bones=document['bones'];legs=[];skirts=[]
    for slot in document['slots']:
        mesh=document['skins'][0]['attachments'].get(slot['name'],{}).get(slot.get('attachment'))
        if not mesh or mesh.get('type')!='mesh':continue
        raw=mesh.get('vertices',[])
        if len(raw)==len(mesh.get('uvs',[])):continue
        names=set();cursor=0
        while cursor<len(raw):
            count=raw[cursor];cursor+=1
            if type(count) is not int or count<1 or cursor+4*count>len(raw):raise ValueError('skirt_probe_weights_invalid')
            for i in range(count):
                index,_,_,weight=raw[cursor+4*i:cursor+4*i+4]
                if type(index) is not int or not 0<=index<len(bones):raise ValueError('skirt_probe_bone_invalid')
                if weight>0:names.add(bones[index]['name'])
            cursor+=4*count
        # These are the existing compiler's auxiliary-bone names, not character names.
        if any('-skirt_' in n for n in names):skirts.append(slot['name'])
        elif names & {'thigh_l','thigh_r','calf_l','calf_r'}:legs.append(slot['name'])
    return legs,skirts


def inspect(document,files,sampler,times):
    legs,skirts=groups(document)
    if len(times)>9 or len(legs)*len(skirts)>32:raise ValueError('skirt_probe_budget')
    probe=Probe(document,files,'external-motion',tiled=True,rendered_bounds=True)
    rows=[]
    if not legs or not skirts:
        return dict(profile='leg-skirt-plane-overlap-probe-v1',legs=legs,skirts=skirts,rows=[],
            status='unmeasured',reason_code='weighted_leg_or_skirt_mesh_missing',
            authority='none',selected=False,order_changed=False)
    for time in times:
        segments=sampler.leg_segments(round(time*1e6))
        try:plane=at(document,'external-motion',time,sampler,round(time*1e6))
        except ValueError as exc:
            rows.append(dict(time=time,status='unmeasured',reason_code=str(exc)));continue
        for leg in legs:
            mesh=document['skins'][0]['attachments'][leg][probe.slots[leg]['attachment']]
            intervals=build(document,mesh,segments,chain_kind='leg')['intervals']
            for skirt in skirts:
                try:
                    result=overlap_support(probe,leg,skirt,time,segments,endpoint_caps=True,
                        reference_plane=plane['coefficients'],depth_intervals=intervals)
                except ValueError as exc:result=dict(status='unmeasured',reason_code=str(exc),time=time,pair=[leg,skirt])
                rows.append(result)
    return dict(profile='leg-skirt-plane-overlap-probe-v1',legs=legs,skirts=skirts,rows=rows,status='candidate_model_only',
        authority='none',selected=False,order_changed=False,
        limitation='torso_plane_is_not_skirt_surface_do_not_auto_apply_order',
        scope='selected_pose_native_alpha_overlap_not_full_motion_acceptance')
