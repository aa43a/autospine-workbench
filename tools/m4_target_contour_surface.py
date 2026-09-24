"""Transfer contour-clipped vertices and weights into a separate target surface."""
import argparse
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import numpy as np
from PIL import Image
from m4_alpha_contour_clip import clip
from autospine_workbench.targets.character43.deform_addition import entries
from autospine_workbench.targets.character43.affine_pose import matrices
from autospine_workbench.targets.character43.skirt_candidate import inverse


def run(source,scene,output):
    raw=source.read_bytes();result=json.loads(raw);scene_raw=scene.read_bytes()
    if sha256(scene_raw).hexdigest()!=result['source_sha256']:raise ValueError('contour_scene_changed')
    doc=json.loads(scene_raw)['skeleton'];rest=matrices(dict(doc,animations={'setup':{}}),'setup',0)
    summaries={}
    for key,s in result['surfaces'].items():
        path=Path(s['texture_path'])
        if sha256(path.read_bytes()).hexdigest()!=s['texture_sha256']:raise ValueError('contour_texture_changed')
        alpha=np.asarray(Image.open(path).convert('RGBA'))[:,:,3]
        clipped=clip(s['vertices'],s['uvs'],s['triangles'],alpha)
        coefficients=np.array(clipped.pop('coefficients'));old=entries({'vertices':s['source_weighted_vertices']})
        weights=np.zeros((len(old),len(s['source_bones'])))
        for i,row in enumerate(old):
            for b,w in row:weights[i,b]=w
        interpolated=coefficients@weights;encoded=[]
        for point,row in zip(clipped['vertices'],interpolated):
            ids=np.where(row>0)[0];encoded.append(len(ids))
            for b in ids:
                xy=inverse(rest[s['source_bones'][b]['name']],point[:2])
                encoded.extend([int(b),*xy,float(row[b])])
        s.update(clipped);s['source_weighted_vertices']=encoded;s['profile']='alpha-isoline-clipped-surface-v1'
        summaries[key]={k:s[k] for k in ('contour_rings','alpha_shape_area','clipped_area','outside_source_area')}
        summaries[key].update(vertices=len(s['vertices']),triangles=len(s['triangles']))
    result['parent_surface_sha256']=sha256(raw).hexdigest()
    output.mkdir(parents=True,exist_ok=False)
    (output/'surface.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    (output/'summary.json').write_text(json.dumps(summaries,indent=2),encoding='utf-8');print(json.dumps(summaries))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('source','scene','output'):p.add_argument(key,type=Path)
    a=p.parse_args();run(a.source,a.scene,a.output)
