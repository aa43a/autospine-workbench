"""Independent full-character geometry check for isolated corrective experiments."""
import argparse
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.automation.motion_target_pose import final_times
from autospine_workbench.targets.character43.affine_pose import sample
from autospine_workbench.targets.character43.numeric_reference import read,write,carry_setup
from autospine_workbench.targets.character43.deformation_qa import inspect


def prepare(source,experiment):
    receipt=json.loads((source/'report.json').read_bytes())
    report=json.loads((experiment/'report.json').read_bytes())
    if report['source_candidate']!=receipt['candidate_bundle_sha256']:
        raise ValueError('corrective_geometry_source_mismatch')
    original=AnimatedStore(source/'isolated-store').read(report['source_candidate'])
    raw=(experiment/'skeleton.json').read_bytes()
    if sha256(raw).hexdigest()!=report['skeleton_sha256']:
        raise ValueError('corrective_geometry_skeleton_mismatch')
    doc=json.loads(raw);before=json.loads(original['skeleton.json']);name='external-motion'
    if doc['animations'][name]['bones']!=before['animations'][name]['bones']:
        raise ValueError('corrective_geometry_bone_tracks_changed')
    selected={r['slot'] for r in report['rows']}
    unchanged=[]
    for document in (before,doc):
        value=deepcopy(document)
        tracks=value['animations'][name].get('attachments',{}).get('default',{})
        for slot in selected:tracks.pop(slot,None)
        unchanged.append(value)
    if unchanged[0]!=unchanged[1]:raise ValueError('corrective_geometry_unselected_tracks_changed')
    files=dict(original,**{'skeleton.json':raw});setup=carry_setup(original,files)
    times=final_times(doc,name,[r['time'] for r in read(original)['animations'][name]])
    frames=[dict(time=t,vertices=sample(doc,name,t)[0]) for t in times]
    files=write(files,dict(skeleton_sha256=sha256(raw).hexdigest(),animations={name:frames}))
    qa=inspect(files,setup_vertices=setup)
    value=dict(source_candidate=report['source_candidate'],skeleton_sha256=report['skeleton_sha256'],
        geometry=qa,selected_slots=sorted(selected),authority='none',selected=False,
        scope='full_character_sampled_geometry_not_runtime_or_visual_acceptance')
    return files,value


def run(source,experiment,output):
    files,value=prepare(source,experiment)
    qa=value['geometry'];selected=set(value['selected_slots'])
    with output.open('xb') as handle:handle.write(canonical_bytes(value))
    print(json.dumps(dict(passed=qa['passed'],failed=[r['slot'] for r in qa['records'] if not r['passed']],
        selected=[r for r in qa['records'] if r['slot'] in selected])),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('source','experiment','output'):p.add_argument(n,type=Path)
    a=p.parse_args();run(a.source,a.experiment,a.output)
