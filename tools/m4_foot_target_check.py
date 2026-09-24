"""Inspect a completed NPZ foot-fit candidate without recording acceptance."""
import argparse
from bisect import bisect_right
from copy import deepcopy
import json
import math
from pathlib import Path
from urllib.request import urlopen

from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.motion_bundle_reader import VerifiedMotionBundleReader
from autospine_workbench.targets.character43.affine_pose import matrices
from autospine_workbench.targets.character43.numeric_reference import read


def temporal_check(document, observation, name='external-motion'):
    """Independent fifth-interval probes, including all animation breakpoints."""
    times = observation['times']
    breaks = set(times)
    for channels in document['animations'][name].get('bones', {}).values():
        for keys in channels.values():
            breaks.update(k.get('time', 0) for k in keys
                          if times[0] <= k.get('time', 0) <= times[-1])
    ordered = sorted(breaks)
    probes = sorted(breaks | {a+(b-a)*f/5 for a,b in zip(ordered, ordered[1:])
                             for f in (1,2,3,4)})
    setup = deepcopy(document)
    setup['animations'] = {'setup': {}}
    rest = matrices(setup, 'setup', 0)
    maximum = 0.; worst = None
    for time in probes:
        index = min(len(times)-2, max(0, bisect_right(times, time)-1))
        fraction = (time-times[index])/(times[index+1]-times[index])
        actual = matrices(document, name, time)
        for bone, angles in observation['tracks'].items():
            angle = angles[index]*(1-fraction)+angles[index+1]*fraction
            c,s = math.cos(math.radians(angle)), math.sin(math.radians(angle))
            r = rest[bone]
            expected = (c*r[0]-s*r[2],c*r[1]-s*r[3],s*r[0]+c*r[2],s*r[1]+c*r[3])
            error = max(abs(a-b) for a,b in zip(actual[bone][:4],expected))/max(abs(v) for v in r[:4])
            if error > maximum:
                maximum = error; worst = dict(time=time,bone=bone)
    return dict(samples=len(probes), maximum_relative_matrix_error=maximum,
                within_v2_tolerance=maximum <= 1e-3, tolerance=1e-3, worst=worst,
                scope='independent_fifth_interval_samples_not_continuous_or_sole_contact_proof')


def run(job):
    with urlopen('http://127.0.0.1:8918/api/motions/'+job, timeout=60) as response:
        value = json.load(response)
    if value['status'] != 'succeeded': raise ValueError('completed_target_required')
    roots = list(Path('workspace/jobs').glob('motion*/'+job+'/request.json'))
    if len(roots) != 1: raise ValueError('exact_target_request_required')
    request = json.loads(roots[0].read_bytes())
    identity = request['motion_identity']
    bundle = VerifiedMotionBundleReader(Path('workspace')).load(identity['clip_sha256'], identity['bundle_sha256'])
    if bundle.source_kind != 'kimodo_npz' or request.get('clip'):
        raise ValueError('full_npz_target_required')
    result = value['result']; artifact = result['artifact_sha256']
    files = AnimatedStore(Path('workspace')).read(artifact)
    motion = json.loads(files['motion-ir.json'])
    if motion['markers'] != bundle.motion['markers']: raise ValueError('source_contacts_changed')
    document = json.loads(files['skeleton.json'])
    evidence = json.loads(files['motion-review.json'])['post_contact_repair']
    observation = evidence['observations']
    rest = deepcopy(document); rest['animations'] = {'setup':{}}
    setup = matrices(rest, 'setup', 0)
    unfit = deepcopy(document)
    for bone in ('foot_l','foot_r'):
        for channel in ('rotate','scale','shear'):
            unfit['animations']['external-motion']['bones'][bone].pop(channel, None)
    key_errors = []
    for index, time in enumerate(observation['times']):
        actual = matrices(document, 'external-motion', time)
        for bone, angles in observation['tracks'].items():
            c,s = math.cos(math.radians(angles[index])), math.sin(math.radians(angles[index]))
            r = setup[bone]
            expected = (c*r[0]-s*r[2],c*r[1]-s*r[3],s*r[0]+c*r[2],s*r[1]+c*r[3])
            key_errors.append(max(abs(a-b) for a,b in zip(actual[bone][:4], expected)))
    samples = read(files)['animations']['external-motion']
    shifts = []
    for frame in samples:
        before, after = [matrices(d,'external-motion',frame['time']) for d in (unfit,document)]
        shifts.extend(math.dist(before[b][4:6],after[b][4:6]) for b in ('foot_l','foot_r'))
    contact = json.loads(files['motion-contact.json'])
    geometry = json.loads(files['deformation.json'])
    layers = {r['layer_id']:r['name'] for r in json.loads(files['character-manifest.json'])['layers']}
    failures = [dict(r, source_layer_name=layers.get(r['slot'])) for r in geometry['records'] if not r['passed']]
    return dict(job_id=job, artifact_sha256=artifact, motion_identity=identity,
        key_samples=len(observation['times']), timeline_samples=len(samples),
        pose_profile=evidence['profile'], temporal_foot_frame=temporal_check(document, observation),
        maximum_key_matrix_error=max(key_errors), maximum_ankle_shift_from_foot_channels_px=max(shifts),
        source_contact_markers_preserved=True, contact_status=contact['status'],
        geometry_passed=result['geometry_passed'], geometry_failures=failures,
        issues=result['issues'], runtime=result['runtime'],
        authority='none', selected=False,
        scope='foot_frame_and_attachment_geometry_not_sole_contact_or_visual_acceptance')


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('job');parser.add_argument('output',type=Path)
    args=parser.parse_args();report=run(args.job)
    with args.output.open('x',encoding='utf-8') as stream:json.dump(report,stream,ensure_ascii=False,indent=2)
    print(json.dumps({k:v for k,v in report.items() if k not in ('runtime','motion_identity','issues')}))
