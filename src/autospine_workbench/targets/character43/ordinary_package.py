"""Reference and source-layer ledger for an ordinary whole-character preview."""
from copy import deepcopy
from hashlib import sha256
import json

from ...automation.storage_io import canonical_bytes
from ..spine43.continuous_pose import world


def build_package(base, coverage, addresses, *, checkpoint=lambda: None):
    document=json.loads(base['skeleton.json']);motion=json.loads(base['motion.json'])
    if document['skeleton']['spine']!='4.3.26' or motion['clip']!='limb-flex-15' or motion['duration']!=2 \
            or set(document['animations'])!={'limb-flex-15'}:
        raise ValueError('character_ordinary_motion_unsupported')
    layers=deepcopy(coverage['layers'])
    if {r['region_id'] for l in layers for r in l['regions']}!={s['name'] for s in document['slots']}:
        raise ValueError('character_coverage_inventory_mismatch')
    frames=[]
    for tick in range(129):
        if tick%16==0:checkpoint()
        frames.append(dict(time=tick/64,vertices=world(document,tick/64)))
    files=dict(base)
    for name in ('playback.json','qa.json','preview-manifest.json'):files.pop(name,None)
    files['numeric-reference.json']=canonical_bytes(dict(skeleton_sha256=sha256(files['skeleton.json']).hexdigest(),
                                                        animations={'limb-flex-15':frames}))
    manifest=dict(schema='autospine.character-composition/v1',profile='ordinary-limb-flex-preserved-v1',
        target='4.3.26',authority='none',production_authorized=False,full_character_animation=False,status='needs_review',
        source_addresses=deepcopy(addresses),layers=layers,animations=['limb-flex-15'],records=[],
        qa=dict(runtime_status='not_run',full_character_contact_status='not_evaluated'),
        files={name:sha256(raw).hexdigest() for name,raw in sorted(files.items())})
    files['character-manifest.json']=canonical_bytes(manifest)
    return files
