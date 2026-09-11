"""Source-closed ordinary deform target diagnostics; no production admission."""
from ...asset.planning.ordinary_deform_interpolation import validate as validate_interpolation
from ...resolved_project import canonical_sha256
from .ordinary_deform_encoding import encode
from .ordinary_deform_checks import inspect

SCHEMA = 'autospine.ordinary-deform-target/v1'
PROFILE = 'spine4326-ordinary-local-deform129-v1'


def build(interpolation, *, deform, repair, source, draft, skeleton):
    validate_interpolation(interpolation,deform=deform,repair=repair,source=source,draft=draft,skeleton=skeleton)
    sources = {(r['layer_id'],r['component_id']):r for r in source['records']}
    sampled = {(r['layer_id'],r['component_id']):r for r in interpolation['records']}
    records = []; documents = {}
    for row in deform['records']:
        key = row['layer_id'],row['component_id']
        result = dict(layer_id=key[0],component_id=key[1],status='blocked',reason_codes=[],
                      target_sha256=None,uv_sha256=None,isolated_image_sha256=None,qa=None)
        records.append(result)
        if sampled[key]['status']!='sampled_interpolation_passed':
            result['reason_codes'] = sampled[key]['reason_codes'][:]; continue
        saved = sources[key]; mesh = saved['mesh']
        doc = encode(row,mesh,skeleton,canonical_sha256(deform))
        qa = inspect(doc,row,skeleton)
        result.update(target_sha256=canonical_sha256(doc),uv_sha256=canonical_sha256(mesh['uvs']),
                      isolated_image_sha256=saved.get('isolated_image_sha256'),qa=qa)
        # Even failing target documents are diagnostic-only; callers must gate export.
        documents[result['target_sha256']] = doc
        if not qa['passed']:
            result['reason_codes'] = sorted({r for t in qa['checks'] for r in t['reason_codes']})
        else:
            result.update(status='target_sampled_passed',reason_codes=['temporal_visual_review_required',
                          'texture_and_alpha_contact_required','runtime_required'])
    report = dict(schema=SCHEMA,profile=PROFILE,target='4.3.26',project_id=deform['project_id'],
                  interpolation_sha256=canonical_sha256(interpolation),deform_sha256=canonical_sha256(deform),
                  source_sha256=canonical_sha256(source),skeleton_sha256=canonical_sha256(skeleton),records=records,
                  runtime_status='not_evaluated',texture_status='not_evaluated',authority='none',production_authorized=False)
    return report,documents


def validate(document, **inputs):
    expected,_ = build(**inputs)
    if canonical_sha256(expected)!=canonical_sha256(document):
        raise ValueError('ordinary_target_replay_mismatch')
    return document
