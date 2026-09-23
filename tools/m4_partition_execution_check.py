"""Submit a clearly labeled diagnostic hand-region proposal through the live API."""
import json
from pathlib import Path
from urllib.request import Request,urlopen
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.targets.character43.deform_addition import entries

BASE='http://127.0.0.1:8918'
PARENT='motion-a7a946be55ee44169e8ccb6e0fe4baa7'


def request(path,body=None):
    r=Request(BASE+path,data=json.dumps(body).encode() if body is not None else None,
        headers={'Origin':BASE,'Content-Type':'application/json','X-Autospine-Intent':'pipeline-preview'})
    return json.load(urlopen(r,timeout=120))


if __name__=='__main__':
    prefix='/api/motions/'+PARENT
    state=request(prefix+'/repair-draft');report=request(prefix+'/view/geometry-details.json')
    row=next(r for r in report['rows'] if r['slot']=='layer-004');event=row['details'][0]
    doc=json.loads(AnimatedStore(Path('workspace')).read(state['artifact_sha256'])['skeleton.json'])
    mesh=doc['skins'][0]['attachments']['layer-004']['layer-004'];owners=entries(mesh)
    hand=next(i for i,b in enumerate(doc['bones']) if b['name']=='hand_l')
    weights=[sum(w for b,w in v if b==hand) for v in owners]
    selected=[i//3 for i in range(0,len(mesh['triangles']),3) if min(weights[v] for v in mesh['triangles'][i:i+3])>=.8]
    assert selected
    geometry=next(r for r in request(prefix+'/view/partition-mesh.json')['rows'] if r['slot']=='layer-004')
    body=dict(artifact_sha256=state['artifact_sha256'],evidence_sha256=state['evidence_sha256'],expected_revision=state['revision'],
        action='partition',slot='layer-004',animation=row['animation'],triangle=event['triangle'],time=event['time'],
        notes='Diagnostic automatically proposed hand-dominant region; not user annotation or acceptance.',
        partition=dict(mesh_sha256=geometry['mesh_sha256'],triangles=selected,bone='hand_l'))
    saved=request(prefix+'/repair-draft',body)
    job=request(prefix+'/repair-execute',dict(revision=saved['revision'],draft_sha256=saved['draft_sha256s'][-1]))
    receipt=dict(job=job,parent=PARENT,draft_revision=saved['revision'],selected_triangles=len(selected),draft_body=body)
    out=Path('tmp/partition-execution-v1');out.mkdir(exist_ok=True)
    with (out/'submission.json').open('x',encoding='utf-8') as f:json.dump(receipt,f,indent=2)
    print(json.dumps(dict(job=job['job_id'],triangles=len(selected))))
