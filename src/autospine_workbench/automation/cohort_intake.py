"""Read-only frozen-cohort intake; names are hints, never source authority."""
from pathlib import PurePosixPath


def assess(manifest, catalog):
    if (manifest.get('schema') != 'autospine.benchmark-manifest/v1'
            or manifest.get('split_status') != 'frozen'
            or catalog.get('schema') != 'autospine.asset-library/v1'):
        raise ValueError('cohort_intake_source_invalid')
    characters = [c for c in manifest['characters']
                  if c['dataset_split'] in ('development', 'visible', 'holdout')]
    if len(characters) != 10 or len({c['id'] for c in characters}) != 10:
        raise ValueError('cohort_intake_requires_frozen_ten')
    projects = catalog['projects']
    if len({p['id'] for p in projects}) != len(projects):
        raise ValueError('cohort_intake_duplicate_project')
    rows = []
    for character in characters:
        candidates = character['psd_candidates']
        hashes = {c['source']['sha256'] for c in candidates}
        names = {PurePosixPath(c['source']['path']).stem for c in candidates}
        exact = [p for p in projects if p.get('source', {}).get('source_sha256') in hashes]
        hints = [p for p in projects if p not in exact
                 and p.get('source', {}).get('kind') == 'audit'
                 and p['id'] in names]
        active = [p for p in exact if p['lifecycle'] == 'active']
        if len(hashes) > 1:
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
    return dict(schema='autospine.cohort-intake/v1', authority='none', production_authorized=False,
                characters=rows, total_characters=len(rows),
                exact_active_single_source=sum(r['reason_code'] == 'source_matched_workflow_not_assessed' for r in rows),
                runtime_status='not_assessed', independent_holdout_status='requires_exposure_audit')
