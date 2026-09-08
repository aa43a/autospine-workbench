"""4.3.26 inspection-only adapter for isolated ownership texture pages."""
from copy import deepcopy
from io import BytesIO
import hashlib
import json
import math
from ...resolved_project import canonical_sha256
from ...asset.joints.partition_pixels import png


def region_uvs(page_uvs,page_size,rect):
    x,y,w,h=rect;pw,ph=page_size
    if min(w,h,pw,ph)<=0:raise ValueError('ownership_preview_rect_invalid')
    result=[]
    for u,v in page_uvs:
        local=[(u*pw-x)/w,(v*ph-y)/h]
        if any(not math.isfinite(a) or not -1e-9<=a<=1+1e-9 for a in local):
            raise ValueError('ownership_preview_uv_invalid')
        result.append([max(0.,min(1.,a)) for a in local])
    return result


def build_preview(atlas,skeleton,pages):
    from PIL import Image
    if atlas.get('schema')!='autospine.ownership-atlas/v1' or canonical_sha256(skeleton)!=atlas['source_skeleton_sha256']:
        raise ValueError('ownership_preview_source_mismatch')
    indices={b['id']:i for i,b in enumerate(skeleton['bones'])};bones=[]
    for b in skeleton['bones']:
        local=b['setup_local'];row={'name':b['id'],'x':local['x'],'y':-local['y'],
            'rotation':-local['rotation_degrees'],'length':b['length']}
        if b['parent_id'] is not None:row['parent']=b['parent_id']
        bones.append(row)
    slots=[];attachments={};tracks={};files={};lines=[];checks=[];residual=[]
    for layer in atlas['layers']:
        if layer['sampler']!={'filter':'linear','mipmaps':False,'wrap':'clamp_to_edge'}:
            raise ValueError('ownership_preview_sampler_unsupported')
        page=pages[layer['page_ref']]
        if hashlib.sha256(page).hexdigest()!=atlas['files'][layer['page_ref']]:raise ValueError('ownership_preview_page_changed')
        pw,ph=layer['page_size'];page_name='textures/'+layer['layer_id']+'.png';files[page_name]=page
        lines.append(f'{page_name}\nsize: {pw},{ph}\nfilter: Linear,Linear\npma: false\nrepeat: none')
        tiles={t['owner_code']:t for t in layer['tiles']}
        with Image.open(BytesIO(page)) as image:
            if image.size!=(pw,ph):raise ValueError('ownership_preview_page_size_invalid')
            for part in layer['partitions']:
                name=part['id'];geo=part['geometry'];rect=tiles[part['tile_owner_code']]['rect'];x,y,w,h=rect
                uv=region_uvs(geo['uvs'],(pw,ph),rect)
                error=max((math.dist(a,b) for a,b in zip(uv,geo['source_uvs'])),default=0.)
                if len(uv)!=len(geo['source_uvs']) or error>1e-9:raise ValueError('ownership_preview_uv_roundtrip_failed')
                vertices=[]
                for influences in geo['weights']:
                    vertices.append(len(influences))
                    for influence in influences:
                        lx,ly=influence['local_xy'];vertices.extend([indices[influence['bone_id']],lx,-ly,influence['weight']])
                slots.append({'name':name,'bone':part['bone_ids'][0],'attachment':name})
                attachments[name]={name:{'type':'mesh','path':name,'uvs':[v for p in uv for v in p],
                    'triangles':[v for tri in geo['triangles'] for v in tri],'vertices':vertices,'width':w,'height':h}}
                lines.append(f'{name}\nbounds: {x},{y},{w},{h}')
                cropped=image.crop((x,y,x+w,y+h));files['editor/images/'+name+'.png']=png('RGBA',(w,h),cropped.tobytes())
                if len(part['bone_ids'])==3:
                    tracks[part['bone_ids'][-1]]={'rotate':[{'time':t,'value':a} for t,a in ((0,0),(.5,30),(1,0),(1.5,-30),(2,0))]}
                checks.append({'id':name,'source_uv_max_error':error,'source_mesh_status':part['status'],
                    'review_status':part['review_status'],'expected_page_uvs':geo['uvs'],'setup_vertices_xy':geo['vertices_xy']})
        lines.append('')
        residual.append({'layer_id':layer['layer_id'],'visible_pixels':layer['residual']['visible_pixels'],'status':'excluded_unbound'})
    if not slots:raise ValueError('ownership_preview_regions_required')
    w,h=skeleton['canvas']
    doc={'skeleton':{'spine':'4.3.26','hash':canonical_sha256(atlas),'images':'./editor/images/',
        'x':0,'y':-h,'width':w,'height':h,'fps':30},'bones':bones,'slots':slots,
        'skins':[{'name':'default','attachments':attachments}],'constraints':[],
        'animations':{'setup':{},'distal-inspection':{'bones':tracks}}}
    encode=lambda d:json.dumps(d,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
    files['skeleton.json']=encode(doc);files['skeleton.atlas']='\n'.join(lines).encode()
    editor=deepcopy(doc);editor['skeleton']['images']='./images/';files['editor/skeleton.json']=encode(editor)
    scope={'schema':'autospine.ownership-target-preview/v1','profile':'spine43-isolated-region-inspection-v1',
        'authority':'none','production_authorized':False,'target':'4.3.26','source_atlas_sha256':canonical_sha256(atlas),
        'source_skeleton_sha256':canonical_sha256(skeleton),'regions':checks,'residuals':residual,
        'scope':'unreviewed_region_sampling_inspection','animation':'raw_lbs_distal_inspection',
        'full_character_status':'blocked','runtime_status':'not_evaluated','seam_status':'not_evaluated',
        'files':{k:hashlib.sha256(v).hexdigest() for k,v in files.items()}}
    return scope,files
