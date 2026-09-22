"""Compare sequence refinements on identical times; preserve failed evidence."""
import argparse
from copy import deepcopy
import json
from pathlib import Path
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.targets.spine43.continuous_pose import area
from m4_raw_preservation_sequence import inspect


def compare(first,second):
    a,b=[json.loads((p/'probe.json').read_bytes()) for p in (first,second)]
    for key in ('parent_sha256','slot'):
        if a[key]!=b[key]:raise ValueError('comparison_parent_mismatch')
    files=AnimatedStore(Path('workspace')).read(a['parent_sha256'])
    doc=json.loads(files['skeleton.json']);name='external-motion';slot=a['slot']
    raw=deepcopy(doc);raw['animations'][name].pop('attachments',None);raw['animations'][name].pop('deform',None)
    mesh=doc['skins'][0]['attachments'][slot][slot]
    triangles=[mesh['triangles'][i:i+3] for i in range(0,len(mesh['triangles']),3)]
    setup=json.loads(files['rig-setup-reference.json'])['vertices'][slot]
    areas=[area(setup,t) for t in triangles]
    times=sorted({k['time'] for tracks in doc['animations'][name]['bones'].values() for track in tracks.values() for k in track})
    rows=[]
    for root in (first,second):
        receipt=json.loads((root/'candidate/report.json').read_bytes())
        artifact=receipt['candidate_bundle_sha256']
        result=json.loads(AnimatedStore(root/'candidate/isolated-store').read(artifact)['skeleton.json'])
        unchanged=deepcopy(result)
        unchanged['animations'][name]['attachments']['default'][slot]=deepcopy(doc['animations'][name]['attachments']['default'][slot])
        if unchanged!=doc:raise ValueError('unrelated_channels_changed')
        samples,failures=inspect(raw,result,name,slot,times,triangles,areas)
        rows.append(dict(candidate=artifact,samples=len(samples),unrelated_channels_unchanged=True,
            regression_count=len(failures),maximum_deficit=max([r['before']-r['after'] for r in failures]or[0]),
            regressions=failures))
    return dict(parent=a['parent_sha256'],slot=slot,comparison=rows,authority='none',selected=False,
        scope='same_source_keys_and_midpoints_cpu_comparison')


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('first',type=Path)
    parser.add_argument('second',type=Path);parser.add_argument('output',type=Path)
    args=parser.parse_args();report=compare(args.first,args.second)
    args.output.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps([{k:v for k,v in r.items() if k!='regressions'}for r in report['comparison']]))
