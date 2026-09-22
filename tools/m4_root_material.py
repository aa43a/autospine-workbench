"""Experimental proximal source-material attachment; not semantic auto-approval."""
from copy import deepcopy
from hashlib import sha256
from io import BytesIO
import numpy as np
from PIL import Image
from m4_pose_material_review import transfer,alpha_at
from autospine_workbench.targets.character43.affine_pose import sample


def split_texture(image,mask):
    if image.ndim!=3 or image.shape[2]!=4 or mask.shape!=image.shape[:2] or mask.dtype!=bool:
        raise ValueError('root_material_mask_shape')
    h,w=mask.shape;padded=np.pad(mask,1)
    dilated=np.logical_or.reduce([padded[y:y+h,x:x+w] for y in range(3) for x in range(3)])
    # Cover only fully opaque interior samples. Never grow the character silhouette.
    guard=dilated&~mask&(image[:,:,3]==255)
    root_image=image.copy();root_image[~(mask|guard),3]=0
    free_image=image.copy();free_image[mask,3]=0
    return root_image,free_image,int(guard.sum())


def preserve_padding(image,source,page):
    """Apply an alpha-only split to the existing atlas page, including its padding."""
    h,w=source.shape[:2]
    if (image.shape!=source.shape or page.shape!=(h+4,w+4,4)
            or not np.array_equal(page[2:-2,2:-2],source)
            or not np.array_equal(image[:,:,:3],source[:,:,:3])
            or not np.all((image[:,:,3]==0)|(image[:,:,3]==source[:,:,3]))):
        raise ValueError('root_material_page_layout')
    result=page.copy()
    keep=(image[:,:,3]>0)
    result[~np.pad(keep,2,mode='edge'),3]=0
    # Preserve the exact source RGB everywhere, including transparent texels.
    result[2:-2,2:-2]=image
    return result


def partition(document,files,arm,body,root_bone,distal_bone):
    points,pose=sample(dict(document,animations={'setup':{}}),'setup',0)
    root=np.asarray(pose[root_bone][:2]);distal=np.asarray(pose[distal_bone][:2]);length=float(np.linalg.norm(distal-root))
    if length<=0:raise ValueError('root_material_axis')
    attachments=document['skins'][0]['attachments'];a=attachments[arm][arm];b=attachments[body][body]
    source_name='images/'+a.get('path',arm)+'.png';body_name='images/'+b.get('path',body)+'.png'
    image=np.asarray(Image.open(BytesIO(files[source_name])).convert('RGBA'))
    body_alpha=np.asarray(Image.open(BytesIO(files[body_name])).convert('RGBA'))[:,:,3]
    h,w=image.shape[:2];x,y=np.meshgrid(np.arange(w)+.5,np.arange(h)+.5)
    uv=np.column_stack((x.ravel()/w,y.ravel()/h))
    world,covered=transfer(np.asarray(a['uvs']).reshape(-1,2),points[arm],a['triangles'],uv)
    body_uv=np.full_like(world,np.nan)
    body_uv[covered],_=transfer(points[body],np.asarray(b['uvs']).reshape(-1,2),b['triangles'],world[covered])
    hidden=(alpha_at(body_alpha,body_uv)>=254)&(image[:,:,3].ravel()>=8)&covered
    # Same proximal support radius as existing shoulder_source; no whole-sleeve locking.
    near=np.linalg.norm(world-root,axis=1)<=.65*length
    mask=(hidden&near).reshape(h,w)
    if not mask.any():raise ValueError('root_material_support_missing')
    root_image,free_image,guard=split_texture(image,mask)
    return root_image,free_image,dict(profile='setup-opaque-proximal-material-v1',radius_ratio=.65,
        root_bone=root_bone,distal_bone=distal_bone,root_texels=int(mask.sum()),opaque_guard_texels=guard,
        excluded_distant_overlap=int((hidden&~near).sum()),source_texture_sha256=sha256(files[source_name]).hexdigest(),
        body_texture_sha256=sha256(files[body_name]).hexdigest(),authority='none',selected=False)


def apply(candidate,source,files,arm,body,root_bone,distal_bone):
    root_image,free_image,report=partition(source,files,arm,body,root_bone,distal_bone)
    result=deepcopy(candidate);output={};attachments=result['skins'][0]['attachments']
    root_name='m4-root-material';free_name='m4-free-material'
    if root_name in attachments or free_name in attachments:raise ValueError('root_material_collision')
    original=next(s for s in source['slots'] if s['name']==arm)
    root_slot=dict(original,name=root_name,attachment=root_name)
    mesh=source['skins'][0]['attachments'][arm][original['attachment']]
    source_path=mesh.get('path',original['attachment'])
    if arm in attachments:
        selected=[arm,'m4-front-mesh'];start='m4-clip-back'
    else:
        selected=[s['name'] for s in result['slots'] if s['name'].startswith('m4-tri-')
                  and attachments[s['name']][s['attachment']].get('type')=='mesh'
                  and attachments[s['name']][s['attachment']].get('path')==source_path]
        if not selected:raise ValueError('root_material_render_parts_missing')
        start=next(s['name'] for s in result['slots'] if s['name'].startswith('m4-tri-back-') or s['name']==body)
    # Outside the back clipping scope, but still before the torso.
    index=next(i for i,s in enumerate(result['slots']) if s['name']==start)
    result['slots'].insert(index,root_slot)
    attachments[root_name]={root_name:dict(deepcopy(mesh),path=root_name)}
    for name in selected:
        slot=next(s for s in result['slots'] if s['name']==name)
        attachments[name][slot['attachment']]['path']=free_name
    tracks=result['animations']['external-motion']['attachments']['default']
    source_tracks=source['animations']['external-motion'].get('attachments',{}).get('default',{})
    if arm in source_tracks:tracks[root_name]={root_name:deepcopy(source_tracks[arm][original['attachment']])}
    atlas=files['skeleton.atlas'].decode()
    source_image=np.asarray(Image.open(BytesIO(files['images/'+source_path+'.png'])).convert('RGBA'))
    page=np.asarray(Image.open(BytesIO(files['textures/'+source_path+'.png'])).convert('RGBA'))
    h,w=source_image.shape[:2]
    expected=f'textures/{source_path}.png\nsize: {w+4},{h+4}\nfilter: Linear,Linear\npma: false\nrepeat: none\n{source_path}\nbounds: 2,2,{w},{h}'
    if expected not in atlas.replace('\r\n','\n'):raise ValueError('root_material_atlas_layout')
    report.update(atlas_padding='preserved_source_page',source_page_sha256=sha256(files['textures/'+source_path+'.png']).hexdigest(),render_parts=len(selected))
    for name,image in ((root_name,root_image),(free_name,free_image)):
        h,w=image.shape[:2]
        for prefix,array in [('images',image),('editor/images',image),('textures',preserve_padding(image,source_image,page))]:
            buffer=BytesIO();Image.fromarray(array).save(buffer,format='PNG');output[f'{prefix}/{name}.png']=buffer.getvalue()
        atlas+=f'\ntextures/{name}.png\nsize: {w+4},{h+4}\nfilter: Linear,Linear\npma: false\nrepeat: none\n{name}\nbounds: 2,2,{w},{h}\n'
    output['skeleton.atlas']=atlas.encode()
    return result,output,report
