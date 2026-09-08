"""Source-bound tri-state painting draft; raster semantics shared with the editor."""
from copy import deepcopy
import math
from ..resolved_project import canonical_sha256


def initial(source):
    if source['schema']!='autospine.wing-edge-preview/v1' or source['authority']!='none' or source['production_authorized'] is not False:
        raise ValueError('wing_split_source')
    region=next(r for r in source['regions'] if r['id']=='topwear');points=region['setup_vertices_xy']
    size=[points[2][0]-points[0][0],points[2][1]-points[0][1]]
    if any(type(n) is not int or n<=0 for n in size) or size[0]*size[1]>8_000_000:raise ValueError('wing_split_canvas')
    return dict(schema='autospine.wing-split-draft/v1',source_preview_sha256=canonical_sha256(source),
      target_image_sha256=source['files']['editor/images/topwear.png'],canvas=size,
      profile='integer-disc-tristate-v1',strokes=[],authority='none',production_authorized=False)


def validate(source,doc):
    base=initial(source)
    if type(doc) is not dict or set(doc)!=set(base) or doc.get('production_authorized') is not False:
        raise ValueError('wing_split_draft_identity')
    if any(doc[k]!=base[k] for k in base if k!='strokes'):raise ValueError('wing_split_draft_identity')
    if any(type(v) is not int for v in doc['canvas']):raise ValueError('wing_split_canvas')
    strokes=doc['strokes'];total=0
    if type(strokes) is not list or len(strokes)>500:raise ValueError('wing_split_budget')
    for stroke in strokes:
        if type(stroke) is not dict or set(stroke)!={'mode','radius','points'}:raise ValueError('wing_split_stroke')
        if stroke['mode'] not in ('remove','keep','erase') or type(stroke['radius']) is not int or not 1<=stroke['radius']<=64:
            raise ValueError('wing_split_brush')
        if type(stroke['points']) is not list or not stroke['points']:raise ValueError('wing_split_points')
        total+=len(stroke['points'])
        if total>4096:raise ValueError('wing_split_budget')
        for point in stroke['points']:
            if type(point) is not list or len(point)!=2 or any(type(v) is not int or not 0<=v<bound for v,bound in zip(point,base['canvas'])):
                raise ValueError('wing_split_point')
    return deepcopy(doc)


def rasterize(source,doc):
    doc=validate(source,doc);w,h=doc['canvas'];mask=bytearray(w*h)
    for stroke in doc['strokes']:
        radius=stroke['radius'];value={'erase':0,'remove':1,'keep':2}[stroke['mode']]
        def stamp(cx,cy):
            for y in range(max(0,cy-radius),min(h,cy+radius+1)):
                for x in range(max(0,cx-radius),min(w,cx+radius+1)):
                    if (x-cx)**2+(y-cy)**2<=radius**2:mask[y*w+x]=value
        previous=stroke['points'][0];stamp(*previous)
        for point in stroke['points'][1:]:
            steps=max(abs(point[0]-previous[0]),abs(point[1]-previous[1]))
            for i in range(1,steps+1):
                stamp(*(math.floor(a+(b-a)*i/steps+.5) for a,b in zip(previous,point)))
            previous=point
    return bytes(mask)
