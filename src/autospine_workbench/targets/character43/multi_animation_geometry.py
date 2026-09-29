"""Recompute merged geometry with each source's verified M5 compression limits."""
from copy import deepcopy
from hashlib import sha256
import json

from .animation_compatibility import signature, compare
from .joint_animation_qa import geometry_report
from .numeric_reference import read


def inspect(raw, files, store):
    multi = json.loads(files['multi-animation.json'])
    document = json.loads(files['skeleton.json'])
    if multi['skeleton_sha256'] != sha256(files['skeleton.json']).hexdigest():
        raise ValueError('multi_animation_geometry_source')
    reference = read(files)
    baseline = signature(files)
    seen, records = set(), []
    for entry in multi['sources']:
        source = store.read(entry['artifact_sha256'])
        source_doc = json.loads(source['skeleton.json'])
        source_ref = read(source)
        if (compare(baseline, signature(source)) or
                sha256(source['skeleton.json']).hexdigest() != entry['skeleton_sha256']):
            raise ValueError('multi_animation_geometry_bind_changed')
        mapping = entry['animation_mapping']
        for original, name in mapping.items():
            if name in seen or document['animations'][name] != source_doc['animations'][original]:
                raise ValueError('multi_animation_geometry_track_changed')
            if reference['animations'][name] != source_ref['animations'][original]:
                raise ValueError('multi_animation_geometry_reference_changed')
            seen.add(name)
        reverse = {value: key for key, value in mapping.items()}
        part = deepcopy(raw)
        part['records'] = [deepcopy(row) for row in raw['records'] if row['animation'] in reverse]
        for row in part['records']:
            row['animation'] = reverse[row['animation']]
        if 'joint-animation.json' in source:
            joint = json.loads(source['joint-animation.json'])
            provenance = json.loads(source['joint-provenance.json'])
            parent = store.read(provenance['parent_artifact_sha256'])
            if (joint['skeleton_sha256'] != entry['skeleton_sha256'] or
                    joint['parent_skeleton_sha256'] != sha256(parent['skeleton.json']).hexdigest()):
                raise ValueError('multi_animation_geometry_parent_changed')
            part = geometry_report(part, joint['inventory']['face'], joint['config']['face']['enabled'],
                                   face_report=joint['face'], source_geometry=json.loads(parent['deformation.json']))
        for row in part['records']:
            row['animation'] = mapping[row['animation']]
            records.append(row)
    if seen != set(document['animations']) or len(records) != len(raw['records']):
        raise ValueError('multi_animation_geometry_inventory')
    result = deepcopy(raw)
    result.update(profile='multi-animation-source-bounded-geometry-v1', records=records,
                  passed=all(row['passed'] for row in records),
                  scope='fresh_merged_geometry_with_verified_per_source_M5_compression_limits')
    return result
