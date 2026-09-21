"""Create an isolated pose-calibration experiment from an exact M4 request."""
import argparse
from copy import deepcopy
import json
import math
from pathlib import Path

from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.motion_bundle_reader import VerifiedMotionBundleReader
from autospine_workbench.targets.character43.affine_pose import matrices
from autospine_workbench.targets.character43.motionir_candidate import build, ROLES
from autospine_workbench.targets.character43.oblique_source import extract
from autospine_workbench.targets.character43.source_pose_fit import fit


def run(job, output):
    request = json.loads((Path('workspace/jobs/motion-intake-v1')/job/'request.json').read_bytes())
    if request.get('projection') or request.get('clip'):
        raise ValueError('probe_requires_full_original_projection')
    identity = request['motion_identity']
    bundle = VerifiedMotionBundleReader(Path('workspace')).load(identity['clip_sha256'], identity['bundle_sha256'])
    files = AnimatedStore(Path('workspace')).read(request['character_sha256'])
    setup = json.loads(files['skeleton.json']); setup['animations'] = {}
    baseline, _ = build(setup, bundle.motion, 'external-motion')
    vectors, _, _ = extract(bundle)
    ticks = next(t for t in bundle.motion['tracks'] if t['property'] == 'rotation')['keys']
    times = [k['tick']/bundle.motion['ticks_per_second'] for k in ticks]
    candidate, report = fit(baseline, 'external-motion', vectors, times)
    records = {r['bone']: r for r in report['records']}
    frames = []
    for i, time in enumerate(times):
        before = matrices(baseline, 'external-motion', time)
        after = matrices(candidate, 'external-motion', time)
        for role, values in vectors.items():
            bone = ROLES.get(role)
            if bone not in records:
                continue
            x, y, _ = values[i]
            angle = math.degrees(math.atan2(-y, x))
            m = before[bone]
            error = abs((math.degrees(math.atan2(m[2], m[0]))-angle+180) % 360-180)
            row = records[bone]
            row['baseline_maximum_direction_error_deg'] = max(row.get('baseline_maximum_direction_error_deg', 0), error)
        frames.append(dict(time=time, before={n: list(m[4:]) for n, m in before.items()},
                           after={n: list(m[4:]) for n, m in after.items()}))
    report.update(source_job_id=request['source_job_id'], baseline_job_id=job,
                  source_identity=identity, character_sha256=request['character_sha256'],
                  scope='rotation_only_calibration_experiment_not_replacement_for_existing_candidate',
                  runtime_verified=False)
    output.mkdir(parents=True, exist_ok=False)
    (output/'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    (output/'skeleton.json').write_text(json.dumps(candidate), encoding='utf-8')
    data = json.dumps(dict(frames=frames, bones=setup['bones'])).replace('<', '\\u003c')
    page = '''<!doctype html><meta charset="utf-8"><title>源姿态对齐实验</title>
<style>body{background:#15232e;color:white;font:16px sans-serif}canvas{background:#263744}input{width:70%}</style>
<h1>第一帧归零 / 绝对方向拟合</h1><p>左：原旋转重定向；右：源方向拟合。仅骨架实验，尚未验证网格、接触和遮挡。</p>
<button id="play">播放/暂停</button><input id="seek" type="range" min="0" step="1"><span id="time"></span><br>
<canvas id="view" width="1200" height="720"></canvas><p><a href="report.json">误差与不可靠投影区间</a></p>
<script>const data=DATA;const slider=document.querySelector('#seek'),canvas=document.querySelector('#view'),ctx=canvas.getContext('2d');
slider.max=data.frames.length-1;let playing=false,last=0;
const points=data.frames.flatMap(f=>Object.values(f.before).concat(Object.values(f.after)));
const xs=points.map(p=>p[0]),ys=points.map(p=>p[1]);const xmin=Math.min(...xs),xmax=Math.max(...xs),ymin=Math.min(...ys),ymax=Math.max(...ys);
const scale=Math.min(540/(xmax-xmin),620/(ymax-ymin));
function draw(){const f=data.frames[+slider.value];ctx.clearRect(0,0,1200,720);document.querySelector('#time').textContent=f.time.toFixed(3)+' s';
['before','after'].forEach((key,col)=>{const xy=p=>[col*600+300+(p[0]-(xmin+xmax)/2)*scale,360-(p[1]-(ymin+ymax)/2)*scale];
for(const b of data.bones){if(!b.parent)continue;const a=xy(f[key][b.parent]),z=xy(f[key][b.name]);ctx.strokeStyle=col?'#62efb8':'#ffba70';ctx.beginPath();ctx.moveTo(...a);ctx.lineTo(...z);ctx.stroke();}});}
slider.oninput=draw;document.querySelector('#play').onclick=()=>playing=!playing;
function tick(now){if(playing&&now-last>33){slider.value=(+slider.value+1)%data.frames.length;draw();last=now;}requestAnimationFrame(tick);}draw();requestAnimationFrame(tick);</script>'''
    (output/'index.html').write_text(page.replace('DATA', data), encoding='utf-8')
    print(json.dumps(dict(job=job, output=str(output), records=report['records'])))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('job'); parser.add_argument('output', type=Path)
    args = parser.parse_args(); run(args.job, args.output)
