"""Read-only screenshot pixel provenance through same-frame mesh and source UV."""
import argparse
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import numpy as np
from PIL import Image
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.targets.character43.numeric_reference import read
from autospine_workbench.automation.storage_io import canonical_bytes


def run(source,index,pixels,output):
    if output.exists():raise ValueError('framebuffer_trace_output_exists')
    receipt=json.loads((source/'report.json').read_bytes());digest=receipt['candidate_bundle_sha256']
    files=AnimatedStore(source/'isolated-store').read(digest)
    runtime=json.loads((source/'runtime/report.json').read_bytes())
    if runtime['bundle_sha256']!=digest:raise ValueError('framebuffer_trace_identity')
    frame=runtime['results'][index];name=frame['animation']
    reference=read(files)['animations'][name][index]
    if reference['time']!=frame['time']:raise ValueError('framebuffer_trace_time')
    shot=next(s for s in runtime['screenshots'] if s['index']==index and s['animation']==name)
    raw=(source/'runtime'/shot['file']).read_bytes()
    if sha256(raw).hexdigest()!=shot['sha256']:raise ValueError('framebuffer_trace_image')
    image=Image.open(BytesIO(raw)).convert('RGBA');doc=json.loads(files['skeleton.json']);info=runtime['info']
    output_rows=[]
    for x,y in pixels:
        if not 0<=x<image.width or not 0<=y<image.height:raise ValueError('framebuffer_trace_pixel_bounds')
        world=np.asarray([info['left']+(x+.5)*info['width']/image.width,
                          info['bottom']+(1-(y+.5)/image.height)*info['height']]);hits=[]
        for slot in frame['draw_order']:
            mesh=doc['skins'][0]['attachments'][slot][slot]
            points=np.asarray(reference['vertices'][slot]);uv=np.asarray(mesh['uvs']).reshape(-1,2)
            texture_path='images/'+mesh.get('path',slot)+'.png'
            if texture_path not in files:raise ValueError('framebuffer_trace_source_texture_missing')
            texture=Image.open(BytesIO(files[texture_path])).convert('RGBA')
            for triangle,ids in enumerate(np.asarray(mesh['triangles']).reshape(-1,3)):
                a,b,c=points[ids];matrix=np.column_stack((b-a,c-a))
                if abs(np.linalg.det(matrix))<1e-12:continue
                w=np.linalg.solve(matrix,world-a);weights=np.r_[1-w.sum(),w]
                if min(weights)<-1e-8:continue
                tex=weights@uv[ids];tx=tex[0]*texture.width-.5;ty=tex[1]*texture.height-.5
                sx,sy=int(np.floor(tx)),int(np.floor(ty));fx,fy=tx-sx,ty-sy
                rgba=np.zeros(4);neighbors=[]
                for dx,dy,weight in ((0,0,(1-fx)*(1-fy)),(1,0,fx*(1-fy)),(0,1,(1-fx)*fy),(1,1,fx*fy)):
                    px=min(texture.width-1,max(0,sx+dx));py=min(texture.height-1,max(0,sy+dy))
                    color=texture.getpixel((px,py));rgba+=weight*np.asarray(color)
                    neighbors.append(dict(pixel=[px,py],rgba=list(color),weight=float(weight)))
                hits.append(dict(slot=slot,triangle=triangle,uv=tex.tolist(),source_texture=texture_path,
                    source_sha256=sha256(files[texture_path]).hexdigest(),bilinear_source_rgba=rgba.tolist(),neighbors=neighbors))
        pixel=list(image.getpixel((x,y)));alpha=pixel[3]/255
        output_rows.append(dict(pixel=[x,y],framebuffer_rgba=pixel,world=world.tolist(),hits=hits,
            display_over_dark=[round(v*alpha+32*(1-alpha),3) for v in pixel[:3]],
            display_over_white=[round(v*alpha+255*(1-alpha),3) for v in pixel[:3]]))
    result=dict(candidate_bundle_sha256=digest,skeleton_sha256=sha256(files['skeleton.json']).hexdigest(),
        time=frame['time'],screenshot_sha256=shot['sha256'],image_size=list(image.size),rows=output_rows,
        scope='explicit_pixel_centers_ideal_mesh_source_bilinear_not_whole_region_or_gpu_sampling_proof',
        authority='none',selected=False)
    output.write_bytes(canonical_bytes(result))
    print(json.dumps(dict(time=frame['time'],rows=[dict(pixel=r['pixel'],rgba=r['framebuffer_rgba'],
        visible_sources=[dict(slot=h['slot'],alpha=h['bilinear_source_rgba'][3]) for h in r['hits'] if h['bilinear_source_rgba'][3]>0],
        dark=r['display_over_dark']) for r in output_rows])),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('source',type=Path);p.add_argument('output',type=Path)
    p.add_argument('--frame',type=int,required=True);p.add_argument('--pixel',action='append',required=True)
    a=p.parse_args();run(a.source,a.frame,[tuple(map(int,s.split(','))) for s in a.pixel],a.output)
