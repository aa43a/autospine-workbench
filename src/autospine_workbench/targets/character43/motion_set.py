"""Group independently verified candidates bound to one unchanged character source."""
from hashlib import sha256
import json
from ...automation.storage_io import canonical_bytes
from .motion_composition import compose
from .deformation_qa import inspect
from .numeric_reference import read as read_reference, write as write_reference


def combine(base, base_digest, candidates):
    if not candidates or len(candidates) > 16:
        raise ValueError('character_motion_set_inventory')
    identifiers = [digest for digest, _ in candidates]
    if len(set(identifiers)) != len(identifiers):
        raise ValueError('character_motion_set_duplicate_source')
    document = json.loads(base['skeleton.json']); document['animations'] = {}
    references = {}; rows = []
    result = {n: data for n, data in base.items() if n.endswith('.png') or n == 'skeleton.atlas'}
    for digest, files in sorted(candidates):
        # Each source is checked against the real base, never a synthetic rebased identity.
        compose(base, files, base_digest, digest)
        incoming = json.loads(files['skeleton.json'])['animations']
        if set(incoming) & set(document['animations']):
            raise ValueError('character_motion_set_duplicate_clip')
        document['animations'].update(incoming)
        references.update(read_reference(files)['animations'])
        # Keep diagnostics and their original identities, including failed repair attempts.
        for name, raw in files.items():
            if name.endswith('.json') and not name.startswith('numeric-reference/') and name not in ('skeleton.json', 'numeric-reference.json', 'inventory.json'):
                result['motion-set-sources/'+digest+'/'+name] = raw
        rows.append(dict(motion_candidate_sha256=digest, animations=sorted(incoming),
                         visual_status='needs_review'))
    result['skeleton.json'] = canonical_bytes(document)
    result = write_reference(result, dict(
        skeleton_sha256=sha256(result['skeleton.json']).hexdigest(), animations=references))
    qa = inspect(result)
    result['deformation.json'] = canonical_bytes(qa)
    result['motion-review.json'] = canonical_bytes(dict(profile='same-source-motion-set-v1',
        authority='none', geometry_passed=qa['passed'], runtime_status='not_evaluated',
        visual_status='needs_review', sources=rows))
    result['character-manifest.json'] = canonical_bytes(dict(schema='autospine.character-motion-preview/v1',
        profile='same-source-motion-set-v1', source_character_sha256=base_digest,
        animations=sorted(document['animations']), authority='none', production_authorized=False,
        status='preview_only', files={n: sha256(raw).hexdigest() for n, raw in result.items()}))
    return result
