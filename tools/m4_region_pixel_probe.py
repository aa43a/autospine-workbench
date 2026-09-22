"""Trace explicitly selected screenshot points through candidate mesh and UVs."""
import argparse
from io import BytesIO
import json
from pathlib import Path
import numpy as np
from PIL import Image
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.targets.character43.numeric_reference import read


def run(source, captures, output):
    receipt=json.loads((source/'report.json').read_text(encoding='utf-8'))
    digest=receipt['candidate_bundle_sha256']
    files=AnimatedStore(source/'isolated-store').read(digest)
    doc=json.loads(files['skeleton.json']);samples=read(files)['animations']['external-motion']
    runtime=json.loads((source/'runtime/report.json').read_text(encoding='utf-8'))
    captures_report=json.loads((captures/'report.json').read_text(encoding='utf-8'))
    if runtime['bundle_sha256']!=digest or captures_report['artifact']!=digest:
        raise ValueError('probe_candidate_mismatch')
    info=runtime['info'];time=.9;frame=min(samples,key=lambda f:abs(f['time']-time))
    if abs(frame['time']-time)>1e-6:raise ValueError('probe_missing_same_time')
    rows=[]
    # Explicit locations read from the isolated screenshots, not inferred defect labels.
    for slot,pixel in [('layer-003',(216,489)),('layer-004',(325,477))]:
        image=Image.open(captures/f'{slot}-{time}.png');width,height=image.size
        query=np.array([info['left']+(pixel[0]+.5)/width*info['width'],
                        info['bottom']+(1-(pixel[1]+.5)/height)*info['height']])
        mesh=doc['skins'][0]['attachments'][slot][slot]
        points=np.asarray(frame['vertices'][slot]);uv=np.asarray(mesh['uvs']).reshape(-1,2)
        texture=Image.open(BytesIO(files['images/'+mesh.get('path',slot)+'.png'])).convert('RGBA')
        hits=[];nearest=[]
        for index,ids in enumerate(np.asarray(mesh['triangles']).reshape(-1,3)):
            a,b,c=points[ids];matrix=np.column_stack((b-a,c-a))
            if abs(np.linalg.det(matrix))<1e-12:continue
            weights=np.linalg.solve(matrix,query-a);weights=np.r_[1-weights.sum(),weights]
            if min(weights)>=-1e-8:
                tex=weights@uv[ids];x=min(texture.width-1,max(0,int(tex[0]*texture.width)))
                y=min(texture.height-1,max(0,int(tex[1]*texture.height)))
                hits.append(dict(triangle=index,uv=tex.tolist(),source_pixel=[x,y],rgba=list(texture.getpixel((x,y)))))
            nearest.append((float(np.linalg.norm(points[ids].mean(axis=0)-query)),index))
        rows.append(dict(slot=slot,screenshot_pixel=pixel,screenshot_size=[width,height],world=query.tolist(),
                         hits=hits,nearest_centroid_triangles=[i for _,i in sorted(nearest)[:5]],
                         classification='mesh_uncovered' if not hits else 'covered_check_texture_alpha'))
    output.parent.mkdir(parents=True,exist_ok=True)
    report=dict(candidate=digest,time=time,sampled_time=frame['time'],rows=rows,authority='none',selected=False,
                scope='two_manually_localized_pixel_centers_nearest_texture_sample_not_whole_region_proof')
    output.write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('source',type=Path);parser.add_argument('captures',type=Path)
    parser.add_argument('output',type=Path);args=parser.parse_args();run(args.source,args.captures,args.output)
