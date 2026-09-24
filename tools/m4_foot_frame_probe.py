"""Replay stale-parent foot frame repair on an isolated pose candidate."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.targets.character43.foot_frame_preservation import preserve
from autospine_workbench.targets.character43.pose_geometry_patch import _times
from autospine_workbench.targets.character43.active_mesh_pose import sample_active
from autospine_workbench.targets.character43.deformation_qa import inspect


def run(scene_path,store,digest,output):
    scene=json.loads(scene_path.read_bytes());doc=scene['skeleton']
    reference=json.loads(AnimatedStore(store).read(digest)['skeleton.json'])
    times=sorted({0.,*_times(doc['animations']['external-motion'].get('bones',{}))})
    candidate,evidence=preserve(doc,reference,'external-motion',times)
    scene['skeleton']=candidate;scene['artifact']=None
    keys=sorted(set(times)|set(_times(candidate['animations']['external-motion'].get('bones',{}))))
    checked=sorted(set(keys)|{(a+b)/2 for a,b in zip(keys,keys[1:])})
    if len(checked)>8193:raise ValueError('foot_frame_probe_sample_limit')
    frames=[]
    for time in checked:
        state=sample_active(candidate,'external-motion',time)
        frames.append(dict(time=time,attachments=state['attachments'],vertices=state['vertices']))
    raw=json.dumps(candidate).encode()
    numeric=dict(skeleton_sha256=sha256(raw).hexdigest(),animations={'external-motion':frames})
    geometry=inspect({'skeleton.json':raw,'numeric-reference.json':json.dumps(numeric).encode()})
    output.mkdir(parents=True,exist_ok=False)
    for name,data in [('candidate.json',scene),('report.json',dict(evidence,reference_artifact=digest)),
                      ('geometry.json',geometry),('active-reference.json',dict(animation='external-motion',frames=frames))]:
        (output/name).write_text(json.dumps(data),encoding='utf8')
    print(json.dumps(dict(evidence=evidence,frames=len(frames),geometry_passed=geometry['passed'],
        failures=[dict(slot=r['slot'],attachment=r['attachment'],frames=r['failing_frame_count']) for r in geometry['records'] if not r['passed']])))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('scene',type=Path);parser.add_argument('store',type=Path)
    parser.add_argument('digest');parser.add_argument('output',type=Path)
    args=parser.parse_args();run(args.scene,args.store,args.digest,args.output)
