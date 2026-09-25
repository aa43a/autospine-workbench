"""Combine disjoint deform experiments with exactly the same parent identity."""
import argparse
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path

from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import canonical_bytes


def merge(parent, variants):
    result = deepcopy(parent); seen = set(); name = 'external-motion'
    for document, slots in variants:
        slots = set(slots)
        if not slots or seen & slots:
            raise ValueError('corrective_merge_overlapping_slots')
        checks = []
        for value in (parent, document):
            value = deepcopy(value)
            tracks = value['animations'][name].get('attachments',{}).get('default',{})
            for slot in slots:
                tracks.pop(slot,None)
            checks.append(value)
        if checks[0] != checks[1]:
            raise ValueError('corrective_merge_unrelated_mutation')
        source = document['animations'][name]['attachments']['default']
        destination = result['animations'][name].setdefault('attachments',{}).setdefault('default',{})
        for slot in slots:
            destination[slot] = deepcopy(source[slot])
        seen.update(slots)
    return result, sorted(seen)


def run(source, experiments, output):
    receipt = json.loads((source/'report.json').read_bytes()); identity = receipt['candidate_bundle_sha256']
    parent = json.loads(AnimatedStore(source/'isolated-store').read(identity)['skeleton.json'])
    variants = []; hashes = []
    for folder in experiments:
        report = json.loads((folder/'report.json').read_bytes()); raw = (folder/'skeleton.json').read_bytes()
        if report['source_candidate'] != identity or sha256(raw).hexdigest() != report['skeleton_sha256']:
            raise ValueError('corrective_merge_identity_mismatch')
        variants.append((json.loads(raw),[row['slot'] for row in report['rows']]))
        hashes.append(report['skeleton_sha256'])
    doc, slots = merge(parent,variants); raw = canonical_bytes(doc)
    output.mkdir(parents=True,exist_ok=False)
    (output/'skeleton.json').write_bytes(raw)
    (output/'report.json').write_bytes(canonical_bytes(dict(source_candidate=identity,
        skeleton_sha256=sha256(raw).hexdigest(),inputs=hashes,rows=[dict(slot=s) for s in slots],
        authority='none',selected=False,scope='disjoint_deform_merge_requires_new_validation')))


if __name__ == '__main__':
    parser = argparse.ArgumentParser();parser.add_argument('source',type=Path)
    parser.add_argument('output',type=Path);parser.add_argument('experiment',type=Path,nargs='+')
    args=parser.parse_args();run(args.source,args.experiment,args.output)
