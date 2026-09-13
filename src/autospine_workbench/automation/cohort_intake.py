"""Read-only frozen-cohort intake; names are hints, never source authority."""
from pathlib import PurePosixPath


def assess(manifest, catalog, source_checks=None):
    if (manifest.get('schema') != 'autospine.benchmark-manifest/v1'
            or manifest.get('split_status') != 'frozen'
            or catalog.get('schema') != 'autospine.asset-library/v1'):
        raise ValueError('cohort_intake_source_invalid')
    characters = [c for c in manifest['characters']
                  if c['dataset_split'] in ('development', 'visible', 'holdout')]
    if len(characters) != 10 or len({c['id'] for c in characters}) != 10:
        raise ValueError('cohort_intake_requires_frozen_ten')
    projects = catalog['projects']
    if source_checks is not None and (source_checks.get('schema') != 'autospine.cohort-source-check/v1'
                                      or source_checks.get('authority') != 'none'):
        raise ValueError('cohort_intake_checks_invalid')
    if len({p['id'] for p in projects}) != len(projects):
        raise ValueError('cohort_intake_duplicate_project')
    rows = []
    for character in characters:
        candidates = character['psd_candidates']
        hashes = {c['source']['sha256'] for c in candidates}
        names = {PurePosixPath(c['source']['path']).stem for c in candidates}
        def matches(p):
            if source_checks is None:
                return p.get('source', {}).get('source_sha256') in hashes
            checked = source_checks['projects'].get(p['id'], {})
            return checked.get('status') == 'verified' and checked.get('source_sha256') in hashes
        exact = [p for p in projects if matches(p)]
        hints = [p for p in projects if p not in exact
                 and ((p.get('source', {}).get('kind') == 'audit' and p['id'] in names)
                      or p.get('source', {}).get('source_sha256') in hashes)]
        active = [p for p in exact if p['lifecycle'] == 'active']
        file_statuses = {source_checks.get('files', {}).get(h, {}).get('status') for h in hashes} if source_checks else set()
        if 'source_bytes_changed' in file_statuses:
            reason = 'frozen_psd_bytes_changed'
        elif 'source_unavailable' in file_statuses:
            reason = 'frozen_psd_unavailable'
        elif len(hashes) > 1:
            reason = 'psd_variant_review_required'
        elif len(active) > 1:
            reason = 'project_selection_required'
        elif active:
            reason = 'source_matched_workflow_not_assessed'
        elif exact:
            reason = 'asset_restore_required'
        elif hints:
            reason = 'audit_source_verification_required'
        else:
            reason = 'psd_import_required'
        def reference(p):
            return {key: p[key] for key in ('id', 'name', 'lifecycle', 'project_revision')}
        rows.append(dict(character_id=character['id'], name=PurePosixPath(character['source']['path']).stem,
                         dataset_split=character['dataset_split'], reason_code=reason,
                         exact_projects=[reference(p) for p in exact],
                         audit_hints=[reference(p) for p in hints],
                         psd_candidates=[c['source'] for c in candidates],
                         png_psd_mapping='not_assessed', whole_character_complete=None))
    return dict(schema='autospine.cohort-intake/v2' if source_checks is not None else 'autospine.cohort-intake/v1',
                authority='none', production_authorized=False,
                characters=rows, total_characters=len(rows),
                exact_active_single_source=sum(r['reason_code'] == 'source_matched_workflow_not_assessed' for r in rows),
                runtime_status='not_assessed', independent_holdout_status='requires_exposure_audit')
