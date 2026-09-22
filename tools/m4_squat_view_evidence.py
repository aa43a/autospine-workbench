"""Compare source knee readability at fixed views without selecting a character adaptation."""
import argparse
import json
import math
from pathlib import Path
from autospine_workbench.motion_bundle_reader import VerifiedMotionBundleReader
from autospine_workbench.targets.character43.oblique_source import extract
from autospine_workbench.targets.character43.oblique_motion import project
from autospine_workbench.targets.character43.knee_projection import measure


def compare(vectors, roots, times, yaws=(-45, -30, -15, 0, 15, 30, 45)):
    if not times or len(times) != len(roots) or any(b <= a for a,b in zip(times,times[1:])):
        raise ValueError('view_samples_invalid')
    if any(not math.isfinite(t) for t in times):
        raise ValueError('view_time_invalid')
    # Declared source basis is screen-down; choose deepest source root once for all views.
    bottom = max(range(len(roots)), key=lambda i: roots[i][1])
    poses = sorted(set([0, bottom, len(times)-1]))
    rows = []
    for yaw in yaws:
        if not math.isfinite(yaw) or abs(yaw) > 90:
            raise ValueError('view_yaw_invalid')
        samples = []
        for i,time in enumerate(times):
            for side in ('left','right'):
                upper,lower = [project(vectors[f'humanoid.leg.{part}.{side}'][i],yaw)
                               for part in ('upper','lower')]
                samples.append(dict(time=time,side=side,upper=list(upper),lower=list(lower),
                                    **measure(upper,lower)))
        measured = [r for r in samples if r['status']=='measured']
        rows.append(dict(yaw_degrees=yaw,
                         min_leg_visibility=min((min(r['projection_visibility']) for r in measured), default=None),
                         key_poses=[r for r in samples if r['time'] in {times[i] for i in poses}],
                         samples=samples))
    return dict(profile='source-knee-view-comparison-v1',authority='none',selected=False,
                key_times=[times[i] for i in poses],lowest_root_time=times[bottom],views=rows,
                scope='source_bone_projection_only_not_character_contour_or_contact_acceptance')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('request',type=Path);parser.add_argument('output',type=Path)
    args=parser.parse_args();request=json.loads(args.request.read_bytes())
    if request.get('clip'):
        raise ValueError('clipped_time_not_supported')
    identity=request['motion_identity']
    bundle=VerifiedMotionBundleReader(Path('workspace')).load(identity['clip_sha256'],identity['bundle_sha256'])
    vectors,roots,_=extract(bundle)
    keys=next(t for t in bundle.motion['tracks'] if t['property']=='rotation')['keys']
    times=[k['tick']/bundle.motion['ticks_per_second'] for k in keys]
    report=compare(vectors,roots,times);report['source_identity']=identity
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('x',encoding='utf-8') as stream:
        json.dump(report,stream,ensure_ascii=False,allow_nan=False,indent=2)
    print(json.dumps(dict(key_times=report['key_times'],views=[
        dict(yaw=r['yaw_degrees'],min_visibility=r['min_leg_visibility'],bottom=[
            dict(side=p['side'],alignment=p['screen_plane_alignment'],visibility=p['projection_visibility'])
            for p in r['key_poses'] if p['time']==report['lowest_root_time']]) for r in report['views']])))


if __name__=='__main__':main()
