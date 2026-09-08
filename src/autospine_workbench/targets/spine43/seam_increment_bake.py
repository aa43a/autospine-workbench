"""Bake bounded increments on the fixed continuous-anchor deform."""
from copy import deepcopy
from .alpha_seam import position,analyze
from .continuous_pose import world,inspect,interpolate
from .seam_translation import rotation,rotate,influences
from .seam_increment import solve


def bake(source,reference,files,mapped,parameters):
    doc=deepcopy(source);animation=next(iter(doc['animations'].values()));setup=world(source,0);records=[]
    if len(mapped['relations'])!=len(parameters['analysis']['relations']):raise ValueError('shape_relation_count')
    for relation,proposal in zip(mapped['relations'],parameters['analysis']['relations']):
        driver,follower=relation['driver'],relation['follower']
        if (driver,follower)!=(proposal['driver'],proposal['follower']):raise ValueError('shape_relation_identity')
        if sum(r['follower']==follower for r in mapped['relations'])!=1:raise ValueError('shape_multiple_drivers')
        attachment=doc['skins'][0]['attachments'][follower][follower];bones=influences(attachment)
        if len(bones)!=1 or len(attachment['vertices'])!=len(setup[follower])*5:raise ValueError('shape_nonrigid_follower')
        bone=next(iter(bones));flat=attachment['triangles'];triangles=[flat[i:i+3] for i in range(0,len(flat),3)]
        anchors=[mapped['boundaries'][follower]['samples'][p['follower_sample']] for p in relation['pairs']]
        chains=[g['pairs'] for g in proposal['groups'] if g['status']=='candidate_requires_review']
        keys=[];frames=[];rotation0=rotation(source,bone,0)
        for frame in range(61):
            time=frame/30;pose=world(source,time);reference_pose=world(reference,time);angle=rotation(source,bone,time);targets=[]
            for pair,anchor in zip(relation['pairs'],anchors):
                driver_anchor=mapped['boundaries'][driver]['samples'][pair['driver_sample']]
                left0,right0=position(driver_anchor,setup[driver]),position(anchor,setup[follower])
                rest=rotate([right0[k]-left0[k] for k in (0,1)],angle-rotation0)
                left,right=position(driver_anchor,pose[driver]),position(anchor,pose[follower])
                targets.append([left[k]+rest[k]-right[k] for k in (0,1)])
            if frame in (0,60):moves=[[0.,0.] for _ in pose[follower]];qa={'status':'endpoint_zero','scale':0.,'backtracks':0}
            else:moves,qa=solve(reference_pose[follower],pose[follower],anchors,targets,triangles,chains)
            frames.append({'time':time,**qa})
            old=animation['attachments']['default'].get(follower,{}).get(follower,{}).get('deform')
            prior=interpolate(old,time,'vertices') if old else [0.]*(len(moves)*2)
            local=[v for move in moves for v in rotate(move,-angle)]
            keys.append({'time':time,'vertices':[a+b for a,b in zip(prior,local)]})
        animation['attachments']['default'][follower]={follower:{'deform':keys}}
        records.append({'driver':driver,'follower':follower,'frames':frames})
    doc['animations']={'seam-increment-inspection':animation};geometry=inspect(doc);after=analyze(doc,files)
    passed=(all(r['passed'] for r in geometry['regions'].values()) and all(r['status']!='blocked' for r in after['relations'])
            and all(f['status']!='blocked' for r in records for f in r['frames']))
    return doc,{'profile':'fixed-deform-increment2-v1','geometry':geometry,'after':after,'solver_frames':records,
               'authority':'none','status':'candidate_noop' if not records else ('candidate_requires_review' if passed else 'blocked')}
