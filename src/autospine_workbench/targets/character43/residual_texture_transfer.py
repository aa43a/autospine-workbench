"""Conservative texture-only trial; keep every untransferred residual pixel."""
from copy import deepcopy
from hashlib import sha256
from io import BytesIO
import json
import math
from ...automation.storage_io import canonical_bytes
from .affine_pose import sample
from .residual_mesh_support import inspect, inside


def build(files):
    from PIL import Image
    support=inspect(files);doc=json.loads(files['skeleton.json'])
    manifest=json.loads(files['character-manifest.json']);attachments=doc['skins'][0]['attachments']
    animation=next(iter(doc['animations']));positions,_=sample(dict(doc,animations={animation:{}}),animation,0)
    result=dict(files);images={};changes=[];rows=[]
    def image(name):
        path='images/'+attachments[name][name].get('path',name)+'.png'
        if path not in images:
            with Image.open(BytesIO(files[path])) as loaded:images[path]=loaded.convert('RGBA')
        return path,images[path]
    for row in support['rows']:
        source,rgba=image(row['region_id']);width,height=rgba.size
        quad=positions[row['region_id']];origin=quad[0]
        def point(x,y):
            return [origin[k]+x/width*(quad[1][k]-origin[k])+y/height*(quad[3][k]-origin[k]) for k in (0,1)]
        counts={};transferred=[];cache={}
        for pixel in row['records']:
            reason=pixel['state'];x,y=pixel['pixel_xy']
            if pixel['alpha']>=8:reason='non_edge_alpha_requires_review'
            elif reason=='unique_mesh_support':
                mesh=pixel['mesh_regions'][0]
                if mesh not in cache:
                    target,destination=image(mesh);attachment=attachments[mesh][mesh]
                    uvs=attachment['uvs'];points=positions[mesh];flat=attachment['triangles']
                    aligned=destination.size==rgba.size and all(math.dist(p,point(uvs[2*i]*width,uvs[2*i+1]*height))<=1e-6 for i,p in enumerate(points))
                    ts=[[points[i] for i in flat[j:j+3]] for j in range(0,len(flat),3)]
                    cache[mesh]=(target,destination,aligned,ts)
                target,destination,aligned,triangles=cache[mesh]
                # One triangle must contain the full texel; otherwise retain it.
                corners=[point(x+dx,y+dy) for dx,dy in ((0,0),(1,0),(1,1),(0,1))]
                if not aligned:reason='uv_alignment_required'
                elif not any(all(inside(p,*t) for p in corners) for t in triangles):reason='full_pixel_coverage_required'
                elif destination.getpixel((x,y))[3]:reason='target_alpha_collision'
                else:
                    color=rgba.getpixel((x,y));destination.putpixel((x,y),color)
                    rgba.putpixel((x,y),color[:3]+(0,));reason='transferred'
                    transferred.append(dict(pixel_xy=[x,y],target_region=mesh,rgba=list(color)))
            counts[reason]=counts.get(reason,0)+1
        rows.append(dict(layer_id=row['layer_id'],region_id=row['region_id'],counts=counts,transferred=transferred))
    for path,rgba in images.items():
        with Image.open(BytesIO(files[path])) as original:
            if original.convert('RGBA').tobytes()==rgba.tobytes():continue
        stream=BytesIO();rgba.save(stream,format='PNG');raw=stream.getvalue();result[path]=raw
        alias='editor/'+path
        if alias in files:
            if files[alias]!=files[path]:raise ValueError('residual_editor_texture_mismatch')
            result[alias]=raw
        changes.append(dict(path=path,before_sha256=sha256(files[path]).hexdigest(),after_sha256=sha256(raw).hexdigest()))
    report=dict(schema='autospine.residual-texture-transfer/v1',authority='none',selected=False,
                source_skeleton_sha256=support['skeleton_sha256'],source_manifest_sha256=support['manifest_sha256'],
                rows=rows,texture_changes=changes,skeleton_unchanged=True,atlas_layout_unchanged=True,
                limitation='aligned_texels_preserved_filtering_draw_order_and_motion_require_runtime_validation')
    # The old inventory described different textures; this is a separate trial.
    trial=deepcopy(manifest);trial.update(schema='autospine.character-residual-transfer-trial/v1',
        source_manifest_sha256=support['manifest_sha256'],authority='none',production_authorized=False)
    result.pop('character-manifest.json');result['residual-transfer.json']=canonical_bytes(report)
    trial['files']={name:sha256(raw).hexdigest() for name,raw in result.items()}
    result['character-manifest.json']=canonical_bytes(trial)
    return result,report
