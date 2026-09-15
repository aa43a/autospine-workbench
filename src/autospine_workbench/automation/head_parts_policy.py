"""Bounded static head-part defaults; long hair and ambiguous ownership stay pending."""
from copy import deepcopy
from ..asset.joints.mesh_candidate import _image
from ..resolved_project import canonical_sha256
from .head_anchor_policy import propose as previous

POLICY='bounded-head-parts-binding-v5'
LIMITS={'alpha':8,'horizontal_face_margin':.5,'upper_face_margin':.5,
        'lower_face_margin':.25,'minimum_overlap_pixels':16,'minimum_visible_pixels':16}
NAMES={'back hair':'hair.back','front hair':'hair.front','ears':None,
       'ears-l':'face.ear','ears-r':'face.ear'}


def evidence(layer,face,images):
    def pixels(item):
        image=_image(item,images);x,y=item['bbox'][:2]
        return {(x+i%image.width,y+i//image.width) for i,a in enumerate(image.pixels[3::4]) if a>=LIMITS['alpha']}
    points,face_points=pixels(layer),pixels(face)
    x0,y0,x1,y1=face['bbox'];w=x1-x0;h=y1-y0
    bounds=[x0-w*LIMITS['horizontal_face_margin'],y0-h*LIMITS['upper_face_margin'],
            x1+w*LIMITS['horizontal_face_margin'],y1+h*LIMITS['lower_face_margin']]
    outside=sum(not(bounds[0]<=x<bounds[2] and bounds[1]<=y<bounds[3]) for x,y in points)
    overlap=len(points&face_points)
    checks=dict(nonempty=len(points)>=LIMITS['minimum_visible_pixels'],bounded_head_extent=outside==0,
                face_contact=overlap>=LIMITS['minimum_overlap_pixels'])
    return dict(face_layer_id=face['layer_id'],face_image_sha256=face['image_sha256'],
                image_sha256=layer['image_sha256'],visible_pixels=len(points),outside_pixels=outside,
                overlap_pixels=overlap,allowed_min_xy=bounds[:2],allowed_max_xy=bounds[2:],mode='static_head_follow'),checks


def propose(source):
    result=previous(source)
    result.update(schema='autospine.simple-binding-policy/v5',policy_id=POLICY)
    result['limits']['head_parts']=deepcopy(LIMITS)
    layers={l['layer_id']:l for l in source.candidate['layers']}
    faces=[layers[r['layer_id']] for r in source.draft['records'] if r['action']=='bind'
           and r['option_id']=='rigid:head' and layers[r['layer_id']].get('semantic')=='body.face']
    anchors={r['joint_id']:r for r in source.assisted['draft']['records']}
    if len(faces)!=1 or not {'head','neck'}<=set(source.assisted['reviewed_joint_ids']):return result
    if any(anchors[k]['status']!='observed' for k in ('head','neck')):return result
    options={r['layer_id']:r['options'] for r in source.bindings['bindings']}
    for row in result['rows']:
        if row['status']!='needs_review':continue
        layer=layers[row['layer_id']];name=layer['name'].strip().lower()
        if name not in NAMES or layer.get('semantic')!=NAMES[name]:continue
        choices=options[layer['layer_id']]
        if len(choices)!=1 or choices[0]['id']!='rigid:head' or choices[0]['bone_ids']!=['head']:continue
        values,checks=evidence(layer,faces[0],source.images)
        row.update(evidence=values,checks=checks,reason_codes=[k for k,v in checks.items() if not v])
        if all(checks.values()):row.update(status='eligible',option_id='rigid:head')
    return result


def validate(source,document):
    expected=propose(source)
    if canonical_sha256(document)!=canonical_sha256(expected):raise ValueError('binding_policy_mismatch')
    return expected
