"""Trace source hand-axis visibility against inherited candidate bone compression."""
import argparse
from copy import deepcopy
import json
import math
from pathlib import Path
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.motion_bundle_reader import VerifiedMotionBundleReader
from autospine_workbench.motion_validation import motion_ir_sha256
from autospine_workbench.targets.character43.source_hand_axis import extract
from autospine_workbench.targets.character43.affine_pose import matrices
from autospine_workbench.targets.character43.oblique_source import extract as body


def run(files,bundle):
    review=json.loads(files['motion-review.json'])
    if motion_ir_sha256(bundle.motion)!=review['motion_sha256']:raise ValueError('hand_trace_source_mismatch')
    if review.get('view_adapter') or review.get('time_range'):raise ValueError('hand_trace_adapted_view_unsupported')
    doc=json.loads(files['skeleton.json']);name='external-motion'
    observed=extract(bundle);vectors,_,_=body(bundle)
    setup=deepcopy(doc);setup['animations']={name:{}}
    rest=matrices(setup,name,0);rows=[]
    def determinant(m):return m[0]*m[3]-m[1]*m[2]
    def visibility(v):return math.hypot(*v[:2])/math.hypot(*v)
    for index,time in enumerate(observed['times']):
        actual=matrices(doc,name,time)
        for side,suffix in [('left','l'),('right','r')]:
            hand='hand_'+suffix;forearm='forearm_'+suffix
            rows.append(dict(time=time,side=side,
                source_hand_axis_visibility=visibility(observed['vectors']['humanoid.arm.hand.'+side][index]),
                source_forearm_visibility=visibility(vectors['humanoid.arm.lower.'+side][index]),
                target_hand_area_ratio=determinant(actual[hand])/determinant(rest[hand]),
                target_forearm_area_ratio=determinant(actual[forearm])/determinant(rest[forearm])))
    return dict(profile='source-hand-compression-trace-v1',observations=observed,rows=rows,
        authority='none',selected=False,
        scope='original_view_source_samples_axis_visibility_not_palm_surface_or_visual_acceptance')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('artifact');p.add_argument('clip');p.add_argument('bundle');p.add_argument('output',type=Path)
    a=p.parse_args();bundle=VerifiedMotionBundleReader(Path('workspace')).load(a.clip,a.bundle)
    report=run(AnimatedStore(Path('workspace')).read(a.artifact),bundle)
    report.update(artifact_sha256=a.artifact,clip_sha256=a.clip,bundle_sha256=a.bundle)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    with a.output.open('x',encoding='utf-8') as f:json.dump(report,f,indent=2)
    print(json.dumps(report['rows'][-2:]))
