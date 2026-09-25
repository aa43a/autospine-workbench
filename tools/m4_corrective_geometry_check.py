"""Independent full-character geometry check for isolated corrective experiments."""
import argparse
from copy import deepcopy
from hashlib import sha256
import json
import math
from pathlib import Path
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.targets.character43.affine_pose import sample
from autospine_workbench.targets.character43.numeric_reference import read,write,carry_setup
from autospine_workbench.targets.character43.deformation_qa import inspect


def required_times(document,name,reference_times,report):
    # Build the coverage requirement before partitioning. Single captures still
    # enforce 4097 below; this does not enlarge the production final_times budget.
    animation=document['animations'][name]
    keys={k['time'] for tracks in animation['bones'].values() for values in tracks.values() for k in values}
    keys.update(k['time'] for skin in animation.get('attachments',{}).values() for slots in skin.values()
                for tracks in slots.values() for values in tracks.values() for k in values)
    keys=sorted(keys|set(reference_times))
    times=sorted(set(keys)|{(a+b)/2 for a,b in zip(keys,keys[1:])})
    declared=report.get('validation_times',[])
    if declared:
        if (report.get('validation',{}).get('frames')!=len(declared) or
                any(not math.isfinite(t) or t<times[0] or t>times[-1] for t in declared) or
                any(b<=a for a,b in zip(declared,declared[1:]))):
            raise ValueError('corrective_geometry_validation_grid_invalid')
        times=sorted(set(times)|set(declared))
    if len(times)>16385:raise ValueError('corrective_geometry_total_samples_limit')
    return times


def checked_times(document,name,reference_times,report):
    times=required_times(document,name,reference_times,report)
    if len(times)>4097:raise ValueError('corrective_geometry_required_samples_exceed_capture_budget')
    return times


def prepare(source,experiment,*,sample_times=None):
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
    reference_times=[r['time'] for r in read(original)['animations'][name]]
    if sample_times is None:times=checked_times(doc,name,reference_times,report)
    else:
        required=required_times(doc,name,reference_times,report)
        if (not sample_times or len(sample_times)>4097 or sample_times!=sorted(set(sample_times))
                or not set(sample_times)<=set(required)):
            raise ValueError('corrective_geometry_batch_times_invalid')
        times=sample_times
    frames=[dict(time=t,vertices=sample(doc,name,t)[0]) for t in times]
    files=write(files,dict(skeleton_sha256=sha256(raw).hexdigest(),animations={name:frames}))
    qa=inspect(files,setup_vertices=setup)
    value=dict(source_candidate=report['source_candidate'],skeleton_sha256=report['skeleton_sha256'],
        geometry=qa,selected_slots=sorted(selected),authority='none',selected=False,
        scope='full_character_sampled_geometry_not_runtime_or_visual_acceptance',
        sample_times=times,partial_time_batch=sample_times is not None)
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
