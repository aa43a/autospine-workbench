"""Create a separate volume hypothesis retaining original material provenance."""
import argparse
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from autospine_workbench.targets.character43.closed_surface_shell import build


def run(source,output):
    raw=source.read_bytes();document=json.loads(raw);result=deepcopy(document)
    for slot,s in result['surfaces'].items():
        # Measured maximum alpha-supported inscribed radius, not a fitted repair parameter.
        thickness=s['maximum_depth']/s['depth_ratio']
        shell=build(s['vertices'],s['triangles'],thickness);n=len(s['vertices'])
        s.update(shell);s['uvs']+= [[0.,0.]]*n
        s['source_weighted_vertices']*=2
        s['uv_valid_for_material']=[True]*n+[False]*n
        s['profile']='closed-extruded-target-surface-hypothesis-v1'
    result['parent_surface_sha256']=sha256(raw).hexdigest()
    output.mkdir(parents=True,exist_ok=False)
    (output/'surface.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({k:{'vertices':len(s['vertices']),'triangles':len(s['triangles']),
                         'boundary_edges':s['boundary_edges'],'thickness':s['thickness']}
                      for k,s in result['surfaces'].items()}))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('source','output'):p.add_argument(name,type=Path)
    a=p.parse_args();run(a.source,a.output)
