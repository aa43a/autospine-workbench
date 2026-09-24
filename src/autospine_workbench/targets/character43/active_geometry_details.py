"""Reuse source-location analysis within one exact active attachment at a time."""
from hashlib import sha256
import json

from .active_deformation_qa import inspect
from .active_mesh_pose import active_document, sample_active


def build(files, artifact, document, samples, limit):
    from .motion_geometry_details import build as locate_fixed
    checked=inspect(document,samples)
    rows=[]
    for record in checked['records']:
        if record['passed']:
            continue
        animation,slot,attachment=(record[k] for k in ('animation','slot','attachment'))
        frames=[f for f in samples['animations'][animation] if f['attachments'][slot]==attachment]
        # Freeze only mesh identity. The source bone timeline remains unchanged;
        # the fixed analyzer removes deform only for its explicit counterfactual.
        normalized,_=active_document(document,animation,frames[0]['time'])
        rest=sample_active(document,animation,frames[0]['time'])['setup_vertices']
        raw=json.dumps(normalized).encode();digest=sha256(raw).hexdigest()
        def encode(value):
            return json.dumps(dict(skeleton_sha256=digest,**value)).encode()
        scoped=dict(files)
        scoped.update({'skeleton.json':raw,
            'numeric-reference.json':encode(dict(animations={animation:frames})),
            'rig-setup-reference.json':encode(dict(vertices=rest)),
            'deformation.json':encode(dict(records=[record]))})
        result=locate_fixed(scoped,artifact,limit=limit)
        for row in result['rows']:
            row.update(attachment=attachment,repair_scope='active_attachment_read_only',
                       source_skeleton_sha256=samples['skeleton_sha256'])
            for detail in row['details']:
                detail['attachment']=attachment
            row['note']+=' 当前按实际姿态附件定位；固定网格修正入口不适用于该记录。'
            rows.append(row)
    return dict(profile='motion-geometry-source-locations-v1',artifact_sha256=artifact,
        skeleton_sha256=samples['skeleton_sha256'],rows=rows,status='available',
        authority='none',selected=False,
        scope='sampled_active_attachment_area_locations_not_visual_acceptance')
