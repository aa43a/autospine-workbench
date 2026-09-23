"""Exercise actual handoff download using a temporary, explicitly withdrawn plan."""
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import sys
from urllib.request import Request, urlopen
from zipfile import ZipFile

base,job,destination=sys.argv[1:]
root=Path(destination);root.mkdir(parents=True,exist_ok=True)
def call(tail,body=None):
    request=Request(base+'/api/motions/'+job+tail,
        data=None if body is None else json.dumps(body).encode(),
        headers={'Origin':base,'Content-Type':'application/json','X-Autospine-Intent':'pipeline-preview'})
    with urlopen(request,timeout=180) as response:return response.read()
state=json.loads(call('/repair-draft'))
report=json.loads(call('/view/geometry-details.json'))
record=next(r for r in report['rows'] if r['details']);event=record['details'][0]
key=lambda r:(r['slot'],r['animation'],r['event']['triangle'],r['event']['time'])
matching=[r for r in state['history'] if key(r)==(record['slot'],record['animation'],event['triangle'],event['time'])]
assert not matching or matching[-1]['action']=='withdraw', 'Do not overwrite an active user plan'
body=dict(artifact_sha256=state['artifact_sha256'],evidence_sha256=state['evidence_sha256'],
 expected_revision=state['revision'],action='pose_attachment',notes='Temporary offline handoff regression; withdraw after download; not a material decision.',
 slot=record['slot'],animation=record['animation'],triangle=event['triangle'],time=event['time'])
saved=json.loads(call('/repair-draft',body));revision=saved['revision']
result=dict(job_id=job,temporary_revision=revision,artifact_sha256=state['artifact_sha256'])
try:
    raw=call('/repair-material/'+str(revision));(root/'task.zip').write_bytes(raw)
    with ZipFile(BytesIO(raw)) as archive:
        inventory=json.loads(archive.read('inventory.json'))
        for name,digest in inventory.items():assert sha256(archive.read(name)).hexdigest()==digest
        request=json.loads(archive.read('request.json'))
        assert request['artifact_sha256']==state['artifact_sha256']
        assert request['draft_revision']==revision
        assert archive.read('pose-preview.html')
        (root/'pose-preview.html').write_bytes(archive.read('pose-preview.html'))
        (root/'request.json').write_bytes(archive.read('request.json'))
        (root/'event.json').write_text(json.dumps(saved['history'][-1]),encoding='utf8')
        result.update(files=sorted(archive.namelist()),zip_bytes=len(raw),inventory_verified=True)
finally:
    withdrawn=json.loads(call('/repair-draft',{**body,'expected_revision':revision,'action':'withdraw',
        'notes':'Offline handoff regression completed; temporary plan withdrawn; no replacement or acceptance.'}))
    result['withdrawn_revision']=withdrawn['revision']
    (root/'report.json').write_text(json.dumps(result,indent=2),encoding='utf8')
print(json.dumps(result))
