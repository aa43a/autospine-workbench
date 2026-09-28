"""Verify continuous-camera depth and ankle observations on a saved real source."""
import argparse
import json
from pathlib import Path
from urllib.request import urlopen
from autospine_workbench.motion_bundle_reader import VerifiedMotionBundleReader
from autospine_workbench.bvh_parser import parse_bvh
from autospine_workbench.targets.character43.motion_depth import _source
from autospine_workbench.targets.character43.source_depth_sampler import SegmentDepthSampler
from autospine_workbench.targets.character43.kimodo_depth_sampler import KimodoDepthSampler
from autospine_workbench.targets.character43.camera_ankle_targets import extract
from autospine_workbench.targets.character43.source_ankle_targets import extract as fixed_ankles, targets


def main():
    p=argparse.ArgumentParser();p.add_argument('--state',type=Path,required=True)
    p.add_argument('--source',required=True);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    job=json.loads(urlopen('http://127.0.0.1:8918/api/motions/'+args.source,timeout=30).read())
    identity=job['result']['motion']
    bundle=VerifiedMotionBundleReader(args.state).load(identity['clip_sha256'],identity['bundle_sha256'])
    mapping=json.loads((bundle.path/'map.json').read_bytes())
    kimodo=(bundle.raw_npz,bundle.kimodo_source) if bundle.source_kind=='kimodo_npz' else None
    bvh=None if kimodo else parse_bvh(bundle.raw_bvh)
    duration=bundle.motion['duration_ticks']/bundle.motion['ticks_per_second']
    args.output.mkdir(parents=True,exist_ok=False);rows=[]
    for name,keys in [('fixed',[dict(time=0,yaw=30)]),('turn',[dict(time=0,yaw=0),dict(time=duration,yaw=360)])]:
        frames,length,_=_source(bvh,mapping,kimodo,camera_keys=keys)
        sampler=(KimodoDepthSampler(*kimodo,mapping,camera_keys=keys,interpolation='linear_observed_positions')
                 if kimodo else SegmentDepthSampler(bvh,mapping,camera_keys=keys))
        torso=next(r['joint_name'] for r in mapping['bones'] if r['role']=='humanoid.spine.upper')
        depth_error=0
        for tick,values in frames:
            actual_depths=sampler.joint_depths(tick)
            depth_error=max(depth_error,max(abs(actual_depths[n]-(z-values[torso])/length) for n,z in values.items()))
        assert depth_error<1e-10
        ankles=extract(bundle,keys);fixed_error=None
        if name=='fixed':
            expected=targets(fixed_ankles(bundle,30),[[-20,-100],[20,-100]],100)
            actual=targets(ankles,[[-20,-100],[20,-100]],100)
            fixed_error=max(abs(a-b) for row,other in zip(expected,actual)
                for point,second in zip(row['targets'],other['targets']) for a,b in zip(point,second))
            assert fixed_error<1e-9
        (args.output/(name+'-ankles.json')).write_text(json.dumps(ankles,allow_nan=False),encoding='utf-8')
        rows.append(dict(name=name,frames=len(frames),joint_depth_error=depth_error,
            fixed_target_error_px=fixed_error,ankle_observation=ankles['observation_sha256'],
            maximum_camera_displacement_source_units=max(abs(v) for f in ankles['camera_displacement'] for pt in f for v in pt)))
    report=dict(source_job=args.source,identity=identity,source_kind=bundle.source_kind,rows=rows,
                scope='camera_observation_consistency_not_target_contact_or_occlusion_acceptance')
    (args.output/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report))


if __name__=='__main__':main()
