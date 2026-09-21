"""Restore verified source metadata needed to reproduce regional worker scope."""
from hashlib import sha256
import json


def prepare(candidate, character, character_digest):
    manifest=json.loads(candidate['character-manifest.json'])
    if manifest.get('source_character_sha256')!=character_digest:
        raise ValueError('regional_replay_character_identity')
    current=json.loads(candidate['skeleton.json']);source=json.loads(character['skeleton.json'])
    if ({k:v for k,v in current.items() if k!='animations'} !=
            {k:v for k,v in source.items() if k!='animations'}):
        raise ValueError('regional_replay_source_rig_changed')
    for name,raw in character.items():
        if (name.endswith('.png') or name=='skeleton.atlas') and candidate.get(name)!=raw:
            raise ValueError('regional_replay_source_texture_changed:'+name)
    inputs=dict(candidate);restored={}
    for name in ('skirt-trial.json',):
        if name not in character:
            if name in candidate:raise ValueError('regional_replay_metadata_without_source')
            continue
        if name in candidate and candidate[name]!=character[name]:
            raise ValueError('regional_replay_metadata_changed')
        inputs[name]=character[name];restored[name]=sha256(character[name]).hexdigest()
    return inputs,dict(profile='verified-character-regional-replay-inputs-v1',
        source_character_sha256=character_digest,
        source_skeleton_sha256=sha256(character['skeleton.json']).hexdigest(),
        restored_metadata=restored,scope='original_character_metadata_with_existing_motion_candidate')
