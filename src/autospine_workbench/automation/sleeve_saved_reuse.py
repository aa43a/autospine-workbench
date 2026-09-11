"""Retain saved labels only when the entire annotation surface is identical."""
from copy import deepcopy

from ..asset.planning.sleeve_regions import validate
from ..resolved_project import canonical_sha256


def reuse(previous, candidate, draft, current, resolved_sha256):
    validate(draft, candidate)
    if not previous['saved'] or previous['source_sha256'] != resolved_sha256:
        return None
    # Source closure changes with unrelated bindings. All other fields, including
    # the skeleton, texture identities, winding and suggestions must be identical.
    before, after = deepcopy(candidate), deepcopy(current)
    before.pop('source_sha256'); after.pop('source_sha256')
    if before != after:
        return None
    result = deepcopy(draft)
    result['candidate_sha256'] = canonical_sha256(current)
    validate(result, current)
    receipt = dict(schema='autospine.sleeve-saved-reuse/v1',
        profile='identical-annotation-surface-v1', authority='none',
        production_authorized=False, motion_review_reused=False,
        previous_revision=previous['revision'],
        previous_registration_sha256=canonical_sha256(previous),
        previous_candidate_sha256=canonical_sha256(candidate),
        previous_draft_sha256=canonical_sha256(draft),
        candidate_sha256=canonical_sha256(current),
        draft_sha256=canonical_sha256(result))
    return result, receipt
