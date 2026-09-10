"""Replay the complete bounded repair against its immutable input closure."""
from .ordinary_sleeve_repair import build, SCHEMA, PROFILE
from ...resolved_project import canonical_sha256


def validate(document, skeleton, *, source, draft):
    """Require all inputs: a selected row alone cannot prove a repair decision."""
    if not isinstance(document, dict) or document.get('schema') != SCHEMA or document.get('profile') != PROFILE:
        raise ValueError('ordinary_sleeve_repair_contract_invalid')
    for key, value in [('source_sha256', source), ('draft_sha256', draft), ('skeleton_sha256', skeleton)]:
        if document.get(key) != canonical_sha256(value):
            raise ValueError('ordinary_sleeve_repair_source_mismatch')
    # Exact replay checks every trial, rejected result, protected vertex, status,
    # sampled point, tick metric and selection; no floating-point tolerance here.
    expected = build(source, draft, skeleton)
    if canonical_sha256(document) != canonical_sha256(expected):
        raise ValueError('ordinary_sleeve_repair_replay_mismatch')
    return document
