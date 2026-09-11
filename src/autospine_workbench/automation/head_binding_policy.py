"""Extend compact-foot evidence with containment in an explicitly bound face."""
from copy import deepcopy

from ..asset.joints.mesh_candidate import _image
from ..resolved_project import canonical_sha256
from .simple_binding_policy import propose as foot_proposal, LIMITS as FOOT_LIMITS

POLICY='head-and-foot-binding-v2'
HEAD_LIMITS={'alpha':8,'min_face_overlap':.98,'max_feature_face_area_ratio':.35}


def propose(source):
    result=foot_proposal(source)
    result.update(schema='autospine.simple-binding-policy/v2',policy_id=POLICY,
                  limits={'foot':deepcopy(FOOT_LIMITS),'head':deepcopy(HEAD_LIMITS)})
    layers={r['layer_id']:r for r in source.candidate['layers']}
    candidates={r['layer_id']:r for r in source.bindings['bindings']}
    faces=[layers[r['layer_id']] for r in source.draft['records'] if r['action']=='bind' and
           r['option_id']=='rigid:head' and layers[r['layer_id']].get('semantic')=='body.face']
    if len(faces)!=1:return result
    face=faces[0];raster=_image(face,source.images);box=face['bbox']
    face_alpha=raster.pixels[3::4]
    for row in result['rows']:
        if row['status']!='needs_review' or row['reason_codes']!=['policy_capability_unsupported']:continue
        binding=candidates[row['layer_id']]
        # v3 creates these options only for recognized static head-detail names.
        if binding['reason_codes']!=['head_detail_name_candidate','visual_parent_review_required']:continue
        if len(binding['options'])!=1 or binding['options'][0]['id']!='rigid:head':continue
        layer=layers[row['layer_id']];image=_image(layer,source.images);alpha=image.pixels[3::4]
        active=overlap=0
        for i,a in enumerate(alpha):
            if a<HEAD_LIMITS['alpha']:continue
            active+=1
            x=layer['bbox'][0]+i%image.width-box[0];y=layer['bbox'][1]+i//image.width-box[1]
            if 0<=x<raster.width and 0<=y<raster.height and face_alpha[y*raster.width+x]>=HEAD_LIMITS['alpha']:overlap+=1
        ratio=overlap/active if active else 0
        area=image.width*image.height/(raster.width*raster.height)
        checks={'visible_face_containment':ratio>=HEAD_LIMITS['min_face_overlap'],
                'small_head_feature':area<=HEAD_LIMITS['max_feature_face_area_ratio'],'nonempty':active>0}
        row.update(checks=checks,evidence={'face_layer_id':face['layer_id'],'face_image_sha256':face['image_sha256'],
                   'visible_pixels':active,'overlapping_pixels':overlap,'face_overlap_ratio':ratio,'feature_face_area_ratio':area},
                   reason_codes=[k for k,v in checks.items() if not v])
        if all(checks.values()):row.update(status='eligible',option_id='rigid:head')
    return result


def validate(source,document):
    expected=propose(source)
    if canonical_sha256(document)!=canonical_sha256(expected):raise ValueError('binding_policy_mismatch')
    return expected
