"""Exact alpha back-projection candidates over the already manually cleaned target."""
from copy import deepcopy
from hashlib import sha256
from .wing_split_draft import initial as stroke_initial,validate as validate_strokes,rasterize
from ..asset.planning.wing_edge_ownership import decode
from ..resolved_project import canonical_sha256


def build(source,files,edge):
    if source['schema']!='autospine.wing-split-preview/v1' or source['production_authorized'] is not False or source['authority']!='none':raise ValueError('projection_source')
    if canonical_sha256(edge)!=source['source_edge_preview_sha256']:raise ValueError('projection_edge_identity')
    if set(files)!=set(source['files']) or any(sha256(files[n]).hexdigest()!=d for n,d in source['files'].items()):raise ValueError('projection_files')
    regions={r['id']:r for r in source['regions']};target=decode(files['editor/images/topwear.png'])
    tx,ty=regions['topwear']['setup_vertices_xy'][0];groups=[]
    for name in sorted(n for n in regions if n.startswith('wing-c')):
        image=decode(files['editor/images/'+name+'.png']);ox,oy=regions[name]['setup_vertices_xy'][0]
        spans=[];count=0
        for y in range(target.height):
            start=None
            for x in range(target.width+1):
                u,v=x+tx-ox,y+ty-oy
                included=x<target.width and 0<=u<image.width and 0<=v<image.height and target.getpixel((x,y))[3]>0 and image.getpixel((u,v))[3]>=8
                if included and start is None:start=x
                if not included and start is not None:spans.append([y,start,x]);count+=x-start;start=None
        groups.append(dict(id=name,pixel_count=count,spans=spans,reason_code='projected_overlap_not_semantic_ownership'))
    return dict(schema='autospine.wing-projection-groups/v1',profile='exact-alpha-backprojection-v1',
      source_preview_sha256=canonical_sha256(source),source_split_draft_sha256=source['source_split_draft_sha256'],
      target_image_sha256=sha256(files['editor/images/topwear.png']).hexdigest(),canvas=list(target.size),
      stroke_template=stroke_initial(edge),groups=groups,authority='none',production_authorized=False)


def initial(candidate):
    return dict(schema='autospine.wing-projection-draft/v1',source_candidate_sha256=canonical_sha256(candidate),
      source_split_draft_sha256=candidate['source_split_draft_sha256'],
      choices=[dict(id=g['id'],action='uncertain') for g in candidate['groups']],local_strokes=[],authority='none',production_authorized=False)


def validate(candidate,edge,doc):
    base=initial(candidate)
    if type(doc) is not dict or set(doc)!=set(base) or doc.get('production_authorized') is not False:raise ValueError('projection_draft_identity')
    if any(doc[k]!=base[k] for k in base if k not in ('choices','local_strokes')):raise ValueError('projection_draft_identity')
    if type(doc['choices']) is not list or len(doc['choices'])!=len(base['choices']):raise ValueError('projection_choices')
    for row,expected in zip(doc['choices'],base['choices']):
        if type(row) is not dict or set(row)!={'id','action'} or row['id']!=expected['id'] or row['action'] not in ('remove','keep','uncertain'):raise ValueError('projection_choices')
    if canonical_sha256(edge)!=candidate['stroke_template']['source_preview_sha256']:raise ValueError('projection_stroke_source')
    validate_strokes(edge,dict(candidate['stroke_template'],strokes=doc['local_strokes']))
    return deepcopy(doc)


def effective_mask(candidate,edge,doc):
    doc=validate(candidate,edge,doc);w,h=candidate['canvas'];remove=bytearray(w*h);veto=bytearray(w*h)
    for group,choice in zip(candidate['groups'],doc['choices']):
        target=remove if choice['action']=='remove' else veto
        for y,a,b in group['spans']:
            for x in range(a,b):target[y*w+x]=1
    local=rasterize(edge,dict(candidate['stroke_template'],strokes=doc['local_strokes']))
    return bytes(1 if value==1 or (value==0 and remove[i] and not veto[i]) else 0 for i,value in enumerate(local))
