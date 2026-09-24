"""Identity-checked same-time surface reference and existing Runtime captures."""
import argparse
import base64
from hashlib import sha256
import json
import math
from pathlib import Path
from PIL import Image
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.targets.character43.affine_pose import matrices


def bend(points):
    a,b,c=points;end=[c[i]-a[i] for i in (0,1)];k=[b[i]-a[i] for i in (0,1)]
    length=math.dist(a,b)+math.dist(b,c)
    if math.hypot(*end)<1e-8 or length<1e-8:raise ValueError('collapsed_chain')
    return (end[0]*k[1]-end[1]*k[0])/math.hypot(*end)/length


def checked(path,digest):
    raw=path.read_bytes()
    if sha256(raw).hexdigest()!=digest:raise ValueError('capture_identity_changed')
    return raw


def panel(raw,size,joints,label):
    width,height=size
    svg=f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="{label}"><image width="{width}" height="{height}" href="data:image/png;base64,{base64.b64encode(raw).decode()}"/>'
    for side,points in joints.items():
        color='#ff9955' if side=='left' else '#55ccff'
        svg+=f'<polyline points="'+ ' '.join(f'{x},{y}' for x,y in points)+f'" fill="none" stroke="{color}" stroke-width="3"/>'
        for x,y in points:svg+=f'<circle cx="{x}" cy="{y}" r="5" fill="{color}"/>'
    return '<figure><figcaption>'+label+'</figcaption>'+svg+'</svg></figure>'


def run(reference,target,state,output):
    if output.exists():raise ValueError('output_exists')
    source=json.loads((reference/'report.json').read_bytes())
    receipt=json.loads((target/'report.json').read_bytes())
    runtime=json.loads((target/'runtime/report.json').read_bytes())
    artifact=receipt['candidate_bundle_sha256']
    if runtime['bundle_sha256']!=artifact or not runtime['passed'] or not source['endpoint_fidelity_passed']:
        raise ValueError('numeric_reference_not_verified')
    request=json.loads((state/'jobs/motion-intake-v1'/receipt['job_id']/'request.json').read_bytes())
    if request.get('clip') is not None:raise ValueError('cropped_candidate_requires_explicit_source_offset')
    source_request=json.loads((state/'jobs/motion-intake-v1'/request['source_job_id']/'request.json').read_bytes())
    if source_request['source_sha256'] != source['motion_sha256']:raise ValueError('motion_source_mismatch')
    files=AnimatedStore(target/'isolated-store').read(artifact)
    doc=json.loads(files['skeleton.json']);animation,=doc['animations']
    info=runtime['info'];rows=[];body=[]
    for capture in source['captures']:
        if capture['yaw_degrees']!=receipt['view']['yaw_degrees']:raise ValueError('view_mismatch')
        time=capture['time']
        matches=[s for s in runtime['screenshots'] if s['animation']==animation and
                 abs(runtime['results'][s['index']]['time']-time)<1e-9]
        if len(matches)!=1:raise ValueError('exact_runtime_capture_required')
        shot=matches[0]
        original=checked(reference/capture['image'],capture['image_sha256'])
        actual=checked(target/'runtime'/shot['file'],shot['sha256'])
        size=Image.open(reference/capture['image']).size
        pose=matrices(doc,animation,time);sj={};tj={};measures=[]
        for side,suffix,prefix in [('left','l','Left'),('right','r','Right')]:
            values=[capture['joints'][prefix+n]['head'] for n in ('UpLeg','Leg','Foot')]
            sj[side]=[[p[0]*size[0],(1-p[1])*size[1]] for p in values]
            tj[side]=[[pose[n+'_'+suffix][4]-info['left'],info['bottom']+info['height']-pose[n+'_'+suffix][5]] for n in ('thigh','calf','foot')]
            a,b=bend(sj[side]),bend(tj[side])
            measures.append(dict(side=side,source_normalized_bend=a,target_normalized_bend=b,
                branch='unknown' if min(abs(a),abs(b))<.01 else 'match' if a*b>0 else 'opposite'))
        rows.append(dict(time=time,source_image_sha256=capture['image_sha256'],target_image_sha256=shot['sha256'],legs=measures))
        body.append(f'<h2>{time:.9f} 秒 · yaw {capture["yaw_degrees"]}°</h2><main>'+panel(original,size,sj,'三维参考模型')+
                    panel(actual,(info['width'],info['height']),tj,'当前 Spine 候选：原几何失败仍保留')+'</main>')
    output.mkdir(parents=True)
    report=dict(artifact=artifact,source_sha256=source_request['source_sha256'],records=rows,
        scope='same_time_declared_view_joint_and_surface_comparison_not_acceptance',authority='none',
        reused_runtime_captures=True,target_geometry_passed=receipt['geometry_passed'])
    (output/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    html='<meta charset="utf-8"><title>同帧同视角膝部对照</title><style>body{background:#17232e;color:white;font:16px system-ui}main{display:grid;grid-template-columns:1fr 1fr}svg{width:100%;max-height:720px}figure{margin:12px}</style><h1>同帧同视角膝部对照</h1><p>橙：左腿；蓝：右腿。分别显示各自相机范围，没有变形对齐图像；不同身体比例不计为像素误差。参考表面不等于目标素材。</p>'
    (output/'index.html').write_text(html+''.join(body),encoding='utf-8')
    print(json.dumps(report))


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for key in ('reference','target','state','output'):p.add_argument(key,type=Path)
    a=p.parse_args();run(a.reference,a.target,a.state,a.output)
