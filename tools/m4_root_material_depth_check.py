"""Compare visible connection-material texels with replayed depth, not visibility."""
import argparse
import base64
from copy import deepcopy
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path

import numpy as np
from PIL import Image

from autospine_workbench.targets.character43.affine_pose import sample


def body_overlap(scene, body, frame, mappings, count):
    """CPU texel-center overlap only; no GPU filtering or surface-depth claim."""
    document=deepcopy(scene['skeleton'])
    attachment=document['skins'][0]['attachments'][body][body]
    document['skins'][0]['attachments']={body:{body:attachment}}
    vertices=np.asarray(sample(document,'external-motion',frame['time'])[0][body])
    world=np.full((count,2),np.nan)
    for triangle,indices,bary in mappings:
        world[indices]=bary @ np.asarray(frame['vertices'])[triangle]
    texture=scene['textures']['images/'+attachment.get('path',body)+'.png']
    alpha=np.asarray(Image.open(BytesIO(base64.b64decode(texture.split(',',1)[1]))).convert('RGBA'))[:,:,3]
    height,width=alpha.shape;uv=np.asarray(attachment['uvs']).reshape(-1,2)
    covered=np.zeros(count,dtype=bool)
    for triangle in np.asarray(attachment['triangles']).reshape(-1,3):
        a,b,c=vertices[triangle];matrix=np.column_stack((b-a,c-a))
        if abs(np.linalg.det(matrix))<1e-12:continue
        weights=(world-a) @ np.linalg.inv(matrix).T
        bary=np.column_stack((1-weights.sum(axis=1),weights))
        indices=np.flatnonzero((bary>=-1e-9).all(axis=1))
        coords=bary[indices] @ uv[triangle]
        x=np.clip((coords[:,0]*width).astype(int),0,width-1)
        y=np.clip((coords[:,1]*height).astype(int),0,height-1)
        covered[indices] |= alpha[y,x]>=8
    return covered


def inspect(folder, field_path, overlap=False):
    field_raw = field_path.read_bytes()
    field = json.loads(field_raw)
    receipt = json.loads((folder/'report.json').read_bytes())
    scene_raw = (folder/'after/runtime/player-assets/scene.json').read_bytes()
    scene = json.loads(scene_raw)
    if field['candidate'] != receipt['parent'] or scene['artifact_sha256'] != receipt['candidate']:
        raise ValueError('candidate_identity_mismatch')
    before = json.loads((folder/'before/runtime/player-assets/scene.json').read_bytes())
    if before['artifact_sha256'] != field['candidate']:
        raise ValueError('parent_identity_mismatch')
    source = before['skeleton']['skins'][0]['attachments'][field['arm']][field['arm']]
    attachment = scene['skeleton']['skins'][0]['attachments']['m4-root-material']['m4-root-material']
    if any(attachment[k] != source[k] for k in ('uvs','triangles','vertices')):
        raise ValueError('material_mesh_mapping_changed')
    slots = [s['name'] for s in scene['skeleton']['slots']]
    if slots.index('m4-root-material') >= slots.index(field['body']):
        raise ValueError('expected_behind_body')
    raw = base64.b64decode(scene['textures']['images/m4-root-material.png'].split(',',1)[1])
    alpha = np.asarray(Image.open(BytesIO(raw)).convert('RGBA'))[:,:,3]
    height,width = alpha.shape
    yy,xx = np.nonzero(alpha>=8)
    points = np.column_stack(((xx+.5)/width,(yy+.5)/height))
    uv = np.asarray(source['uvs']).reshape(-1,2)
    mappings = []
    covered = np.zeros(len(points),dtype=bool)
    for triangle in np.asarray(source['triangles']).reshape(-1,3):
        a,b,c = uv[triangle]
        matrix = np.column_stack((b-a,c-a))
        if abs(np.linalg.det(matrix)) < 1e-12:
            continue
        weights = (points-a) @ np.linalg.inv(matrix).T
        bary = np.column_stack((1-weights.sum(axis=1),weights))
        indices = np.flatnonzero((bary>=-1e-9).all(axis=1))
        if len(indices):
            mappings.append((triangle,indices,bary[indices]))
            covered[indices] = True
    rows = []
    for frame in field['rows']:
        depth = np.array([np.nan if v is None else v for v in frame['depth_values']])
        low = np.full(len(points),np.inf); high = np.full(len(points),-np.inf)
        unknown = ~covered.copy()
        for triangle,indices,bary in mappings:
            values = depth[triangle]
            if not np.isfinite(values).all():
                unknown[indices] = True
                continue
            interpolated = bary @ values
            np.minimum.at(low,indices,interpolated)
            np.maximum.at(high,indices,interpolated)
        known = ~unknown & np.isfinite(low) & np.isfinite(high)
        front = known & (low>0)
        back = known & (high<=0)
        mixed = known & ~(front|back)
        count = dict(front_proxy_texels=int(front.sum()),back_or_margin_texels=int(back.sum()),
                     conflicting_uv_texels=int(mixed.sum()),unknown_texels=int((~known).sum()))
        assert sum(count.values()) == len(points)
        if overlap:
            body=body_overlap(before,field['body'],frame,mappings,len(points))
            count['body_overlap_texels']=int(body.sum())
            count['front_proxy_body_overlap_texels']=int((body&front).sum())
        rows.append(dict(time=frame['time'],**count))
    return dict(candidate=receipt['candidate'],parent=receipt['parent'],
                scene_sha256=sha256(scene_raw).hexdigest(),field_sha256=sha256(field_raw).hexdigest(),
                texture_sha256=sha256(raw).hexdigest(),visible_material_texels=len(points),
                unmapped_texels=int((~covered).sum()),rows=rows,authority='none',selected=False,
                body_overlap_sampling='CPU_nearest_alpha8_texel_centers' if overlap else 'not_evaluated',
                scope='UV_texel_centers_against_depth_proxy_with_optional_CPU_overlap_not_GPU_visibility',
                limitations=['does_not_validate_replayed_depth_model','does_not_measure_actual_body_surface',
                             'front_evidence_is_not_proof_of_visible_occlusion_error'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('folder','field','output'):
        parser.add_argument(key,type=Path)
    parser.add_argument('--body-overlap',action='store_true')
    args = parser.parse_args()
    result = inspect(args.folder,args.field,args.body_overlap)
    with args.output.open('x',encoding='utf8') as stream:
        json.dump(result,stream,ensure_ascii=False,allow_nan=False,indent=2)
    print(json.dumps(dict(candidate=result['candidate'],texels=result['visible_material_texels'],
                         frames=len(result['rows']),max_front=max(r['front_proxy_texels'] for r in result['rows']),
                         max_unknown=max(r['unknown_texels'] for r in result['rows']))))
