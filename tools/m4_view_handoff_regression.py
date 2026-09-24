"""Queue an explicit original-texture correspondence regression, not new artwork."""
import argparse
import base64
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import urllib.request
import urllib.error
from zipfile import ZipFile

from autospine_workbench.targets.character43.affine_pose import sample


def run(base, job, output):
    def request(path, body=None, raw=False):
        data=None if body is None else json.dumps(body).encode()
        req=urllib.request.Request(base+path,data=data,headers={
            'Content-Type':'application/json','X-Autospine-Intent':'pipeline-preview','Origin':base})
        try:
            with urllib.request.urlopen(req,timeout=120) as response:
                value=response.read()
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f'{exc.code}: {exc.read().decode()}') from exc
        return value if raw else json.loads(value)
    path='/api/motions/'+job
    state=request(path+'/repair-draft')
    # Do not supersede any live human or experimental intervention.
    latest={}
    for row in state['history']:
        latest[(row['slot'],row['animation'],row['event']['triangle'],row['event']['time'])]=row
    resume=json.loads((output/'draft.json').read_text(encoding='utf-8')) if (output/'draft.json').exists() else None
    if (output/'submitted.json').exists():
        raise ValueError('Already submitted; poll the existing job instead of resubmitting')
    if resume is not None and resume!=state:
        raise ValueError('Recorded draft changed; inspect instead of overwriting')
    if resume is None and any(r['action']!='withdraw' for r in latest.values()):
        raise ValueError('Use a candidate with no active intervention drafts')
    report=request(path+'/view/geometry-details.json')
    row=report['rows'][0];event=row['details'][0]
    plan=dict(artifact_sha256=state['artifact_sha256'],evidence_sha256=state['evidence_sha256'],
        expected_revision=state['revision'],action='pose_attachment',slot=row['slot'],animation=row['animation'],
        triangle=event['triangle'],time=event['time'],view_needs=['side'],
        notes='Original-texture handoff regression only; not new side artwork, repair or visual acceptance')
    saved=resume or request(path+'/repair-draft',plan);revision=saved['revision']
    output.mkdir(parents=True,exist_ok=True)
    (output/'draft.json').write_text(json.dumps(saved,indent=2),encoding='utf-8')
    template=request(path+'/view-pose-template/'+str(revision))
    with ZipFile(BytesIO(request(path+'/repair-material/'+str(revision),raw=True))) as archive:
        png=archive.read('source-texture.png')
    with ZipFile(BytesIO(request(path+'/download',raw=True))) as archive:
        doc=json.loads(archive.read('skeleton.json'))
    duration=template['view_pose']['interval'][1]
    time=min(.1,duration/4);interval=[time/2,time*1.5]
    controls=template['control_template'];controls['target_xy']=sample(doc,row['animation'],time)[0][row['slot']]
    template['view_pose'].update(interval=interval,poses=[dict(time=time,correspondence=controls)],
        texture_sha256=sha256(png).hexdigest(),texture_size=template['request']['texture_size'])
    (output/'handoff.json').write_text(json.dumps(template),encoding='utf-8')
    result=request(path+'/view-pose-execute',dict(request=template['request'],view_pose=template['view_pose'],
        png_base64=base64.b64encode(png).decode()))
    (output/'submitted.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(dict(job_id=result['job_id'],parent=job,revision=revision,interval=interval,
        purpose='original_texture_transport_regression_not_visual_repair')))


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--base',default='http://127.0.0.1:8918')
    parser.add_argument('--job',required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();run(args.base,args.job,args.output)
