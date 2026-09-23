"""Prepare an explicit unchanged-artwork upload check; never visual acceptance."""
import argparse
from io import BytesIO
import json
from pathlib import Path
from urllib.request import urlopen
from zipfile import ZipFile
from m4_partition_execution_check import BASE, PARENT, request


def prepare(output):
    output.mkdir(parents=True,exist_ok=False)
    prefix='/api/motions/'+PARENT
    state=request(prefix+'/repair-draft');report=request(prefix+'/view/geometry-details.json')
    row=report['rows'][0];event=row['details'][0]
    matching=[r for r in state['history'] if r['slot']==row['slot'] and r['animation']==row['animation']
              and r['event']['triangle']==event['triangle'] and r['event']['time']==event['time']]
    if matching and matching[-1]['action']!='withdraw':raise ValueError('active_plan_would_be_replaced')
    body=dict(artifact_sha256=state['artifact_sha256'],evidence_sha256=state['evidence_sha256'],
        expected_revision=state['revision'],slot=row['slot'],animation=row['animation'],
        triangle=event['triangle'],time=event['time'],action='pose_attachment',
        notes='Diagnostic live upload/recovery test using unchanged source texture; withdraw after test; not artwork repair.')
    saved=request(prefix+'/repair-draft',body)
    (output/'fixture.json').write_text(json.dumps(dict(job=PARENT,body=body,revision=saved['revision'])),encoding='utf-8')
    raw=urlopen(BASE+prefix+'/repair-material/'+str(saved['revision']),timeout=120).read()
    with ZipFile(BytesIO(raw)) as archive:
        for name in ('request.json','source-texture.png'):(output/name).write_bytes(archive.read(name))
    print(json.dumps(dict(job=PARENT,revision=saved['revision'])))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('output',type=Path)
    prepare(parser.parse_args().output)
