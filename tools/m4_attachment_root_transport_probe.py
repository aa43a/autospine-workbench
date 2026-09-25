"""Experimental root transport on a baked torso candidate; no automatic adoption."""
import argparse
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path

from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.automation.motion_target_pose import final_times
from autospine_workbench.targets.character43.affine_pose import matrices
from autospine_workbench.targets.character43.attachment_root_transport import displacements
from autospine_workbench.targets.character43.numeric_reference import read
from autospine_workbench.targets.character43.torso_projection_candidate import transformed, inverse
from autospine_workbench.targets.spine43.continuous_pose import interpolate
from autospine_workbench.targets.character43.runtime_storage_reference import f32


def run(source, output, roots):
    receipt = json.loads((source/'report.json').read_bytes())
    files = AnimatedStore(source/'isolated-store').read(receipt['candidate_bundle_sha256'])
    torso = json.loads(files['motion-torso-projection.json'])
    if torso.get('applied') is not True:
        raise ValueError('attachment_transport_requires_baked_torso')
    doc = json.loads(files['skeleton.json']); candidate = deepcopy(doc); name = 'external-motion'
    rows = torso['source']['records']
    shapes = [dict(time=r['time'], vertices=[r['longitudinal'],r['shear'],r['transverse']]) for r in rows]
    reference_times = final_times(doc, name, [r['time'] for r in read(files)['animations'][name]])
    # Bake anew on representable times, rather than emit colliding Float32 keys.
    # The independent checker still evaluates every original reference time.
    times = sorted({f32(time) for time in reference_times})
    tracks = candidate['animations'][name].setdefault('attachments',{}).setdefault('default',{})
    changes = {}; maximum = 0.
    for time in times:
        old = matrices(doc,name,time); warped = transformed(doc,old,interpolate(shapes,time,'vertices'))
        shifts = displacements(doc['bones'],old,warped,'chest',roots)
        for slot, choices in doc['skins'][0]['attachments'].items():
            data = choices[slot]['vertices']; values = []; i = j = 0; touched = False
            keys = doc['animations'][name].get('attachments',{}).get('default',{}).get(slot,{}).get(slot,{}).get('deform')
            previous = interpolate(keys,time,'vertices') if keys else []
            while i < len(data):
                count = data[i]; i += 1
                for _ in range(count):
                    index,x,y,weight = data[i:i+4]; i += 4
                    bone = doc['bones'][index]['name']
                    px,py = previous[j:j+2] if previous else (0.,0.); j += 2
                    if bone in shifts and weight > 0:
                        dx,dy = shifts[bone]; m = inverse(old[bone])
                        px += m[0]*dx+m[1]*dy; py += m[2]*dx+m[3]*dy
                        maximum = max(maximum,(dx*dx+dy*dy)**.5); touched = True
                    values.extend((px,py))
            if touched:
                changes.setdefault(slot,[]).append(dict(time=time,vertices=values))
    if not changes:
        raise ValueError('attachment_transport_no_affected_vertices')
    for slot, keys in changes.items():
        tracks[slot] = {slot: {'deform': keys}}
    output.mkdir(parents=True,exist_ok=False)
    raw = canonical_bytes(candidate)
    (output/'skeleton.json').write_bytes(raw)
    report = dict(source_candidate=receipt['candidate_bundle_sha256'],skeleton_sha256=sha256(raw).hexdigest(),
                  rows=[dict(slot=s) for s in sorted(changes)],roots=roots,maximum_root_shift_px=maximum,
                  original_reference_samples=len(reference_times),key_samples=len(times),
                  time_policy='recompute_at_distinct_runtime_float32_times_preserve_original_qa_samples',
                  authority='none',selected=False,scope='root_translation_experiment_requires_all_target_checks')
    (output/'report.json').write_bytes(canonical_bytes(report))
    print(json.dumps(report),flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('source',type=Path);parser.add_argument('output',type=Path)
    parser.add_argument('--root',action='append',required=True)
    args = parser.parse_args();run(args.source,args.output,args.root)
