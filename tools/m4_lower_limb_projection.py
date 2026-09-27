"""Compare verified source knee depth with an exact, unchanged animated artifact."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.motion_bundle_reader import VerifiedMotionBundleReader
from autospine_workbench.targets.character43.affine_pose import matrices
from autospine_workbench.targets.character43.lower_limb_projection import angle, measure
from autospine_workbench.targets.character43.oblique_source import extract


def run(state, job, artifact, output):
    raw=(state/'jobs/motion-intake-v1'/job/'request.json').read_bytes()
    request=json.loads(raw)
    if request.get('projection') or request.get('clip'):
        raise ValueError('requires_full_original_projection')
    identity=request['motion_identity']
    bundle=VerifiedMotionBundleReader(state).load(identity['clip_sha256'],identity['bundle_sha256'])
    files=AnimatedStore(state).read(artifact)
    if json.loads(files['motion-ir.json'])!=bundle.motion:
        raise ValueError('source_candidate_motion_mismatch')
    document=json.loads(files['skeleton.json'])
    vectors,_,_=extract(bundle)
    tracks=[t for t in bundle.motion['tracks'] if t['property']=='rotation']
    ticks=[k['tick'] for k in tracks[0]['keys']]
    if any([k['tick'] for k in t['keys']]!=ticks for t in tracks):
        raise ValueError('source_times_mismatch')
    frames=[]
    for i,tick in enumerate(ticks):
        time=tick/bundle.motion['ticks_per_second'];pose=matrices(document,'external-motion',time)
        sides={}
        for side,suffix in [('left','l'),('right','r')]:
            u,l=(vectors[f'humanoid.leg.{part}.{side}'] for part in ('upper','lower'))
            if len(u)!=len(ticks) or len(l)!=len(ticks):raise ValueError('source_count_mismatch')
            points=[pose[f'{name}_{suffix}'][4:] for name in ('thigh','calf','foot')]
            origin=points[0];points=[[x-origin[0],origin[1]-y] for x,y in points]
            target_angle=angle(points[1],[b-a for a,b in zip(points[1],points[2])])
            sides[side]=dict(source=measure(u[i],l[i]),side_projection=measure(u[i],l[i],yaw=90),
                             target_points=points,target_bend_deg=target_angle)
        frames.append(dict(time=time,sides=sides))
    summary={}
    for side in ('left','right'):
        worst=max(frames,key=lambda f:f['sides'][side]['source']['hidden_bend_deg'] or 0)
        summary[side]=dict(time=worst['time'],**worst['sides'][side])
    report=dict(profile='source-knee-depth-comparison-v1',authority='none',selected=False,
        source_job=job,request_sha256=sha256(raw).hexdigest(),source_identity=identity,
        artifact_sha256=artifact,skeleton_sha256=sha256(files['skeleton.json']).hexdigest(),
        basis=json.loads((bundle.path/'map.json').read_bytes())['basis'],frames=frames,summary=summary,
        scope='source_frame_joint_projection_only_not_mesh_occlusion_or_visual_acceptance')
    output.mkdir(parents=True,exist_ok=False)
    (output/'report.json').write_bytes(canonical_bytes(report))
    (output/'index.html').write_text(render(frames),encoding='utf-8')
    print(json.dumps(summary),flush=True)
    return report


def render(frames):
    data=json.dumps(frames).replace('<','\\u003c')
    return '''<!doctype html><meta charset="utf-8"><title>膝盖深度与二维投影</title>
<style>body{background:#13212d;color:#e6edf5;font:16px sans-serif;margin:24px}canvas{background:#203342;width:100%;max-width:1100px}input{width:65%}pre{white-space:pre-wrap}</style>
<h1>膝盖前后关系 · 同帧对照</h1><p>左：原始正面投影；中：源动作侧面投影；右：当前二维骨架。各栏按各自腿长归一化，髋部对齐，不表示根骨位移或贴图效果。</p>
<button id="play">播放</button> <input id="time" type="range" min="0" step="1"><span id="label"></span>
<canvas id="view" width="1100" height="500"></canvas><pre id="info"></pre>
<p>蓝色为左腿，橙色为右腿。侧视图仅展示深度证据，不是可直接采用的角色侧身素材；本页不修改候选、不判断裙腿遮挡。</p>
<script>const frames=DATA;const slider=document.getElementById('time'),canvas=document.getElementById('view'),ctx=canvas.getContext('2d');
slider.max=frames.length-1;let playing=false,last=0;document.getElementById('play').onclick=()=>{playing=!playing;last=0;};
function draw(){const f=frames[+slider.value];ctx.clearRect(0,0,1100,500);let lines=[];
['原始正面','源动作侧面','当前二维'].forEach((title,col)=>{ctx.fillStyle='white';ctx.fillText(title,80+col*365,30);
for(const [side,color] of [['left','#65cff8'],['right','#ffbd69']]){const r=f.sides[side];let p=col===2?r.target_points:[[0,0],...(col===0?[r.source.knee,r.source.ankle]:[r.side_projection.knee,r.side_projection.ankle])];
const length=Math.hypot(p[1][0],p[1][1])+Math.hypot(p[2][0]-p[1][0],p[2][1]-p[1][1]);const scale=330/Math.max(length,1e-9);ctx.strokeStyle=color;ctx.fillStyle=color;ctx.lineWidth=3;ctx.beginPath();p.forEach((v,i)=>{const x=col*365+180+v[0]*scale,y=80+v[1]*scale;i?ctx.lineTo(x,y):ctx.moveTo(x,y);});ctx.stroke();p.forEach(v=>{ctx.beginPath();ctx.arc(col*365+180+v[0]*scale,80+v[1]*scale,5,0,7);ctx.fill();});}
});for(const side of ['left','right']){const r=f.sides[side],fmt=v=>v==null?'不可判定':v.toFixed(2);lines.push(`${side}: 三维弯曲 ${fmt(r.source.bend_3d_deg)}°，正面投影 ${fmt(r.source.bend_projected_deg)}°，当前二维 ${fmt(r.target_bend_deg)}°；膝盖相对髋踝线深度/腿长 ${fmt(r.source.knee_depth_ratio)}`);}
document.getElementById('label').textContent=f.time.toFixed(3)+' s';document.getElementById('info').textContent=lines.join('\\n');}
slider.oninput=()=>{playing=false;draw();};function tick(now){if(playing&&(!last||now-last>=1000/30)){slider.value=(+slider.value+1)%frames.length;last=now;draw();}requestAnimationFrame(tick);}draw();requestAnimationFrame(tick);</script>'''.replace('DATA',data)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('state',type=Path);p.add_argument('job');p.add_argument('artifact');p.add_argument('output',type=Path)
    a=p.parse_args();run(a.state,a.job,a.artifact,a.output)
