"""Submit a labeled unchanged-artwork regression, then withdraw its draft."""
import argparse
import base64
import json
from pathlib import Path
from m4_material_live_fixture import prepare
from m4_partition_execution_check import request,PARENT


def run(output,selection):
    prepare(output);prefix='/api/motions/'+PARENT
    receipt=request(prefix+'/material-return',dict(request=json.loads((output/'request.json').read_bytes()),
        png_base64=base64.b64encode((output/'source-texture.png').read_bytes()).decode()))
    state=request(prefix+'/material-mapping');mesh=next(r for r in request(prefix+'/view/partition-mesh.json')['rows'] if r['slot']==receipt['slot'])
    saved=request(prefix+'/material-mapping',dict(action='map',expected_revision=state['revision'],
        material_bundle_sha256=receipt['material_bundle_sha256'],mesh_sha256=mesh['mesh_sha256'],triangles=selection,interval=[1,2]))
    try:
        job=request(prefix+'/material-execute',dict(revision=saved['revision'],mapping_sha256=saved['mapping_sha256s'][-1]))
        (output/'execution.json').write_text(json.dumps(job),encoding='utf-8')
        (output/'mapping.json').write_text(json.dumps(saved),encoding='utf-8')
        print(json.dumps(job))
    finally:
        current=request(prefix+'/material-mapping')
        if current['revision']!=saved['revision']:raise ValueError('concurrent_mapping_change_no_withdrawal')
        request(prefix+'/material-mapping',dict(action='withdraw',expected_revision=current['revision'],material_bundle_sha256=receipt['material_bundle_sha256']))
        fixture=json.loads((output/'fixture.json').read_bytes());state=request(prefix+'/repair-draft')
        if state['revision']!=fixture['revision']:raise ValueError('concurrent_draft_change_no_withdrawal')
        request(prefix+'/repair-draft',dict(fixture['body'],expected_revision=state['revision'],action='withdraw'))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('output',type=Path);parser.add_argument('selection',type=Path)
    args=parser.parse_args();old=json.loads(args.selection.read_bytes())
    run(args.output,old['state']['history'][-1]['mapping']['triangles'])
