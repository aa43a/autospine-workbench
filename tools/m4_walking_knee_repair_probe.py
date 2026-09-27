"""Bake bounded parent/setup-preserving local repair and independently resample."""
import argparse
from copy import deepcopy
import json
from hashlib import sha256
from pathlib import Path
from autospine_workbench.targets.character43.parent_pose_area_repair import compare
from autospine_workbench.targets.character43.affine_pose import sample, matrices
from autospine_workbench.targets.character43.deform_addition import entries, local_delta
from autospine_workbench.targets.character43.numeric_reference import write as write_reference
from autospine_workbench.targets.character43.deformation_qa import inspect
from autospine_workbench.targets.spine43.continuous_pose import area
from autospine_workbench.resolved_project import canonical_sha256


def run(source, output, slot):
    doc=json.loads(source.read_text(encoding='utf-8'));name=next(iter(doc['animations']))
    if doc['animations'][name].get('attachments'):
        raise ValueError('requires_uncorrected_input')
    rest=deepcopy(doc);rest['animations'][name]={'bones':{}}
    setup=sample(rest,name,0)[0]
    mesh=doc['skins'][0]['attachments'][slot][slot];weights=entries(mesh)
    triangles=[mesh['triangles'][i:i+3] for i in range(0,len(mesh['triangles']),3)]
    areas=[area(setup[slot],t) for t in triangles]
    times=sorted({k.get('time',0) for row in doc['animations'][name]['bones'].values() for keys in row.values() for k in keys})
    times=sorted(set(times)|{(a+b)/2 for a,b in zip(times,times[1:])})
    candidate=deepcopy(doc);keys=[];rows=[]
    for t in times:
        original=sample(doc,name,t)[0][slot]
        corrected=original
        if any(area(original,tri)/a<.5 for tri,a in zip(triangles,areas)):
            result=compare(doc,doc,name,slot,t,protect_setup=True,local_refinement=True)
            corrected=result['points']['parent_setup_floor']
            metrics=result['parent_setup_floor']
            rows.append(dict(time=t,minimum_area_ratio=metrics['minimum_setup_ratio'],
                             maximum_shift=metrics['maximum_shift'],fixed_shift=metrics['fixed_shift'],
                             setup_failures=metrics['setup_failures']))
        keys.append(dict(time=t,vertices=local_delta(doc,weights,matrices(doc,name,t),original,corrected)))
    candidate['animations'][name]['attachments']={'default':{slot:{slot:{'deform':keys}}}}
    samples=sorted(set(times)|{(a+b)/2 for a,b in zip(times,times[1:])})
    frames=[dict(time=t,vertices=sample(candidate,name,t)[0]) for t in samples]
    raw=json.dumps(candidate,sort_keys=True,separators=(',',':')).encode()
    files=write_reference({'skeleton.json':raw},dict(skeleton_sha256=sha256(raw).hexdigest(),animations={name:frames}))
    qa=inspect(files,setup_vertices=setup)
    report=dict(parent_sha256=canonical_sha256(doc),skeleton_sha256=canonical_sha256(candidate),
                selected=False,authority='none',rows=rows,geometry=qa,
                scope='cpu_local_deform_requires_contact_depth_runtime_and_visual_checks')
    output.mkdir()
    for label,data in [('skeleton.json',candidate),('report.json',report)]:
        with (output/label).open('x',encoding='utf-8') as stream:json.dump(data,stream)
    print(json.dumps(dict(repaired_knots=len(rows),samples=len(samples),geometry_passed=qa['passed'],
        maximum_shift=max([r['maximum_shift'] for r in rows] or [0]),
        failures=[r for r in qa['records'] if not r['passed']])))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('source',type=Path);p.add_argument('output',type=Path);p.add_argument('--slot',required=True)
    a=p.parse_args();run(a.source,a.output,a.slot)
