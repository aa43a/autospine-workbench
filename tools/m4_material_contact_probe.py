"""Diagnostic lower shoe material probes, not semantic sole or contact labels."""
import argparse
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import numpy as np
from PIL import Image
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.resolved_project import canonical_sha256
from autospine_workbench.targets.character43.active_mesh_pose import sample_active
from autospine_workbench.targets.character43.deform_addition import entries
from autospine_workbench.targets.character43.material_contact_trace import trace
from autospine_workbench.targets.character43.numeric_reference import read
from m4_pose_material_review import transfer


def run(store,artifact,output,limit):
    files=AnimatedStore(store).read(artifact);doc=json.loads(files['skeleton.json'])
    reference=read(files)
    if reference['skeleton_sha256']!=sha256(files['skeleton.json']).hexdigest():
        raise ValueError('material_probe_source_mismatch')
    animation='external-motion';times=[f['time'] for f in reference['animations'][animation]]
    setup=sample_active(dict(doc,animations={'setup':{}}),'setup',0);anchors=[]
    for slot,name in setup['attachments'].items():
        if name is None:continue
        mesh=doc['skins'][0]['attachments'][slot][name]
        bones={doc['bones'][i]['name'] for row in entries(mesh) for i,w in row if w>0}
        if bones not in ({'foot_l'},{'foot_r'}):continue
        path='images/'+mesh.get('path',name)+'.png';raw=files[path]
        alpha=np.asarray(Image.open(BytesIO(raw)).convert('RGBA'))[:,:,3]
        yy,xx=np.nonzero(alpha>=254)
        uv=np.column_stack(((xx+.5)/alpha.shape[1],(yy+.5)/alpha.shape[0]))
        points,valid=transfer(np.asarray(mesh['uvs']).reshape(-1,2),setup['vertices'][slot],mesh['triangles'],uv)
        if not valid.any():continue
        bottom=np.flatnonzero(valid & (points[:,1]<=np.min(points[valid,1])+1.))
        ordered=bottom[np.argsort(points[bottom,0])]
        for n,i in enumerate(sorted(set([int(ordered[0]),int(ordered[len(ordered)//2]),int(ordered[-1])]))):
            anchors.append(dict(id=f'{slot}-{n}',slot=slot,uv=uv[i].tolist(),texture_path=path,
                                texture_sha256=sha256(raw).hexdigest()))
    if not anchors:raise ValueError('material_probe_no_pure_foot_mesh')
    request=dict(document_sha256=canonical_sha256(doc),animation=animation,interval=[times[0],times[-1]],
                 times=times,limit_px=limit,anchors=anchors)
    report=trace(doc,files,request)
    report.update(artifact_sha256=artifact,skeleton_byte_sha256=sha256(files['skeleton.json']).hexdigest(),request=request,
                  selection='automatic_opaque_setup_lower_edge_not_reviewed_sole',
                  interval_source='capture_span_not_source_contact_marker')
    with output.open('x',encoding='utf8') as f:json.dump(report,f,indent=2)
    print(json.dumps(dict(passed=report['passed'],anchors=len(anchors),samples=len(times),
        rows=[dict(id=r['id'],drift=r['maximum_drift_px'],unresolved=r['unresolved_samples']) for r in report['records']])))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('store',type=Path);parser.add_argument('artifact');parser.add_argument('output',type=Path)
    parser.add_argument('--limit-px',required=True,type=float)
    args=parser.parse_args();run(args.store,args.artifact,args.output,args.limit_px)
