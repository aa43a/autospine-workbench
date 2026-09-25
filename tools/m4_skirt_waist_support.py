"""Recover fixed waist support from the existing same-material contact contract."""
from hashlib import sha256
import json
import math
from autospine_workbench.targets.character43.affine_pose import sample
from autospine_workbench.targets.character43.skirt_contact import source_image
from autospine_workbench.targets.character43.skirt_motion_contact import locate,transport


def fixed_region(source,current,slot):
    before=json.loads(source['skeleton.json']);after=json.loads(current['skeleton.json'])
    if any(before.get(k)!=after.get(k) for k in ('bones','slots','skins')):
        raise ValueError('skirt_waist_support_bind_mismatch')
    trial=json.loads(source['skirt-trial.json']);rows=[r for r in trial['rows'] if r['layer_id']==slot]
    if len(rows)!=1:raise ValueError('skirt_waist_support_row')
    positions=sample(dict(before,animations={'setup':{}}),'setup',0)[0]
    attachments=before['skins'][0]['attachments'];row=rows[0];ox,oy=row['origin']
    alpha=source_image(source,before,positions,slot)[0].getchannel('A');y=row['contact']['waist_y']
    left,right=row['contact']['overlap_x'];torso=[]
    for layer in json.loads(source['character-manifest.json'])['layers']:
        if layer['name'] in ('topwear','topwear-front') and layer['state']=='rigid_reviewed':
            for region in layer['regions']:
                other=region['region_id'];image,origin=source_image(source,before,positions,other)
                torso.append((other,image.getchannel('A'),origin))
    anchors=[]
    for x in sorted({round(left+(right-left)*i/16) for i in range(17)}):
        point=[ox+x+.5,oy-y-.5]
        if alpha.getpixel((x,y))<8:continue
        for other,mask,origin in torso:
            tx,ty=math.floor(point[0]-origin[0]),math.floor(origin[1]-point[1])
            if 0<=tx<mask.width and 0<=ty<mask.height and mask.getpixel((tx,ty))>=8:
                anchors.append(dict(point=point,torso=other,
                    skirt_anchor=locate(positions[slot],attachments[slot][slot]['triangles'],point),
                    torso_anchor=locate(positions[other],attachments[other][other]['triangles'],point)))
    if not anchors:raise ValueError('skirt_waist_support_unobservable')
    fixed=sorted({v for a in anchors for v in a['skirt_anchor'][0]})
    return fixed,dict(anchors=anchors,fixed_vertices=fixed,contact_source_sha256=sha256(source['skirt-trial.json']).hexdigest(),
        method='existing_alpha_supported_same_material_waist_samples',bind_identity_verified=True)


def contact_change(before,after,anchors):
    return max(math.dist(transport(before,a['skirt_anchor']),transport(after,a['skirt_anchor'])) for a in anchors)
