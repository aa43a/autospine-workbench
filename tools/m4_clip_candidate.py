"""Isolated Spine clipping candidate; no claim from mesh-only numeric validators."""
import argparse
from base64 import b64decode,b64encode
from copy import deepcopy
from hashlib import sha256
import json
import math
from pathlib import Path
import shutil
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import canonical_bytes
from m4_candidate_comparison import crop_camera


def validate_segments(segments):
    if not 1 <= len(segments) <= 64:raise ValueError('clip_candidate_segment_budget')
    previous=None
    for segment in segments:
        start,end=segment['start'],segment['end'];frames=segment['frames']
        if (not all(math.isfinite(t) for t in (start,end)) or start<0 or end<start
                or (previous is None and start!=0) or (previous is not None and start!=previous)):
            raise ValueError('clip_candidate_segment_time')
        if not frames or frames[0]['time']!=start or frames[-1]['time']!=end:
            raise ValueError('clip_candidate_frame_endpoints')
        count=len(frames[0]['points']);last=None
        if not 3<=count<=512:raise ValueError('clip_candidate_vertex_budget')
        for frame in frames:
            time=frame['time'];points=frame['points']
            if not math.isfinite(time) or (last is not None and time<=last):
                raise ValueError('clip_candidate_frame_time')
            if len(points)!=count or any(len(p)!=2 or any(not math.isfinite(v) for v in p) for p in points):
                raise ValueError('clip_candidate_frame_points')
            last=time
        previous=end


