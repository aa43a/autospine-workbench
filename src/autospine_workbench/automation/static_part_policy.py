"""Bounded static ear/headwear and torso defaults with explicit spatial support."""
from copy import deepcopy
import math
from ..asset.joints.mesh_candidate import _image
from ..resolved_project import canonical_sha256
from .pixel_head_anchor_policy import propose as previous
from .head_parts_policy import evidence as head_evidence

POLICY = 'supported-static-parts-binding-v8'
LIMITS = {'alpha': 8, 'minimum_pixels': 64, 'headwear_support_ratio': .98,
          'torso_side_margin_shoulder_ratio': .10}


def pixels(layer, images):
    image = _image(layer, images); x, y = layer['bbox'][:2]
    return {(x+i%image.width, y+i//image.width)
            for i, a in enumerate(image.pixels[3::4]) if a >= LIMITS['alpha']}


def torso_evidence(layer, anchors, images):
    points = pixels(layer, images)
    neck, pelvis = anchors['neck']['position'], anchors['pelvis']['position']
    shoulders = [anchors[k]['position'] for k in ('shoulder.left', 'shoulder.right')]
    left, right = sorted(p[0] for p in shoulders); width = right-left
    margin = width*LIMITS['torso_side_margin_shoulder_ratio']
    bounds = [left-margin, math.floor(neck[1]), right+margin, pelvis[1]]
    outside = sum(not(bounds[0] <= x <= bounds[2] and bounds[1] <= y <= bounds[3]) for x,y in points)
    chest = tuple(map(math.floor, anchors['chest']['position']))
    checks = dict(nonempty=len(points)>=LIMITS['minimum_pixels'],
                  ordered_torso=width>0 and neck[1]<anchors['chest']['position'][1]<pelvis[1],
                  bounded_torso_extent=outside==0, chest_on_foreground=chest in points)
    return dict(image_sha256=layer['image_sha256'], visible_pixels=len(points), outside_pixels=outside,
                allowed_min_xy=bounds[:2], allowed_max_xy=bounds[2:], mode='static_chest_follow'), checks


def propose(source):
    result = previous(source)
    result.update(schema='autospine.simple-binding-policy/v8', policy_id=POLICY)
    result['limits']['static_parts'] = deepcopy(LIMITS)
    layers = {r['layer_id']:r for r in source.candidate['layers']}
    options = {r['layer_id']:r['options'] for r in source.bindings['bindings']}
    bound = [layers[r['layer_id']] for r in source.draft['records']
             if r['action']=='bind' and r['option_id']=='rigid:head']
    faces = [r for r in bound if r['semantic']=='body.face']
    anchors = {r['joint_id']:r for r in source.assisted['draft']['records']}
    reviewed = set(source.assisted['reviewed_joint_ids'])
    def ready(keys):
        return set(keys)<=reviewed and all(anchors[k]['status']=='observed' for k in keys)
    for row in result['rows']:
        if row['status']!='needs_review': continue
        layer = layers[row['layer_id']]; name = layer['name'].strip().lower()
        target = None
        if name in ('ears-l','ears-r','headwear','headwear-front','headwear-back'):
            allowed = (None,'face.ear') if name.startswith('ears-') else (None,'accessory.headwear')
            if layer.get('semantic') not in allowed or len(faces)!=1 or not ready(('head','neck')): continue
            values, checks = head_evidence(layer, faces[0], source.images)
            if name.startswith('headwear'):
                support = set().union(*(pixels(r,source.images) for r in bound
                    if r['semantic'] in ('body.face','hair.front','hair.back')))
                points = pixels(layer,source.images)
                ratio = len(points & support)/len(points) if points else 0
                checks.pop('face_contact')
                checks['bound_head_support'] = ratio>=LIMITS['headwear_support_ratio']
                values['bound_head_support_ratio'] = ratio
            target = 'rigid:head'
        elif name in ('topwear','topwear-front') and layer.get('semantic')=='wear.top':
            if not ready(('neck','chest','pelvis','shoulder.left','shoulder.right')): continue
            values, checks = torso_evidence(layer,anchors,source.images)
            target = 'rigid:chest'
        else: continue
        choices = options[row['layer_id']]
        if len(choices)!=1 or choices[0]['id']!=target or choices[0]['bone_ids']!=[target.split(':')[1]]: continue
        row.update(evidence=values,checks=checks,reason_codes=[k for k,v in checks.items() if not v])
        if all(checks.values()): row.update(status='eligible',option_id=target)
    return result


def validate(source, document):
    expected = propose(source)
    if canonical_sha256(expected)!=canonical_sha256(document): raise ValueError('binding_policy_mismatch')
    return expected
