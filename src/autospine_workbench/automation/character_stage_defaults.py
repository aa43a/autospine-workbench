"""Reversible stage defaults for supported, fully covered weighted regions."""
import json
from ..resolved_project import canonical_sha256
from ..targets.character43.binding_inventory import inspect
from .storage_io import publish_document, read_document

PROFILE = 'supported-weighted-stage-defaults-v1'


def _supported(layer, rows):
    name = layer.get('name', '').strip().lower()
    for row in rows:
        bones = {item['bone'] for item in row['influences']}
        region = row['region_id']
        if name in ('handwear-l', 'handwear-r'):
            side = name[-1]
            allowed = {f'{part}_{side}' for part in ('upperarm', 'forearm', 'hand')}
            allowed.add('cloth-' + region)
        elif name in ('legwear', 'legwear-l', 'legwear-r', 'footwear', 'footwear-l', 'footwear-r'):
            side = name[-1] if name.endswith(('-l', '-r')) else region[-1]
            if side not in ('l', 'r'): return False
            parts = ('foot',) if name.startswith('footwear') else ('thigh', 'calf', 'foot')
            allowed = {f'{part}_{side}' for part in parts}
        elif name in ('bottomwear', 'bottomwear-front'):
            allowed = {'chest'} | {f'{layer["layer_id"]}-skirt_{i}_{part}'
                                  for i in range(3) for part in ('upper', 'lower')}
        elif name in ('headwear', 'headwear-front', 'headwear-back'):
            allowed = {'head'}
        else:
            return False
        if not bones or not bones <= allowed: return False
    return bool(rows)


def evaluate(job, files, human_overrides=()):
    from .character_weighted_review import eligible
    inventory = inspect(json.loads(files['skeleton.json']), job['layers']) if job['layers'] else {'regions': []}
    runtime = job.get('runtime', {})
    ready = (job.get('status') == 'needs_review' and runtime.get('geometry_status') == 'passed'
             and runtime.get('geometry_failed_records') == 0 and runtime.get('frames', 0) > 0)
    accepted = []
    for layer in job['layers']:
        rows = [row for row in inventory['regions'] if row['layer_id'] == layer['layer_id']]
        if ready and eligible(layer) and layer['layer_id'] not in human_overrides and _supported(layer, rows):
            accepted.append(layer['layer_id'])
    return dict(schema='autospine.character-stage-defaults/v1', policy_id=PROFILE,
                decision_source='policy_auto', authority='none', production_authorized=False,
                project_id=job['project_id'], job_id=job['job_id'], artifact_sha256=job['artifact_sha256'],
                runtime_sha256=canonical_sha256(runtime), layers_sha256=canonical_sha256(job['layers']),
                inventory_sha256=canonical_sha256(inventory), accepted_layer_ids=sorted(accepted),
                human_override_layer_ids=sorted(set(human_overrides)),
                calibration_status='unmeasured', visual_review_required=True, reversible=True)


def previous_overrides(root, project):
    """Conservatively retain past revocations across rebuilds until explicit review."""
    from .character_weighted_review import history
    from types import SimpleNamespace
    folders=list(root.parent.glob('job-*'))
    if len(folders)>4096: raise ValueError('character_stage_defaults_history_limit')
    denied=set()
    for folder in folders:
        if not (folder/'weighted-review').exists(): continue
        entries=history(SimpleNamespace(_path=lambda _, f=folder:f), folder.name)
        if not entries or entries[-1][1].get('project_id')!=project: continue
        latest=entries[-1][1]
        denied.update(latest.get('revoked_replayed_layer_ids',[]))
        earlier={key for _,doc in entries[:-1] for key in doc['accepted_layer_ids']}
        denied.update(earlier-set(latest['accepted_layer_ids']))
    return denied


def publish(root, job, files):
    document = evaluate(job, files, previous_overrides(root,job['project_id']))
    if not publish_document(root/'stage-defaults.json', document, staging=root/'staging'):
        if read_document(root/'stage-defaults.json') != document:
            raise ValueError('character_stage_defaults_conflict')


def read(root, job, files):
    path = root/'stage-defaults.json'
    if not path.exists(): return None
    document = read_document(path)
    overrides=document.get('human_override_layer_ids')
    if type(overrides) is not list or any(type(key) is not str for key in overrides):
        raise ValueError('character_stage_defaults_source_changed')
    if document != evaluate(job, files, overrides): raise ValueError('character_stage_defaults_source_changed')
    return document


def accepted(job, value):
    doc = value.get('default_review')
    if not doc or value.get('default_review_sha256') != canonical_sha256(doc): return set()
    expected = dict(schema='autospine.character-stage-defaults/v1', policy_id=PROFILE,
                    calibration_status='unmeasured', decision_source='policy_auto', authority='none',
                    production_authorized=False, project_id=job['project_id'], job_id=job['job_id'],
                    artifact_sha256=job['artifact_sha256'], runtime_sha256=canonical_sha256(job['runtime']),
                    layers_sha256=canonical_sha256(job['layers']), visual_review_required=True, reversible=True)
    if any(doc.get(key) != val for key, val in expected.items()): return set()
    from .character_weighted_review import eligible
    allowed = {layer['layer_id'] for layer in job['layers'] if eligible(layer)}
    ids = doc.get('accepted_layer_ids')
    return set(ids) if type(ids) is list and all(type(k) is str for k in ids) and set(ids) <= allowed else set()
