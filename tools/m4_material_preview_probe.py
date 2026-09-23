"""Read-only real candidate fixture; no draft or acceptance is written."""
import json
from pathlib import Path
import sys
from urllib.request import urlopen
from autospine_workbench.automation.motion_material_preview import build

base,job,destination=sys.argv[1:]
def read(parts):
    with urlopen(base+'/api/motions/'+job+'/view/'+'/'.join(parts),timeout=120) as response:
        return response.read(),response.headers.get('Content-Type')
report=json.loads(read(['geometry-details.json'])[0])
record=next(r for r in report['rows'] if r['details'])
row=dict(artifact_sha256=report['artifact_sha256'],slot=record['slot'],animation=record['animation'],event=record['details'][0])
output=Path(destination);output.mkdir(parents=True,exist_ok=True)
(output/'pose-preview.html').write_bytes(build(read,row))
(output/'event.json').write_text(json.dumps(row),encoding='utf-8')
print(json.dumps(dict(artifact=row['artifact_sha256'],slot=row['slot'],time=row['event']['time'])))
