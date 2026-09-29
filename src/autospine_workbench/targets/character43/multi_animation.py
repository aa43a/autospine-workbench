"""Merge only identical bind structures; animation data and references stay exact."""
from copy import deepcopy
from hashlib import sha256
import json
import re

from ...automation.storage_io import canonical_bytes
from ...resolved_project import canonical_sha256
from .animation_compatibility import signature, compare
from .numeric_reference import read, write

PROFILE = 'exact-compatible-multi-animation-v1'
EVIDENCE = ('motion-review.json', 'motion-contact.json', 'joint-animation.json',
            'joint-provenance.json', 'deformation.json', 'generic-deformation.json',
            'parent-motion-review.json', 'character-manifest.json')


def build(sources):
    """sources: [{name, artifact_sha256, files}], supplied by verified local stores."""
    if type(sources) is not list or not 2 <= len(sources) <= 16:
        raise ValueError('multi_animation_source_count')
    names = [s['name'] for s in sources]
    if (any(type(n) is not str or not re.fullmatch('[a-zA-Z0-9_-]{1,48}', n) for n in names)
            or len(set(names)) != len(names)):
        raise ValueError('multi_animation_names_invalid')
    first = sources[0]['files']
    baseline = signature(first)
    document = deepcopy(json.loads(first['skeleton.json']))
    document['animations'] = {}
    document.get('skeleton', {}).pop('hash', None)
    output = {name: raw for name, raw in first.items()
              if name.endswith('.atlas') or name.startswith(('images/', 'textures/', 'editor/images/'))}
    setup = None
    references, records = {}, []
    for source in sources:
        files = source['files']
        inventory = {n: sha256(v).hexdigest() for n, v in files.items()}
        if canonical_sha256(inventory) != source['artifact_sha256']:
            raise ValueError('multi_animation_source_identity')
        differences = compare(baseline, signature(files))
        if differences:
            raise ValueError('multi_animation_incompatible_' + '_'.join(differences))
        rig = json.loads(files['skeleton.json'])
        reference = read(files)
        skeleton_sha = sha256(files['skeleton.json']).hexdigest()
        if reference['skeleton_sha256'] != skeleton_sha or set(reference['animations']) != set(rig['animations']):
            raise ValueError('multi_animation_reference_source')
        current_setup = json.loads(files['rig-setup-reference.json'])
        if current_setup.pop('skeleton_sha256') != skeleton_sha:
            raise ValueError('multi_animation_setup_source')
        if setup is not None and current_setup != setup:
            raise ValueError('multi_animation_setup_mismatch')
        setup = current_setup
        mapping = {}
        for index, (original, animation) in enumerate(sorted(rig['animations'].items())):
            # Export-safe deterministic aliases also prevent two external-motion
            # tracks from overwriting one another. Original names are retained.
            name = f"{source['name']}-{index+1:02d}"
            mapping[original] = name
            document['animations'][name] = deepcopy(animation)
            references[name] = reference['animations'][original]
        evidence = {}
        for key in EVIDENCE:
            if key in files:
                path = f"sources/{source['name']}/{key}"
                output[path] = files[key]
                evidence[key] = dict(file=path, sha256=sha256(files[key]).hexdigest())
        records.append(dict(name=source['name'], artifact_sha256=source['artifact_sha256'],
                            skeleton_sha256=skeleton_sha, animation_mapping=mapping, evidence=evidence))
    if len(document['animations']) > 64:
        raise ValueError('multi_animation_animation_limit')
    output['skeleton.json'] = canonical_bytes(document)
    editor = deepcopy(document)
    editor.setdefault('skeleton', {})['images'] = './images/'
    output['editor/skeleton.json'] = canonical_bytes(editor)
    digest = sha256(output['skeleton.json']).hexdigest()
    output['rig-setup-reference.json'] = canonical_bytes(dict(setup, skeleton_sha256=digest))
    output = write(output, dict(skeleton_sha256=digest, animations=references), compressed=True)
    report = dict(schema='autospine.multi-animation/v1', profile=PROFILE,
        signature_sha256=baseline['signature_sha256'], sources=records, skeleton_sha256=digest,
        animation_count=len(document['animations']), status='requires_runtime_validation',
        authority='none', production_authorized=False, visual_status='not_reviewed',
        inherited_evidence_scope='per_source_candidate_only_not_merged_package_acceptance')
    output['multi-animation.json'] = canonical_bytes(report)
    # Do not inherit a single source motion's manifest or acceptance summary.
    original_manifest = json.loads(first['character-manifest.json'])
    manifest = dict(schema=original_manifest['schema'] if 'schema' in original_manifest else
                    'autospine.character-motion-preview/v1', profile=PROFILE,
                    layers=deepcopy(original_manifest['layers']), animations=sorted(document['animations']),
                    source_artifacts=[r['artifact_sha256'] for r in records],
                    status='requires_runtime_validation', multi_animation_profile=PROFILE,
                    authority='none', selected=False, production_authorized=False)
    manifest['files'] = {n: sha256(v).hexdigest() for n, v in output.items()}
    output['character-manifest.json'] = canonical_bytes(manifest)
    return output, report