def build(document, report, arm, body):
    candidate=deepcopy(document);animation=candidate['animations']['external-motion']
    if animation.get('drawOrder') or len(candidate['skins'])!=1 or candidate['skins'][0]['name']!='default':raise ValueError('clip_candidate_existing_order')
    validate_segments(report['segments'])
    slots={s['name']:s for s in candidate['slots']};attachments=candidate['skins'][0]['attachments']
    if arm not in slots or body not in slots:raise ValueError('clip_candidate_slots_missing')
    if list(slots).index(arm)>=list(slots).index(body):raise ValueError('clip_candidate_order_unsupported')
    names=['m4-clip-back','m4-clip-front','m4-front-mesh'];bone='m4-clip-world'
    if any(n in slots for n in names) or any(b['name']==bone for b in candidate['bones']):raise ValueError('clip_candidate_collision')
    candidate['bones'].append(dict(name=bone,x=0,y=0,rotation=0))
    original=slots[arm];mesh=attachments[arm][original['attachment']]
    if mesh.get('type')!='mesh':raise ValueError('clip_candidate_mesh_required')
    attachments[names[2]]={names[2]:dict(deepcopy(mesh),path=mesh.get('path',original['attachment']))}
    tracks=animation.setdefault('attachments',{}).setdefault('default',{})
    if arm in tracks:tracks[names[2]]={names[2]:deepcopy(tracks[arm][original['attachment']])}
    output=[]
    for slot in candidate['slots']:
        if slot['name']==arm:output.append(dict(name=names[0],bone=bone,attachment='clip-000'))
        output.append(slot)
        if slot['name']==body:output.extend([dict(name=names[1],bone=bone,attachment='clip-000'),dict(original,name=names[2],attachment=names[2])])
    candidate['slots']=output
    for side,slot,end in [('back',names[0],arm),('front',names[1],names[2])]:
        attachments[slot]={};tracks[slot]={};keys=[]
        for i,segment in enumerate(report['segments']):
            name=f'clip-{i:03d}';frames=segment['frames'];setup=[v for p in frames[0]['points'] for v in p]
            if len(setup)//2>512:raise ValueError('clip_candidate_vertex_budget')
            attachments[slot][name]=dict(type='clipping',end=end,vertexCount=len(setup)//2,vertices=setup,inverse=side=='back')
            tracks[slot][name]=dict(deform=[dict(time=f['time'],vertices=[v-setup[j] for j,v in enumerate(v for p in f['points'] for v in p)]) for f in frames])
            keys.append(dict(time=segment['start'],name=name))
        animation.setdefault('slots',{})[slot]=dict(attachment=keys)
    return candidate


def run(source,segments,output,arm,body,*,crop=None,material_bones=None):
    camera=None if crop is None else crop_camera(crop)
    receipt=json.loads((source/'report.json').read_bytes());raw=segments.read_bytes();report=json.loads(raw)
    parent=receipt['candidate_bundle_sha256']
    if report['parent']!=parent:raise ValueError('clip_candidate_parent')
    files=AnimatedStore(source/'isolated-store').read(parent);document=json.loads(files['skeleton.json'])
    candidate=build(document,report,arm,body)
    additions={};material_report=None
    if material_bones is not None:
        from m4_root_material import apply
        candidate,additions,material_report=apply(candidate,document,files,arm,body,*material_bones)
    runtime=json.loads((source/'runtime/report.json').read_bytes())
    if runtime['bundle_sha256']!=parent or not runtime['passed']:raise ValueError('clip_candidate_runtime_source')
    source_scene=json.loads((source/'runtime/player-assets/scene.json').read_bytes())
    if source_scene['artifact_sha256']!=parent or source_scene['skeleton']!=document:raise ValueError('clip_candidate_scene_source')
    textures=source_scene['textures'];expected={n:v for n,v in files.items() if n.endswith('.png')}
    if (set(textures)!=set(expected) or source_scene['atlas']!=files['skeleton.atlas'].decode()
            or any(not textures[n].startswith('data:image/png;base64,') or b64decode(textures[n].split(',',1)[1],validate=True)!=v for n,v in expected.items())
            or sha256((source/'runtime/player-assets/runtime.js').read_bytes()).hexdigest()!=runtime['runtime_sha256']):
        raise ValueError('clip_candidate_player_assets')
    output.mkdir(parents=True,exist_ok=False)
    isolated={n:v for n,v in files.items() if n.endswith('.png') or n in ('skeleton.atlas','character-manifest.json')}
    isolated['skeleton.json']=canonical_bytes(candidate)
    isolated.update(additions)
    if material_report is not None:isolated['root-material-experiment.json']=canonical_bytes(material_report)
    isolated['clipping-experiment.json']=canonical_bytes(dict(parent=parent,segments_sha256=sha256(raw).hexdigest(),authority='none',selected=False))
    digest=AnimatedStore(output/'isolated-store').publish(isolated)
    for label,doc,address in [('before',document,parent),('after',candidate,digest)]:
        target=output/label/'runtime';target.mkdir(parents=True)
        shutil.copy2(source/'runtime/player.html',target/'player.html')
        shutil.copytree(source/'runtime/player-assets',target/'player-assets')
        scene=deepcopy(source_scene);scene['skeleton']=doc;scene['artifact_sha256']=address;scene['info']['slots']=len(doc['slots'])
        if label=='after' and additions:
            scene['atlas']=isolated['skeleton.atlas'].decode()
            scene['textures'].update({n:'data:image/png;base64,'+b64encode(v).decode() for n,v in additions.items() if n.endswith('.png')})
        if camera is not None:
            scene['info'].update(camera)
            with (target/'player.html').open('a',encoding='utf-8') as stream:
                stream.write('<style>canvas{width:min(100%,600px)!important;height:auto!important;image-rendering:pixelated}</style>')
        (target/'player-assets/scene.json').write_bytes(canonical_bytes(scene))
    views=[dict(url=f'{label}/runtime/player.html',artifact=address,geometry_passed=True if label=='before' else None,
                runtime_status='既有数值证据' if label=='before' else '新裁剪实验，待验证',unreliable_samples='未统计') for label,address in [('before',parent),('after',digest)]]
    count=len(report['segments'])
    (output/'comparison.json').write_bytes(canonical_bytes(dict(authority='none',selected=False,title='Reach 连续裁剪边界实验',headings=['原候选（相同视角）','连续裁剪候选'],
        view_scope='full_character' if camera is None else 'diagnostic_world_crop',camera=camera,
        note=f'右肩源骨架深度代理，{count} 个拓扑区间。'+('另含近端连接片材料实验；不固定远端袖布。' if additions else '')+'尚未通过裁剪数值、跨图层、插值深度和视觉验收；左臂未修复。',rows=[dict(label='Reach',views=views)])))
    for name,target in [('m4-reach-comparison.html','index.html'),('m4-reach-comparison.js','comparison.js')]:shutil.copy2(Path('tools')/name,output/target)
    (output/'report.json').write_bytes(canonical_bytes(dict(parent=parent,candidate=digest,authority='none',selected=False,segments=count,runtime_status='not_evaluated',runtime_sha256=runtime['runtime_sha256'],material=material_report)))
    print(digest)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('source','segments','output'):p.add_argument(name,type=Path)
    p.add_argument('--arm',required=True);p.add_argument('--body',required=True);p.add_argument('--crop',nargs=4,type=float)
    p.add_argument('--material-bones',nargs=2,metavar=('ROOT','DISTAL'))
    a=p.parse_args();run(a.source,a.segments,a.output,a.arm,a.body,crop=a.crop,material_bones=a.material_bones)
