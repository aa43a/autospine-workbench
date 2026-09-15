"""Whole-character dress recipe with source-preserving component selection."""
from hashlib import sha256
import json
from .storage_io import canonical_bytes
from .pipeline_run import PipelineRunError
from ..targets.character43.affine_pose import sample
from ..targets.character43.skirt_contact import source_image
from ..targets.character43.dress_waist import propose
from ..targets.character43.component_mount_candidate import generate as partition
from ..targets.character43.skirt_candidate import generate

PROFILE = 'isolated-dress-chest-skirt-v1'


def seal(files, blocked=()):
    manifest = json.loads(files['character-manifest.json'])
    for failure in blocked:
        for layer in manifest['layers']:
            if layer['layer_id'] == failure['layer_id'] or any(r['region_id'] == failure['layer_id'] for r in layer['regions']):
                layer['reason_codes'] = sorted(set(layer.get('reason_codes', []) + [failure['reason_code']]))
    manifest['files'] = {n: sha256(b).hexdigest() for n, b in files.items() if n != 'character-manifest.json'}
    return dict(files, **{'character-manifest.json': canonical_bytes(manifest)})


def prepare(files, *, publish=None):
    """Select only a unique supported component per unreviewed garment layer."""
    files = dict(files)
    manifest = json.loads(files['character-manifest.json'])
    slots = sorted(r['region_id'] for l in manifest['layers']
                   if l['name'] in ('topwear', 'topwear-front') and l['state'] == 'static_reference'
                   for r in l['regions'] if r.get('state', l['state']) == 'static_reference')
    if not slots:
        raise PipelineRunError('character_dress_layers_missing')
    selected = []; blocked = []; partitions = []
    for slot in slots:
        owner = next(l['layer_id'] for l in manifest['layers'] if any(r['region_id'] == slot for r in l['regions']))
        doc = json.loads(files['skeleton.json'])
        attachment = doc['skins'][0]['attachments'][slot][slot]
        parent = doc['bones'][attachment['vertices'][1]]['name']
        try:
            trial, evidence = partition(files, slot, [parent], partition_only=True)
            split_doc = json.loads(trial['skeleton.json'])
            positions, pose = sample(dict(split_doc, animations={'setup': {}}), 'setup', 0)
            eligible = []; failures = []
            for part in evidence['parts']:
                if part['component_id'] == 'unbound-residual':
                    continue
                image, origin = source_image(trial, split_doc, positions, part['region_id'])
                try:
                    propose(image.getchannel('A'), origin, pose)
                    eligible.append(part['region_id'])
                except ValueError as exc:
                    if not str(exc).startswith('skirt_'): raise
                    failures.append(dict(region_id=part['region_id'], reason_code=str(exc)))
            if len(eligible) != 1:
                blocked.append(dict(layer_id=owner, source_region_id=slot,
                    reason_code='skirt_dress_component_ambiguous' if eligible else 'skirt_dress_component_not_found',
                    component_failures=failures))
                continue
        except ValueError as exc:
            if not str(exc).startswith('component_mount_'): raise
            blocked.append(dict(layer_id=owner, source_region_id=slot, reason_code=str(exc)))
            continue
        if publish is not None and publish(files) != evidence['source_bundle_sha256']:
            raise PipelineRunError('character_dress_partition_source_mismatch')
        # Keep source evidence, but never obsolete numeric chunks. The new manifest
        # hashes every retained file; the unchanged source remains separately addressed.
        for name, raw in files.items():
            if not name.startswith('numeric-reference/'):
                trial.setdefault(name, raw)
        partitions.append(dict(source_region_id=slot, selected_region_id=eligible[0],
                               evidence=evidence, component_failures=failures))
        files = seal(trial)
        selected.extend(eligible)
    files['dress-partitions.json'] = canonical_bytes(dict(
        schema='autospine.dress-partitions/v1', profile=PROFILE, authority='none',
        selected=False, partitions=partitions, blocked_layers=blocked))
    return seal(files, blocked), selected, blocked


def apply_selected(manager, request, result):
    # Evaluate the existing opt-in residual policy before component topology changes.
    from .character_residual_defaults import apply as residual_defaults
    result = residual_defaults(manager, request, result)
    store = manager.application.store
    source = result['artifact_sha256']
    files, selected, blocked = prepare(store.read(source), publish=store.publish)
    partition_digest = store.publish(files)
    if selected:
        output, report = generate(files, partition_digest, selected,
            waist_driver='candidate-chest-v1', dress_components=True)
        blocked += report.get('blocked_layers', [])
    else:
        output = files
        report = dict(rows=[], geometry_passed=False, setup_error_px=0)
    output = seal(output, blocked)
    applied = dict(result, artifact_sha256=store.publish(output),
        manifest=json.loads(output['character-manifest.json']),
        skirt_trial=dict(profile=PROFILE, layer_ids=[r['layer_id'] for r in report['rows']],
            source_artifact_sha256=source, partition_artifact_sha256=partition_digest,
            geometry_passed=report['geometry_passed'], setup_error_px=report['setup_error_px'],
            blocked_layers=blocked, authority='none', selected=False))
    return applied
