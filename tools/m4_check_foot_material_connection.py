"""Trace frozen overlapping UV probes using official-core-verified world vertices."""
import argparse
import base64
from hashlib import sha256
import json
from pathlib import Path
import numpy as np
from autospine_workbench.resolved_project import canonical_sha256
from m4_pose_material_review import transfer


def mapping(mesh,queries):
    uv=np.asarray(mesh['uvs'],float).reshape(-1,2)
    weights,valid=transfer(uv,np.eye(len(uv)),mesh['triangles'],queries)
    if not valid.all():raise ValueError('foot_material_probe_uncovered')
    return weights


def run(folder,probe_path):
    raw_scene=(folder/'candidate.json').read_bytes();raw_reference=(folder/'active-reference.json').read_bytes()
    core=json.loads((folder/'official-core.json').read_bytes())
    if not core['passed'] or core['input_sha256']!=[sha256(raw_scene).hexdigest(),sha256(raw_reference).hexdigest()]:
        raise ValueError('foot_material_runtime_identity')
    scene=json.loads(raw_scene);document=scene['skeleton'];reference=json.loads(raw_reference)
    receipt=json.loads((folder/'report.json').read_bytes());raw_probes=probe_path.read_bytes();probes=json.loads(raw_probes)
    if (probes['source_sha256']!=receipt['source_sha256'] or
            receipt['output_sha256']!=canonical_sha256(document)):
        raise ValueError('foot_material_source_identity')
    cached={};rows=[]
    for pair in probes['rows']:
        for slot in (pair['leg'],pair['shoe']):
            query=pair['probes'][slot]
            uri=scene['textures']['editor/images/'+query['texture_path']+'.png']
            prefix='data:image/png;base64,'
            if not uri.startswith(prefix) or sha256(base64.b64decode(uri[len(prefix):],validate=True)).hexdigest()!=query['texture_sha256']:
                raise ValueError('foot_material_texture_identity')
        samples=[]
        for frame in reference['frames']:
            positions={}
            for slot in (pair['leg'],pair['shoe']):
                attachment=frame['attachments'][slot]
                mesh=document['skins'][0]['attachments'][slot][attachment]
                query=pair['probes'][slot]
                if mesh.get('path',attachment)!=query['texture_path']:raise ValueError('foot_material_texture_changed')
                key=(slot,attachment)
                if key not in cached:cached[key]=mapping(mesh,query['uv'])
                positions[slot]=cached[key]@np.asarray(frame['vertices'][slot])
            distance=np.linalg.norm(positions[pair['leg']]-positions[pair['shoe']],axis=1)
            if not np.isfinite(distance).all():raise ValueError('foot_material_nonfinite')
            samples.append(dict(time=frame['time'],maximum_px=float(distance.max()),median_px=float(np.median(distance))))
        rows.append(dict(side=pair['side'],probes=pair['probe_count'],peak=max(samples,key=lambda s:s['maximum_px']),samples=samples))
    report=dict(candidate_sha256=receipt['output_sha256'],probe_sha256=sha256(raw_probes).hexdigest(),
        reference_sha256=sha256(raw_reference).hexdigest(),sample_count=len(reference['frames']),rows=rows,
        authority='none',selected=False,scope='shared_setup_material_distance_not_framebuffer_gap_or_ground_contact_acceptance')
    with (folder/'material-connection.json').open('x',encoding='utf-8') as f:json.dump(report,f,indent=2)
    print(json.dumps(dict(samples=report['sample_count'],peaks=[dict(side=r['side'],**r['peak']) for r in rows])))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('folder',type=Path);p.add_argument('probes',type=Path)
    a=p.parse_args();run(a.folder,a.probes)
