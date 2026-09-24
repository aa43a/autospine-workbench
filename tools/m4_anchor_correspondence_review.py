"""Locate rejected anchor pairs on unchanged source textures and exact source poses."""
import argparse
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path

import numpy as np
from PIL import Image
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.targets.character43.affine_pose import sample
from m4_pose_material_review import transfer


def run(report_path, source_root, output):
    raw=report_path.read_bytes(); report=json.loads(raw); rows=[]
    output.mkdir(parents=True,exist_ok=False)
    for index,row in enumerate(report['records']):
        source=source_root/str(index)
        receipt=json.loads((source/'report.json').read_bytes())
        if receipt['candidate_bundle_sha256']!=row['artifact_sha256']:
            raise ValueError('anchor_review_source_changed')
        files=AnimatedStore(source/'isolated-store').read(row['artifact_sha256'])
        doc=json.loads(files['skeleton.json']); arm,body=row['arm'],row['body']
        meshes=doc['skins'][0]['attachments']; am,bm=meshes[arm][arm],meshes[body][body]
        setup=sample(dict(doc,animations={'setup':{}}),'setup',0)[0]
        ids=row['anchors']; auv=np.asarray(am['uvs']).reshape(-1,2)[ids]
        buv,valid=transfer(setup[body],np.asarray(bm['uvs']).reshape(-1,2),bm['triangles'],np.asarray(setup[arm])[ids])
        if not valid.all():raise ValueError('anchor_review_missing_correspondence')
        textures=[]
        for slot,mesh,uv in ((arm,am,auv),(body,bm,buv)):
            data=files['images/'+mesh.get('path',slot)+'.png']
            size=Image.open(BytesIO(data)).size; filename=f'{index}-{slot}.png'
            (output/filename).write_bytes(data)
            textures.append(dict(url=filename,width=size[0],height=size[1],sha256=sha256(data).hexdigest(),
                                 points=(uv*np.asarray(size)).tolist()))
        frames=[]
        for record in row['records']:
            time=record['time']; world=sample(doc,'external-motion',time)[0]
            target,ok=transfer(setup[body],world[body],bm['triangles'],np.asarray(setup[arm])[ids])
            if not ok.all():raise ValueError('anchor_review_missing_pose')
            frames.append(dict(time=time,arm=np.asarray(world[arm])[ids].tolist(),target=target.tolist(),
                               gap=np.linalg.norm(np.asarray(world[arm])[ids]-target,axis=1).tolist()))
        rows.append(dict(character=row['character'],artifact=row['artifact_sha256'],anchors=ids,textures=textures,frames=frames))
    data=dict(report_sha256=sha256(raw).hexdigest(),rows=rows,authority='none',selected=False)
    (output/'data.json').write_text(json.dumps(data,indent=2),encoding='utf8')
    template=Path(__file__).with_name('m4_anchor_correspondence_review.html').read_text(encoding='utf8')
    (output/'index.html').write_text(template.replace('/*DATA*/',json.dumps(data).replace('<','\\u003c')),encoding='utf8')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('report','sources','output'):parser.add_argument(name,type=Path)
    args=parser.parse_args();run(args.report,args.sources,args.output)
