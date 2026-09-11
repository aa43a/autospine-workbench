"""Evidence checks for compact single-foot regions; no learned accuracy claim."""
from copy import deepcopy
import math

from ..asset.joints.layer_binding import validate_layer_bindings
from ..asset.joints.mesh_candidate import _image
from ..benchmark.layer_binding_draft import validate_layer_binding_draft
from ..resolved_project import canonical_sha256

POLICY = 'compact-foot-binding-v1'
LIMITS = {'alpha': 8, 'max_height_calf_ratio': .65, 'max_width_calf_ratio': .60,
          'max_above_ankle_calf_ratio': .20, 'min_other_ankle_margin_calf_ratio': .50}


def _evidence(layer, image, bones, side):
    ankle = bones['foot_'+side]['head_xy']
    other = bones['foot_'+('r' if side == 'l' else 'l')]['head_xy']
    length = bones['calf_'+side]['length']
    x0,y0,x1,y1 = layer['bbox']
    alpha = image.pixels[3::4]
    active = {i for i,a in enumerate(alpha) if a >= LIMITS['alpha']}
    components = 0
    remaining = set(active)
    while remaining:
        components += 1
        queue = [remaining.pop()]
        while queue:
            i = queue.pop(); x,y = i % image.width, i // image.width
            for j in (i-1 if x else -1, i+1 if x+1<image.width else -1,
                      i-image.width if y else -1, i+image.width if y+1<image.height else -1):
                if j in remaining:
                    remaining.remove(j); queue.append(j)
    cx,cy = (x0+x1)/2,(y0+y1)/2
    ix,iy = int(ankle[0]-x0),int(ankle[1]-y0)
    inside = 0 <= ix < image.width and 0 <= iy < image.height
    values = {'components': components, 'foreground_pixels': len(active),
              'ankle_on_foreground': inside and iy*image.width+ix in active,
              'height_calf_ratio': (y1-y0)/length, 'width_calf_ratio': (x1-x0)/length,
              'above_ankle_calf_ratio': max(0,ankle[1]-y0)/length,
              'other_ankle_margin_calf_ratio': (math.dist((cx,cy),other)-math.dist((cx,cy),ankle))/length}
    checks = {'one_connected_region': components == 1, 'nonempty': len(active)>=16,
              'ankle_on_foreground': values['ankle_on_foreground'],
              'compact_height': values['height_calf_ratio'] <= LIMITS['max_height_calf_ratio'],
              'compact_width': values['width_calf_ratio'] <= LIMITS['max_width_calf_ratio'],
              'no_calf_span': values['above_ankle_calf_ratio'] <= LIMITS['max_above_ankle_calf_ratio'],
              'separated_sides': values['other_ankle_margin_calf_ratio'] >= LIMITS['min_other_ankle_margin_calf_ratio']}
    return values, checks


def propose(source):
    validate_layer_bindings(source.candidate,source.assisted,source.skeleton,source.bindings)
    validate_layer_binding_draft(source.bindings,source.draft)
    bones = {b['id']:b for b in source.skeleton['bones']}
    rows = []
    for layer,binding,record in zip(source.candidate['layers'],source.bindings['bindings'],source.draft['records']):
        row = {'layer_id':layer['layer_id'],'status':'needs_review','option_id':None,
               'reason_codes':[],'evidence':{},'checks':{}}
        if record['action'] != 'pending' or record['notes'].strip():
            row.update(status='preserved',reason_codes=['existing_review_preserved'])
        elif 'footwear_name_candidate' not in binding['reason_codes']:
            row['reason_codes']=['policy_capability_unsupported']
        else:
            option = binding['suggested_option_id']
            if option not in ('rigid:foot_l','rigid:foot_r'):
                row['reason_codes']=['side_name_required']
            else:
                image = _image(layer,source.images)
                values,checks = _evidence(layer,image,bones,option[-1])
                row.update(evidence=values,checks=checks,reason_codes=[k for k,v in checks.items() if not v])
                if all(checks.values()):row.update(status='eligible',option_id=option)
        rows.append(row)
    # Multiple regions targeting the same foot need ownership/occlusion review.
    claimed=[r['option_id'] for r in source.draft['records'] if r['action']=='bind']
    eligible=[r['option_id'] for r in rows if r['status']=='eligible']
    for row in rows:
        if row['status']=='eligible' and (row['option_id'] in claimed or eligible.count(row['option_id'])>1):
            row.update(status='needs_review',option_id=None,reason_codes=['shared_foot_ownership_required'])
    return {'schema':'autospine.simple-binding-policy/v1','authority':'none','production_authorized':False,
            'policy_id':POLICY,'limits':deepcopy(LIMITS),'calibration_status':'unmeasured',
            'source_addresses':deepcopy(source.source_addresses),'rows':rows}


def validate(source, document):
    expected = propose(source)
    if canonical_sha256(expected)!=canonical_sha256(document):raise ValueError('binding_policy_mismatch')
    return expected
