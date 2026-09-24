"""Save target rest geometry with explicit hypothetical depth and original material."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
from PIL import Image
import numpy as np
from autospine_workbench.targets.character43.active_mesh_pose import sample_active
from autospine_workbench.targets.character43.alpha_surface import build


def run(source, images, output):
    raw = source.read_bytes(); scene = json.loads(raw); doc = scene['skeleton']
    setup = sample_active(dict(doc, animations={'setup':{}}),'setup',0)
    result = dict(source_sha256=sha256(raw).hexdigest(), accepted=False, surfaces={})
    for slot in ('layer-003','layer-004'):
        name = setup['attachments'][slot]
        mesh = doc['skins'][0]['attachments'][slot][name]
        path = images/(mesh.get('path',name)+'.png'); texture = path.read_bytes()
        alpha = np.asarray(Image.open(path).convert('RGBA'))[:,:,3]
        surface = build(setup['vertices'][slot],np.array(mesh['uvs']).reshape(-1,2),
                        np.array(mesh['triangles']).reshape(-1,3),alpha)
        surface.update(texture_path=str(path.resolve()),texture_sha256=sha256(texture).hexdigest(),
                       source_attachment=name, source_weighted_vertices=mesh['vertices'],
                       source_bones=doc['bones'])
        result['surfaces'][slot] = surface
    output.mkdir(parents=True,exist_ok=False)
    (output/'surface.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({s:{'vertices':len(v['vertices']),'triangles':len(v['triangles']),
                        'maximum_depth':v['maximum_depth'],'setup_error':v['setup_affine_residual']}
                      for s,v in result['surfaces'].items()}))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for key in ('source','images','output'): p.add_argument(key,type=Path)
    a = p.parse_args(); run(a.source,a.images,a.output)
