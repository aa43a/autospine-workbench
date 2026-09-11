"""Alternative shoe support from a selected leg pair and visible alpha overlap."""
from copy import deepcopy
from ..asset.joints.mesh_candidate import _image
from ..resolved_project import canonical_sha256
from .head_binding_policy import propose as previous_policy

POLICY='head-foot-contact-binding-v3'
LIMITS={'alpha':8,'min_shoe_overlap':.5,'min_side_overlap_margin':.5,
        'cuff_height_fraction':.2,'min_cuff_overlap':.5}


def _pixels(layer,images):
    image=_image(layer,images);x,y=layer['bbox'][:2]
    return {(x+i%image.width,y+i//image.width) for i,a in enumerate(image.pixels[3::4]) if a>=LIMITS['alpha']}


def contact_evidence(shoe,left,right,box,side):
    own,other=(left,right) if side=='l' else (right,left)
    cuff={p for p in shoe if p[1]<box[1]+(box[3]-box[1])*LIMITS['cuff_height_fraction']}
    ratio=len(shoe&own)/len(shoe) if shoe else 0
    opposite=len(shoe&other)/len(shoe) if shoe else 0
    cuff_ratio=len(cuff&own)/len(cuff) if cuff else 0
    values={'shoe_visible_pixels':len(shoe),'same_side_overlap_pixels':len(shoe&own),
            'other_side_overlap_pixels':len(shoe&other),'same_side_overlap_ratio':ratio,
            'side_overlap_margin':ratio-opposite,'cuff_overlap_ratio':cuff_ratio}
    checks={'reviewed_leg_overlap':ratio>=LIMITS['min_shoe_overlap'],
            'reviewed_leg_side_margin':ratio-opposite>=LIMITS['min_side_overlap_margin'],
            'reviewed_leg_cuff_overlap':cuff_ratio>=LIMITS['min_cuff_overlap']}
    return values,checks


def propose(source):
    result=previous_policy(source)
    result.update(schema='autospine.simple-binding-policy/v3',policy_id=POLICY)
    result['limits']['contact']=deepcopy(LIMITS)
    layers={r['layer_id']:r for r in source.candidate['layers']}
    options={r['layer_id']:r for r in source.bindings['bindings']}
    legs={side:[r['layer_id'] for r in source.draft['records'] if r['action']=='bind' and r['option_id']==f'mesh_chain:{side}:leg'] for side in ('l','r')}
    cache={}
    for row in result['rows']:
        if row['status']!='needs_review' or row['reason_codes']!=['ankle_on_foreground']:continue
        if any(len(ids)!=1 for ids in legs.values()):
            row['reason_codes'].append('reviewed_leg_pair_required');continue
        for ids in legs.values():
            if ids[0] not in cache:cache[ids[0]]=_pixels(layers[ids[0]],source.images)
        layer=layers[row['layer_id']];option=options[row['layer_id']]['suggested_option_id']
        values,checks=contact_evidence(_pixels(layer,source.images),cache[legs['l'][0]],cache[legs['r'][0]],layer['bbox'],option[-1])
        row['evidence'].update(values,reference_leg_left=legs['l'][0],reference_leg_right=legs['r'][0],
                              reference_left_sha256=layers[legs['l'][0]]['image_sha256'],reference_right_sha256=layers[legs['r'][0]]['image_sha256'])
        # Preserve the failed point test as evidence. The new policy accepts a
        # distinct, source-bound leg-support path rather than changing v1 limits.
        row['checks'].pop('ankle_on_foreground')
        row['checks'].update(checks)
        row['reason_codes']=[key for key,value in row['checks'].items() if not value]
        if all(row['checks'].values()):row.update(status='eligible',option_id=option)
    claimed=[r['option_id'] for r in source.draft['records'] if r['action']=='bind']
    eligible=[r['option_id'] for r in result['rows'] if r['status']=='eligible']
    for row in result['rows']:
        if row['status']=='eligible' and row['option_id'] in ('rigid:foot_l','rigid:foot_r') and (row['option_id'] in claimed or eligible.count(row['option_id'])>1):
            row.update(status='needs_review',option_id=None,reason_codes=['shared_foot_ownership_required'])
    return result


def validate(source,document):
    expected=propose(source)
    if canonical_sha256(expected)!=canonical_sha256(document):raise ValueError('binding_policy_mismatch')
    return expected
