"""Apply explicit PSD version selection to a copy of the frozen intake manifest."""
from copy import deepcopy
from hashlib import sha256
import re


def select(manifest, manifest_bytes, versions):
    if (versions.get('schema') != 'autospine.cohort-source-versions/v1'
            or versions.get('baseline_manifest_sha256') != sha256(manifest_bytes).hexdigest()
            or versions.get('authority') != 'human_source_selection'
            or versions.get('production_authorized') is not False):
        raise ValueError('cohort_source_versions_identity')
    result = deepcopy(manifest)
    seen = set()
    for entry in versions['entries']:
        identity = entry['character_id']
        matches = [c for c in result['characters'] if c['id'] == identity]
        if len(matches) != 1 or identity in seen:
            raise ValueError('cohort_source_versions_scope')
        seen.add(identity); character = matches[0]
        if (character['dataset_split'] != entry['dataset_split']
                or character['psd_candidates'] != entry['previous_psd_candidates']):
            raise ValueError('cohort_source_versions_prior_changed')
        source = entry['source']
        if (not re.fullmatch('[a-f0-9]{64}', source.get('sha256', ''))
                or type(source.get('byte_size')) is not int or source['byte_size'] < 26
                or not isinstance(source.get('canvas'), list) or len(source['canvas']) != 2
                or any(type(n) is not int or n <= 0 for n in source['canvas'])
                or source.get('path') not in [c['source']['path'] for c in character['psd_candidates']]):
            raise ValueError('cohort_source_versions_invalid')
        candidate = deepcopy(next(c for c in character['psd_candidates'] if c['source']['path'] == source['path']))
        candidate['source'] = deepcopy(source)
        candidate['mapping'].update(status='candidate', requires_visual_review=True,
                                    basis='explicit_psd_version_selection_only')
        character['psd_candidates'] = [candidate]
        character.update(annotation_status='pending', reviewed_joints={}, supported_motion_set=[])
    return result
