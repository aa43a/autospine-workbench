"""Full source replay for discrete ordinary sleeve deformation candidates."""
from .ordinary_sleeve_deform import build, SCHEMA, PROFILE
from ...resolved_project import canonical_sha256


def validate(document, *, repair, source, draft, skeleton):
    if (not isinstance(document, dict) or document.get('schema') != SCHEMA
            or document.get('profile') != PROFILE):
        raise ValueError('ordinary_deform_contract_invalid')
    for key, value in [('repair_sha256', repair), ('source_sha256', source),
                       ('draft_sha256', draft), ('skeleton_sha256', skeleton)]:
        if document.get(key) != canonical_sha256(value):
            raise ValueError('ordinary_deform_source_mismatch')
    expected = build(repair, source, draft, skeleton)
    if canonical_sha256(document) != canonical_sha256(expected):
        raise ValueError('ordinary_deform_replay_mismatch')
    return document
