"""Package a verified experimental scene for fresh official WebGL diagnostics."""
import argparse
import base64
from hashlib import sha256
import json
from pathlib import Path
import struct
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.targets.character43.numeric_reference import write


def select_frames(frames, motion, requested):
    selected={0,len(frames)-1}
    selected.update(round(i*(len(frames)-1)/16) for i in range(17))
    for time in requested:
        index=min(range(len(frames)),key=lambda i:abs(frames[i]['time']-time))
        if abs(frames[index]['time']-time)>1e-5:raise ValueError('capture_requested_time_unavailable')
        selected.add(index)
    tracks=[motion.get('drawOrder',[])]
    tracks.extend(c.get('attachment',[]) for c in motion.get('slots',{}).values())
    for keys in tracks:
        for key in keys:
            time=struct.unpack('f',struct.pack('f',key.get('time',0)))[0]
            index=next((i for i,f in enumerate(frames) if f['time']>=time),None)
            if index is None or frames[index]['time']!=time:raise ValueError('capture_switch_boundary_missing')
            selected.update(i for i in (index-1,index,index+1) if 0<=i<len(frames))
    return [frames[i] for i in sorted(selected)]


def run(source,output,times):
    scene_raw=(source/'candidate.json').read_bytes();reference_raw=(source/'active-reference.json').read_bytes()
    core=json.loads((source/'official-core.json').read_bytes())
    if not core['passed'] or core['input_sha256']!=[sha256(scene_raw).hexdigest(),sha256(reference_raw).hexdigest()]:
        raise ValueError('scene_capture_unverified_source')
    scene=json.loads(scene_raw);reference=json.loads(reference_raw);doc=scene['skeleton'];animation=reference['animation']
    if set(doc['animations'])!={animation}:raise ValueError('scene_capture_animation_inventory')
    frames=select_frames(reference['frames'],doc['animations'][animation],times)
    raw=canonical_bytes(doc);files={'skeleton.json':raw,'skeleton.atlas':scene['atlas'].encode()}
    for name,uri in scene['textures'].items():
        prefix='data:image/png;base64,'
        if not name.endswith('.png') or not uri.startswith(prefix):raise ValueError('scene_capture_texture')
        files[name]=base64.b64decode(uri[len(prefix):],validate=True)
    files['character-manifest.json']=canonical_bytes(dict(authority='none',production_authorized=False,
        source_scene_sha256=sha256(scene_raw).hexdigest(),scope='diagnostic_render_not_adoption'))
    files=write(files,dict(skeleton_sha256=sha256(raw).hexdigest(),animations={animation:frames}))
    output.mkdir(parents=True,exist_ok=False);store=AnimatedStore(output/'isolated-store');digest=store.publish(files)
    receipt=dict(candidate_bundle_sha256=digest,source_scene_sha256=sha256(scene_raw).hexdigest(),
        source_reference_sha256=sha256(reference_raw).hexdigest(),authority='none',selected=False,
        frames=len(frames),times=[f['time'] for f in frames],scope='diagnostic_times_and_switch_boundaries_not_full_clip_capture')
    (output/'report.json').write_bytes(canonical_bytes(receipt))
    print(json.dumps(dict(folder=str((store.root/digest).resolve()),**receipt)))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('source',type=Path);p.add_argument('output',type=Path)
    p.add_argument('--time',type=float,action='append',default=[])
    a=p.parse_args();run(a.source,a.output,a.time)
