"""Static eyelash ownership from already bound bilateral eye neighborhoods."""
from copy import deepcopy
from ..asset.joints.mesh_candidate import _image
from ..resolved_project import canonical_sha256
from .head_parts_policy import propose as previous

POLICY = 'bound-eye-neighborhood-binding-v6'
LIMITS = {'alpha': 8, 'eye_margin_ratio': .5, 'min_eye_face_overlap': .98,
          'max_eye_face_area_ratio': .2, 'minimum_visible_pixels': 16}


def evidence(layer, eye, other, face, images):
    def pixels(item):
        image = _image(item, images); x, y = item['bbox'][:2]
        return {(x+i%image.width, y+i//image.width) for i,a in enumerate(image.pixels[3::4]) if a >= LIMITS['alpha']}
    points, ep, op, fp = [pixels(item) for item in (layer, eye, other, face)]
    if not ep or not op or not fp:
        return {}, {'visible_eye_references': False}
    x0=min(x for x,y in ep); y0=min(y for x,y in ep)
    x1=max(x for x,y in ep)+1; y1=max(y for x,y in ep)+1
    w=x1-x0; h=y1-y0; margin=LIMITS['eye_margin_ratio']
    bounds=[x0-w*margin,y0-h*margin,x1+w*margin,y1+h*margin]
    fx,fy,fr,fb=face['bbox']; area=(fr-fx)*(fb-fy)
    outside=sum(not(bounds[0]<=x<bounds[2] and bounds[1]<=y<bounds[3]) for x,y in points)
    face_outside=sum(not(fx<=x<fr and fy<=y<fb) for x,y in points)
    opposite_inside=sum(bounds[0]<=x<bounds[2] and bounds[1]<=y<bounds[3] for x,y in op)
    overlap=min(len(ep&fp)/len(ep),len(op&fp)/len(op))
    checks=dict(nonempty=len(points)>=LIMITS['minimum_visible_pixels'],
        visible_eye_references=min(len(ep),len(op))>=LIMITS['minimum_visible_pixels'],
        eye_face_support=overlap>=LIMITS['min_eye_face_overlap'],
        small_eye_reference=area>0 and w*h/area<=LIMITS['max_eye_face_area_ratio'],
        inside_eye_neighborhood=outside==0,inside_face_bounds=face_outside==0,
        distinct_eye_neighborhood=opposite_inside==0,eyelash_eye_contact=bool(points&ep))
    values=dict(face_layer_id=face['layer_id'],face_image_sha256=face['image_sha256'],
        eye_layer_id=eye['layer_id'],eye_image_sha256=eye['image_sha256'],
        other_eye_layer_id=other['layer_id'],other_eye_image_sha256=other['image_sha256'],
        image_sha256=layer['image_sha256'],visible_pixels=len(points),outside_eye_pixels=outside,
        outside_face_bounds_pixels=face_outside,opposite_eye_pixels=opposite_inside,
        eye_face_overlap_ratio=overlap,allowed_min_xy=bounds[:2],allowed_max_xy=bounds[2:],
        mode='static_head_follow_no_expression')
    return values,checks


def propose(source):
    result=previous(source)
    result.update(schema='autospine.simple-binding-policy/v6',policy_id=POLICY)
    result['limits']['eye_neighborhood']=deepcopy(LIMITS)
    layers={l['layer_id']:l for l in source.candidate['layers']}
    bound=[layers[r['layer_id']] for r in source.draft['records']
           if r['action']=='bind' and r['option_id']=='rigid:head']
    faces=[l for l in bound if l.get('semantic')=='body.face']
    eyes={s:[l for l in bound if l['name'].strip().lower()=='eyewhite-'+s
             and l.get('semantic') in (None,'face.eye.white')] for s in ('l','r')}
    anchors={r['joint_id']:r for r in source.assisted['draft']['records']}
    if (len(faces)!=1 or any(len(v)!=1 for v in eyes.values())
        or not {'head','neck'}<=set(source.assisted['reviewed_joint_ids'])
        or any(anchors[k]['status']!='observed' for k in ('head','neck'))): return result
    bindings={r['layer_id']:r for r in source.bindings['bindings']}
    for row in result['rows']:
        if row['status']!='needs_review' or row['reason_codes']!=['visible_face_containment']: continue
        layer=layers[row['layer_id']];name=layer['name'].strip().lower()
        if name not in ('eyelash-l','eyelash-r') or layer.get('semantic') not in (None,'face.eye.lash'): continue
        options=bindings[layer['layer_id']]['options']
        if len(options)!=1 or options[0]['id']!='rigid:head' or options[0]['bone_ids']!=['head']: continue
        side=name[-1]
        values,checks=evidence(layer,eyes[side][0],eyes['r' if side=='l' else 'l'][0],faces[0],source.images)
        row.update(evidence=values,checks=checks,reason_codes=[k for k,v in checks.items() if not v])
        if all(checks.values()): row.update(status='eligible',option_id='rigid:head')
    return result


def validate(source,document):
    expected=propose(source)
    if canonical_sha256(document)!=canonical_sha256(expected): raise ValueError('binding_policy_mismatch')
    return expected
