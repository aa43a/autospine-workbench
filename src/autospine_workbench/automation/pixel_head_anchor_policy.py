"""Compare exclusive raster bounds and reviewed anchors in the same pixel cells."""
import math
from ..resolved_project import canonical_sha256
from .eye_neighborhood_policy import propose as previous

POLICY = 'pixel-cell-head-anchor-binding-v7'


def propose(source):
    result = previous(source)
    result.update(schema='autospine.simple-binding-policy/v7', policy_id=POLICY)
    layers = {row['layer_id']: row for row in source.candidate['layers']}
    for row in result['rows']:
        # The preceding policy already verifies unique semantics/options, reviewed
        # visible anchors, contact, dimensions, and preservation of manual choices.
        if row['status'] != 'needs_review' or row['reason_codes'] != ['face_above_neck']:
            continue
        evidence = row['evidence']
        face = layers[evidence['face_layer_id']]
        bottom = face['bbox'][3]
        neck_y = evidence['neck_point'][1]
        if not math.isfinite(bottom) or not math.isfinite(neck_y) or bottom != int(bottom):
            continue
        # bbox max is exclusive: bottom-1 is the last represented pixel row.
        # Accept only that same row, never an arbitrary distance tolerance.
        if bottom - 1 != math.floor(neck_y):
            continue
        evidence.update(face_last_pixel_row=bottom - 1, neck_pixel_row=math.floor(neck_y),
                        coordinate_rule='exclusive_bbox_same_pixel_cell')
        row['checks'].pop('face_above_neck')
        row['checks']['face_not_below_neck_pixel_cell'] = True
        row.update(status='eligible', reason_codes=[],
                   option_id='rigid:head' if row['layer_id'] == face['layer_id'] else 'rigid:neck')
    return result


def validate(source, document):
    expected = propose(source)
    if canonical_sha256(document) != canonical_sha256(expected):
        raise ValueError('binding_policy_mismatch')
    return expected
