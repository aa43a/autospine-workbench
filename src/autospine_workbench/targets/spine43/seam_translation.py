"""Alpha-supported seam candidates; bounded rigid distal translation only."""
from copy import deepcopy
from io import BytesIO
import math
from .continuous_pose import world,interpolate,inspect


def influences(attachment):
    data=attachment['vertices'];indices=set();i=0
    while i<len(data):
        count=data[i];i+=1
        for _ in range(count):
            index,_,_,weight=data[i:i+4];i+=4
            if weight>0:indices.add(index)
    return indices


def rotation(doc,index,time):
    tracks=next(iter(doc['animations'].values()))['bones'];angles={}
    for bone in doc['bones']:
        keys=tracks.get(bone['name'],{}).get('rotate')
        angles[bone['name']]=angles.get(bone.get('parent'),0)+bone['rotation']+(interpolate(keys,time,'value') if keys else 0)
    return angles[doc['bones'][index]['name']]


def rotate(point,angle):
    a=math.radians(angle);x,y=point
    return [x*math.cos(a)-y*math.sin(a),x*math.sin(a)+y*math.cos(a)]


def candidates(doc,files):
    from PIL import Image
    setup=world(doc,0);attachments={n:s[n] for n,s in doc['skins'][0]['attachments'].items()};supported={}
    for name,a in attachments.items():
        with Image.open(BytesIO(files['editor/images/'+name+'.png'])) as image:
            alpha=image.convert('RGBA').getchannel('A');w,h=alpha.size;flags=[]
            for u,v in zip(a['uvs'][::2],a['uvs'][1::2]):
                x=max(0,min(w-1,round(u*w)));y=max(0,min(h-1,round(v*h)))
                flags.append(alpha.crop((max(0,x-2),max(0,y-2),min(w,x+3),min(h,y+3))).getextrema()[1]>=8)
            supported[name]=flags
    result=[]
    for follower,a in attachments.items():
        bones=influences(a)
        if len(bones)!=1:continue
        bone=next(iter(bones));options=[]
        for driver,b in attachments.items():
            if len(influences(b))<2 or bone not in influences(b):continue
            pairs=[]
            for i,p in enumerate(setup[driver]):
                if not supported[driver][i]:continue
                eligible=[j for j,flag in enumerate(supported[follower]) if flag]
                if not eligible:continue
                j=min(eligible,key=lambda j:math.dist(p,setup[follower][j]))
                if math.dist(p,setup[follower][j])<=4:pairs.append([i,j])
            if len(pairs)>=3:options.append({'driver':driver,'follower':follower,'bone_index':bone,'pairs':pairs})
        if len(options)==1:result.extend(options)
    return result


def constrain(source,files):
    if set(source['animations'])!={'continuous-corrective-inspection'}:raise ValueError('seam_source_animation_invalid')
    doc=deepcopy(source);animation=next(iter(doc['animations'].values()));setup=world(source,0)
    links=candidates(source,files);records=[]
    for link in links:
        driver,follower,bone,pairs=(link[k] for k in ('driver','follower','bone_index','pairs'))
        slot=source['skins'][0]['attachments'][follower][follower];count=len(slot['uvs'])//2;keys=[];maximum=0.;capped=0
        # Positive influence set must correspond to an actual single influence per vertex.
        if len(slot['vertices'])!=count*5:raise ValueError('seam_follower_encoding_unsupported')
        for frame in range(61):
            time=frame/30;pose=world(source,time);angle=rotation(source,bone,time);deltas=[]
            for i,j in pairs:
                rest=[setup[follower][j][k]-setup[driver][i][k] for k in (0,1)]
                rest=rotate(rest,angle-rotation(source,bone,0))
                deltas.append([pose[driver][i][k]+rest[k]-pose[follower][j][k] for k in (0,1)])
            delta=[sum(d[k] for d in deltas)/len(deltas) for k in (0,1)];length=math.hypot(*delta)
            if length>16:delta=[v*16/length for v in delta];capped+=1
            if frame in (0,60):delta=[0.,0.]
            maximum=max(maximum,math.hypot(*delta));local=rotate(delta,-angle)
            old=animation.get('attachments',{}).get('default',{}).get(follower,{}).get(follower,{}).get('deform')
            prior=interpolate(old,time,'vertices') if old else [0.]*(count*2)
            keys.append({'time':time,'vertices':[v+local[i%2] for i,v in enumerate(prior)]})
        animation['attachments']['default'][follower]={follower:{'deform':keys}}
        records.append({**link,'max_translation_px':maximum,'capped_keys':capped,'review_status':'pending'})
    doc['animations']={'seam-translation-inspection':animation}
    qa=inspect(doc);before=inspect(source)
    for record in records:
        driver,follower=record['driver'],record['follower']
        for label,item in (('before',source),('after',doc)):
            samples=[world(item,i/60) for i in range(121)]
            record[label+'_supported_growth_px']=max(math.dist(s[driver][i],s[follower][j])-math.dist(setup[driver][i],setup[follower][j]) for s in samples for i,j in record['pairs'])
    passed=all(r['passed'] for r in qa['regions'].values()) and all(s['status']!='blocked' for s in qa['seam_proxy'])
    return doc,{'candidates':records,'before':before,'after':qa,
                'status':'candidate_noop' if not links else ('candidate_requires_review' if passed else 'blocked'),
                'authority':'none','alpha_contact_coverage':'unproven','translation_limit_px':16}
