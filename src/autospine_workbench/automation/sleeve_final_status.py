"""Derive final diagnostics from validated stages; never grant adoption authority."""
from copy import deepcopy


def finalize(report):
    result = deepcopy(report)
    rows = result['records']
    for row in rows:
        if row['status'] != 'candidate_exported':
            row['download'] = None
            continue
        frame = row.get('official_framebuffer')
        if frame and frame['failed_samples']:
            row.update(status='blocked', reason_code='official_framebuffer_contact_failure', download=None)
        elif row.get('runtime_status') == 'core_failed':
            row.update(status='blocked', reason_code='official_core_numeric_failure', download=None)
        elif frame:
            # Absence of a software peak is not a whole-surface overlap pass.
            row['reason_code'] = ('sleeve_occlusion_review_required' if row.get('runtime_status') == 'core_passed'
                                  else 'official_core_required')
        elif row.get('runtime_status') == 'core_passed':
            row['reason_code'] = 'official_framebuffer_required'
    captured = [r['official_framebuffer'] for r in rows if r.get('official_framebuffer')]
    result['alpha_contact_status'] = (
        'sampled_contacts_failed' if any(f['failed_samples'] for f in captured) else
        'sampled_contacts_passed' if rows and len(captured) == len(rows) else
        'partially_evaluated' if captured else 'not_evaluated')
    result['status'] = 'needs_review' if any(r['download'] for r in rows) else 'blocked'
    result.update(authority='none', production_authorized=False)
    return result
