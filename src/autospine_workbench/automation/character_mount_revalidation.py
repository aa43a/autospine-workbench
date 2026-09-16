"""Reuse reviewed component mounts only when all rendered and numeric bytes match."""
from hashlib import sha256
import json
from .storage_io import canonical_bytes
from .pipeline_run import PipelineRunError


def equivalent(previous,current):
    required={'character-manifest.json','skeleton.json','numeric-reference.json'}
    if not required<=previous.keys() or not required<=current.keys():return False
    metadata={'character-manifest.json','skirt-trial.json','motion-replay.json'}
    if {k:v for k,v in previous.items() if k not in metadata}!={k:v for k,v in current.items() if k not in metadata}:
        return False
    for name in ('character-manifest.json','skirt-trial.json'):
        if (name in previous)!=(name in current):return False
        if name not in previous:continue
        pair=[json.loads(f[name]) for f in (previous,current)]
        for value in pair:
            value.pop('source_character_sha256',None)
            if name=='character-manifest.json':
                value.pop('files',None);value.pop('motion_replay_sha256',None)
                value.get('source_addresses',{}).pop('base_bundle_sha256',None)
        if pair[0]!=pair[1]:return False
    return True


def rebuild(store,current_digest,review):
    from ..targets.character43.component_mount_candidate import generate
    decision=review['decision'];old_digest=decision['source_bundle_sha256']
    original,current=store.read(old_digest),store.read(current_digest)
    if not equivalent(original,current):
        raise PipelineRunError('character_mount_source_changed')
    files,report=generate(original,decision['source_region_id'],review['allowed_parents'],decision)
    receipt=dict(schema='autospine.character-mount-revalidation/v1',authority='none',
        new_human_confirmation=False,original_decision=decision,
        original_source_sha256=old_digest,current_source_sha256=current_digest,
        rule='identical-render-and-numeric-bytes-with-build-receipt-changes-v1')
    files['component-mount-revalidation.json']=canonical_bytes(receipt)
    manifest=json.loads(files['character-manifest.json'])
    manifest['source_addresses']=json.loads(current['character-manifest.json'])['source_addresses']
    manifest['files']={n:sha256(raw).hexdigest() for n,raw in files.items() if n!='character-manifest.json'}
    files['character-manifest.json']=canonical_bytes(manifest)
    return files,report
