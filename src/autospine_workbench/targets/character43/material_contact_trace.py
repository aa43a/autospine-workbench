"""Identity-bound material drift over an explicit interval, not floor inference."""
from hashlib import sha256
from io import BytesIO
import math

from PIL import Image
from ...resolved_project import canonical_sha256
from .active_mesh_pose import sample_active
from .pose_variant_transition import _map
from .pose_geometry_patch import _times


def trace(document, textures, request):
    if request['document_sha256']!=canonical_sha256(document):
        raise ValueError('material_contact_document_changed')
    start,end=request['interval'];times=request['times'];limit=request['limit_px']
    if (not all(type(t) in (int,float) and math.isfinite(t) for t in [start,end,limit,*times])
            or start<0 or end<=start or limit<=0 or not 2<=len(times)<=4096
            or times[0]!=start or times[-1]!=end or any(b<=a for a,b in zip(times,times[1:]))):
        raise ValueError('material_contact_times_or_limit')
    if end>max(_times(document['animations'][request['animation']]),default=0):
        raise ValueError('material_contact_interval_outside_animation')
    anchors=request['anchors']
    if not 1<=len(anchors)<=64 or len({a['id'] for a in anchors})!=len(anchors):
        raise ValueError('material_contact_anchor_inventory')
    for anchor in anchors:
        uv=anchor['uv'];path=anchor['texture_path']
        if len(uv)!=2 or not all(type(v) in (int,float) and math.isfinite(v) and 0<=v<1 for v in uv):
            raise ValueError('material_contact_uv')
        if path not in textures or sha256(textures[path]).hexdigest()!=anchor['texture_sha256']:
            raise ValueError('material_contact_texture_changed')
        with Image.open(BytesIO(textures[path])) as image:
            alpha=image.convert('RGBA').getpixel((int(uv[0]*image.width),int(uv[1]*image.height)))[3]
        if alpha<8:raise ValueError('material_contact_transparent_anchor')
    rows={a['id']:dict(id=a['id'],slot=a['slot'],uv=a['uv'],samples=[]) for a in anchors}
    origins={};budget=2_000_000
    for time in times:
        active=sample_active(document,request['animation'],time)
        for anchor in anchors:
            slot=anchor['slot'];name=active['attachments'].get(slot)
            item=dict(time=time,attachment=name)
            if name is None:
                item['status']='attachment_hidden_or_missing'
            else:
                mesh=document['skins'][0]['attachments'][slot][name]
                path='images/'+mesh.get('path',name)+'.png'
                if path!=anchor['texture_path']:
                    item['status']='material_correspondence_missing'
                else:
                    uv=[mesh['uvs'][i:i+2] for i in range(0,len(mesh['uvs']),2)]
                    flat=mesh['triangles'];tri=[flat[i:i+3] for i in range(0,len(flat),3)]
                    budget-=len(tri)
                    if budget<0:raise ValueError('material_contact_sample_budget')
                    hits=_map(anchor['uv'],uv,tri,active['vertices'][slot])
                    item['status']='uncovered_uv' if not hits else 'ambiguous_uv' if len(hits)>1 else 'measured'
                    if len(hits)==1:
                        point=hits[0];item['world']=point
                        if time==start:origins[anchor['id']]=point
                        if anchor['id'] in origins:
                            item['drift_px']=math.dist(point,origins[anchor['id']])
                        else:item['status']='interval_origin_unresolved'
            rows[anchor['id']]['samples'].append(item)
    for row in rows.values():
        measured=[s['drift_px'] for s in row['samples'] if s['status']=='measured']
        row['unresolved_samples']=sum(s['status']!='measured' for s in row['samples'])
        row['maximum_drift_px']=max(measured,default=None)
        row['passed']=False if any(v>limit for v in measured) else None if row['unresolved_samples'] else True
    records=list(rows.values())
    return dict(profile='active-material-contact-trace-v1',document_sha256=request['document_sha256'],
        request_sha256=canonical_sha256(request),records=records,limit_px=limit,
        interval_convention='closed_diagnostic_interval',
        passed=False if any(r['passed'] is False for r in records) else None if any(r['passed'] is None for r in records) else True,
        authority='none',selected=False,
        scope='explicit_interval_material_drift_not_sole_classification_floor_or_gpu_contact')
