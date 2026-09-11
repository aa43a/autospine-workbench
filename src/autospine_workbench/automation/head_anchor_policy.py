"""Seed a face/neck binding from reviewed anchors and mutually consistent source pixels."""
from copy import deepcopy
import math
from ..asset.joints.mesh_candidate import _image
from ..resolved_project import canonical_sha256
from .foot_contact_policy import propose as previous

POLICY='reviewed-head-anchor-binding-v4'
LIMITS={'alpha':8,'max_face_anchor_span_ratio':3,'max_neck_width_anchor_span_ratio':1,
        'minimum_overlap_pixels':16,'minimum_visible_pixels':64}


def anchor_evidence(face,neck,head_point,neck_point,images):
    def pixels(layer):
        image=_image(layer,images);x,y=layer['bbox'][:2]
        return {(x+i%image.width,y+i//image.width) for i,a in enumerate(image.pixels[3::4]) if a>=LIMITS['alpha']}
    fp,np=pixels(face),pixels(neck);span=math.dist(head_point,neck_point)
    f=face['bbox'];n=neck['bbox'];overlap=len(fp&np)
    checks=dict(head_anchor_visible=tuple(map(math.floor,head_point)) in fp,
                neck_anchor_visible=tuple(map(math.floor,neck_point)) in np,
                head_above_neck=head_point[1]<neck_point[1],
                face_above_neck=f[3]<=neck_point[1],neck_below_head=n[1]>=head_point[1],
                compact_face=span>0 and max(f[2]-f[0],f[3]-f[1])<=span*LIMITS['max_face_anchor_span_ratio'],
                compact_neck=span>0 and n[2]-n[0]<=span*LIMITS['max_neck_width_anchor_span_ratio'],
                face_neck_contact=overlap>=LIMITS['minimum_overlap_pixels'],
                visible_head_parts=min(len(fp),len(np))>=LIMITS['minimum_visible_pixels'])
    return dict(face_layer_id=face['layer_id'],neck_layer_id=neck['layer_id'],face_sha256=face['image_sha256'],
                neck_sha256=neck['image_sha256'],head_point=head_point,neck_point=neck_point,overlap_pixels=overlap),checks


def propose(source):
    result=previous(source);result.update(schema='autospine.simple-binding-policy/v4',policy_id=POLICY)
    result['limits']['head_anchor']=deepcopy(LIMITS)
    layers=source.candidate['layers'];faces=[l for l in layers if l['semantic']=='body.face' and l['name'].strip().lower()=='face']
    necks=[l for l in layers if l['semantic']=='body.neck' and l['name'].strip().lower()=='neck']
    if len(faces)!=1 or len(necks)!=1:return result
    anchors={r['joint_id']:r for r in source.assisted['draft']['records']}
    reviewed=set(source.assisted['reviewed_joint_ids'])
    if not {'head','neck'}<=reviewed or any(anchors[k]['status']!='observed' for k in ('head','neck')):return result
    values,checks=anchor_evidence(faces[0],necks[0],anchors['head']['position'],anchors['neck']['position'],source.images)
    options={r['layer_id']:r['options'] for r in source.bindings['bindings']}
    targets={faces[0]['layer_id']:'rigid:head',necks[0]['layer_id']:'rigid:neck'}
    for row in result['rows']:
        key=row['layer_id']
        if key not in targets or row['status']!='needs_review' or row['reason_codes']!=['policy_capability_unsupported']:continue
        if len(options[key])!=1 or options[key][0]['id']!=targets[key]:continue
        row.update(evidence=deepcopy(values),checks=deepcopy(checks),reason_codes=[k for k,v in checks.items() if not v])
        if all(checks.values()):row.update(status='eligible',option_id=targets[key])
    return result


def validate(source,document):
    expected=propose(source)
    if canonical_sha256(document)!=canonical_sha256(expected):raise ValueError('binding_policy_mismatch')
    return expected
