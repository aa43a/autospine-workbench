"""Isolated FBX/BVH inspection and explicit Mixamo MotionIR compilation."""
from dataclasses import asdict
from hashlib import sha256
import json
import math
from pathlib import Path
import runpy
import subprocess
import sys

from ..bvh_parser import parse_bvh
from ..bvh_fk import _world_matrices, _origin
from ..motion2d.mixamo_map import build_map
from ..motion_bvh_commands import compile_bvh_motion_bundle
from .storage_io import canonical_bytes, read_document
from .motion_intake_process import progress

VIEWS = {'front': ('+X', '-Y', '+Z'), 'side': ('-Z', '-Y', '+X')}


def inspect_bvh(raw, view):
    bvh = parse_bvh(raw)
    names = [b.name for b in bvh.joints]
    indices = sorted({round(i*(bvh.frame_count-1)/min(239, max(1,bvh.frame_count-1)))
                      for i in range(min(240,bvh.frame_count))})
    frames = [dict(time=i*bvh.frame_time_seconds, frame=i,
                   joints=[list(_origin(m)) for m in _world_matrices(bvh,bvh.frames[i])]) for i in indices]
    preview = dict(schema='autospine.source-motion-preview/v1', names=names,
                   parents=[b.parent_index for b in bvh.joints], frames=frames, view=view,
                   scope='source_joint_samples_not_character_animation')
    return bvh, preview


def compile_source(raw, view, folder, state_root):
    progress(folder, 'inspect_bvh')
    bvh, preview = inspect_bvh(raw, view)
    preview_raw=canonical_bytes(preview);(folder/'preview.json').write_bytes(preview_raw)
    result=dict(frame_count=bvh.frame_count, joint_count=len(bvh.joints),
                fps=1/bvh.frame_time_seconds, duration_seconds=(bvh.frame_count-1)*bvh.frame_time_seconds,
                preview_sha256=sha256(preview_raw).hexdigest(), bvh_sha256=sha256(raw).hexdigest(),
                projection=view, contact_status='not_inferred', loop=False,
                target_runtime_status='not_evaluated', character_animation_status='not_built')
    names={b.name:b for b in bvh.joints}
    prefixes=[p for p in ('','mixamorig:') if all(p+n in names for n in
              ('Hips','LeftUpLeg','LeftLeg','LeftFoot','RightUpLeg','RightLeg','RightFoot'))]
    if len(prefixes)!=1:
        return dict(result,motion_status='needs_mapping',reason_code='motion_skeleton_mapping_required')
    prefix=prefixes[0]
    reference=sum(math.sqrt(sum(v*v for v in names[prefix+n].offset)) for n in
                  ('LeftLeg','LeftFoot','RightLeg','RightFoot'))/2
    try:
        progress(folder, 'compile_motion')
        mapping=build_map(bvh,clip_id='external.'+sha256(raw).hexdigest()[:16]+'.'+view,
                          reference_length=reference,screen_x=VIEWS[view][0],screen_y=VIEWS[view][1],
                          depth=VIEWS[view][2],prefix=prefix)
        (folder/'map.json').write_bytes(canonical_bytes(mapping))
        compiled=compile_bvh_motion_bundle(state_root,folder/'source.bvh',folder/'map.json')
    except (ValueError,RuntimeError) as exc:
        return dict(result,motion_status='needs_mapping',reason_code='motion_projection_or_mapping_unsupported',
                    diagnostic=str(exc)[:500])
    identity=asdict(compiled);identity.pop('path',None)
    return dict(result,motion_status='compiled',motion=identity,
                reference_length_source_units=reference,reference_policy='mean_rest_leg_segment_lengths')


def execute(folder, state_root, blender):
    progress(folder, 'verify_source')
    request=read_document(folder/'request.json');source=folder/('source.'+request['format'])
    if sha256(source.read_bytes()).hexdigest()!=request['source_sha256']:
        raise ValueError('motion_source_changed')
    if request['format']=='fbx':
        progress(folder, 'convert_fbx')
        if not blender or not Path(blender).is_file():raise ValueError('motion_blender_unavailable')
        tools=Path(__file__).resolve().parents[3]/'tools'
        command=[blender,'--background','--factory-startup','--python-exit-code','1',
                 '--python',str(tools/'export-fbx-bvh.py'),'--',str(source),str(folder/'source.bvh'),'--root-only']
        with (folder/'blender.log').open('wb') as log:
            process=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,timeout=180)
        if process.returncode:raise ValueError('motion_fbx_conversion_failed')
        evidence=json.loads((folder/'source.inspection.json').read_bytes())
        progress(folder, 'verify_bridge')
        if evidence['source_sha256'] != request['source_sha256']:
            raise ValueError('motion_source_changed')
        verify=runpy.run_path(str(tools/'verify-fbx-bvh.py'))['verify']
        verified=verify((folder/'source.bvh').read_bytes(),evidence)
        (folder/'bridge-verification.json').write_bytes(canonical_bytes(verified))
        if not verified['passed']:raise ValueError('motion_fbx_bridge_mismatch')
    if request['format'] == 'npz':
        from .motion_kimodo_intake import compile_source as compile_npz
        result = compile_npz(source.read_bytes(), request, folder, state_root, producer=request.get('source_producer'))
    else:
        result=compile_source((folder/'source.bvh').read_bytes(),request['view'],folder,state_root)
    if request['format'] == 'fbx':
        result['fbx_bridge'] = verified
    if sha256(source.read_bytes()).hexdigest()!=request['source_sha256']:raise ValueError('motion_source_changed')
    (folder/'worker-result.json').write_bytes(canonical_bytes(result))


if __name__=='__main__':
    try:execute(Path(sys.argv[1]),Path(sys.argv[2]),sys.argv[3])
    except Exception as exc:
        print(json.dumps(dict(reason_code=str(exc)[:200])))
        sys.exit(1)
