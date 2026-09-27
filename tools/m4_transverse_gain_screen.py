"""Screen one constant distal compensation gain on all known regression poses."""
import argparse
from copy import deepcopy
from hashlib import sha256
import json
import math
from pathlib import Path
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.targets.character43.affine_pose import matrices, sample
from autospine_workbench.targets.character43.deform_addition import entries
from autospine_workbench.targets.character43.limb_transverse_repair import build
from autospine_workbench.targets.character43.parent_setup_preservation import floors
from autospine_workbench.targets.character43.projected_area_reference import reference
from autospine_workbench.targets.character43.transverse_gain_feasibility import screen
from autospine_workbench.targets.spine43.continuous_pose import area


def run(state, artifact, slot, source, output):
    raw=source.read_bytes();report=json.loads(raw)
    if report['parent_artifact_sha256']!=artifact or report['slot']!=slot:
        raise ValueError('gain_screen_source_mismatch')
    times=sorted({r['time'] for r in report['failures'] if not r['fixed'] and r['regressed']})
    document=json.loads(AnimatedStore(state).read(artifact)['skeleton.json']);name='external-motion'
    endpoints=[build(document,name,[slot],correction_frame='transverse',anchor_terminal=True,
                     required_times=times,distal_gain=g)[0] for g in (0.,1.)]
    rest=deepcopy(document);rest['animations']={name:{'bones':{}}}
    setup=sample(rest,name,0)[0][slot];mesh=document['skins'][0]['attachments'][slot][slot]
    triangles=[mesh['triangles'][i:i+3] for i in range(0,len(mesh['triangles']),3)]
    areas=[area(setup,t) for t in triangles];influences=entries(mesh);bones=document['bones']
    used={bones[b]['name'] for row in influences for b,w in row if w>0}
    lengths=[math.hypot(b['x'],b['y']) for b in bones if b['name'] in used and b.get('parent') in used]
    if not lengths or min(lengths)<=0:raise ValueError('gain_screen_chain_missing')
    poses=[]
    for time in times:
        previous=sample(document,name,time)[0][slot]
        refs=reference(areas,triangles,influences,bones,matrices(rest,name,0),matrices(document,name,time))
        limits,_=floors(previous,triangles,refs,areas)
        poses.append(dict(time=time,zero=sample(endpoints[0],name,time)[0][slot],
            one=sample(endpoints[1],name,time)[0][slot],floors=limits,
            context=dict(row={'triangles':triangles},areas=refs,budget=.1*min(lengths),
                         free=[sum(w>0 for _,w in row)>1 for row in influences])))
    result=screen(poses,[i/32 for i in range(33)])
    result.update(parent_artifact_sha256=artifact,regression_source_sha256=sha256(raw).hexdigest(),slot=slot)
    with output.open('xb') as handle:handle.write(canonical_bytes(result))
    print(json.dumps({k:v for k,v in result.items() if k!='trials'}))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('state',type=Path);parser.add_argument('artifact');parser.add_argument('slot')
    parser.add_argument('source',type=Path);parser.add_argument('output',type=Path)
    args=parser.parse_args();run(args.state,args.artifact,args.slot,args.source,args.output)
