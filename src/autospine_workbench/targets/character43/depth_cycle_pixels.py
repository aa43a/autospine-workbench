"""Locate simple ordering-cycle constraints in the same sampled alpha raster."""
import math
from .affine_pose import sample
from ..spine43.seam_raster import mask,texture

PROFILE='same-frame-cycle-alpha-support-v1-experiment'


def inventory(cycle):
    slots=cycle['slots']
    if (len(slots)<4 or len(slots)>17 or slots[0]!=slots[-1]
            or len(set(slots[:-1]))!=len(slots)-1):
        raise ValueError('cycle_pixels_simple_cycle_required')
    if [(e['back'],e['front']) for e in cycle['edges']]!=list(zip(slots,slots[1:])):
        raise ValueError('cycle_pixels_edge_inventory')
    return slots[:-1]


def classify(masks):
    import numpy as np
    if len(masks)<3 or any(m.shape!=masks[0].shape or m.dtype!=bool for m in masks):
        raise ValueError('cycle_pixels_mask_inventory')
    common=np.logical_and.reduce(masks)
    counts=[int((a&b).sum()) for a,b in zip(masks,masks[1:]+masks[:1])]
    status=('simultaneous_cycle_support' if common.any() else
            'spatially_distributed_cycle_support' if all(counts) else 'cycle_not_simultaneous_at_sample')
    return dict(status=status,common_pixels=int(common.sum()),edge_overlap_pixels=counts),common


def analyze(document,files,animation,cycle,time,*,pixel_budget=4_000_000):
    import numpy as np
    names=inventory(cycle)
    if not math.isfinite(time) or time<0:raise ValueError('cycle_pixels_time_invalid')
    if document['animations'][animation].get('slots'):raise ValueError('cycle_pixels_attachment_timeline_unsupported')
    slots={s['name']:s for s in document['slots']};meshes={};bounds={}
    positions=sample(document,animation,time)[0]
    for name in names:
        slot=slots[name];mesh=document['skins'][0]['attachments'][name][slot['attachment']]
        if (mesh.get('type')!='mesh' or slot.get('blend','normal')!='normal'
                or slot.get('color','ffffffff')!='ffffffff' or mesh.get('color','ffffffff')!='ffffffff'):
            raise ValueError('cycle_pixels_attachment_unsupported')
        triangles=mesh['triangles']
        if len(triangles)%3 or any(type(i) is not int or not 0<=i<len(positions[name]) for i in triangles):
            raise ValueError('cycle_pixels_triangle_indices')
        points=[positions[name][i] for i in sorted(set(triangles))]
        if not points:raise ValueError('cycle_pixels_empty_mesh')
        bounds[name]=[min(p[0] for p in points),min(-p[1] for p in points),
                      max(p[0] for p in points),max(-p[1] for p in points)]
        meshes[name]=mesh
    overlaps=[]
    for a,b in zip(names,names[1:]+names[:1]):
        aa,bb=bounds[a],bounds[b]
        rect=[max(aa[0],bb[0]),max(aa[1],bb[1]),min(aa[2],bb[2]),min(aa[3],bb[3])]
        if rect[2]>rect[0] and rect[3]>rect[1]:overlaps.append(rect)
    report=dict(profile=PROFILE,time=time,slots=names,edges=cycle['edges'],authority='none',selected=False,
                scope='cpu_alpha8_bilinear_cycle_witness_not_depth_truth_or_runtime_acceptance')
    if not overlaps:return dict(report,status='cycle_not_simultaneous_at_sample',common_pixels=0,edge_overlap_pixels=[0]*len(names)),None
    left=math.floor(min(r[0] for r in overlaps));top=math.floor(min(r[1] for r in overlaps))
    width=math.ceil(max(r[2] for r in overlaps))-left;height=math.ceil(max(r[3] for r in overlaps))-top
    rect=[left,top,width,height];work=width*height*len(names)
    # Bound raster work as well as allocated pixels; count each source triangle.
    triangle_work=width*height*sum(len(meshes[n]['triangles'])//3 for n in names)
    if work>pixel_budget or triangle_work>128_000_000:
        return dict(report,status='unmeasured',reason_code='cycle_pixels_budget',roi=rect,
                    required_pixels=work,triangle_work=triangle_work),None
    masks=[]
    for name in names:
        mesh=meshes[name];raw=files['images/'+mesh.get('path',slots[name]['attachment'])+'.png']
        masks.append(mask(mesh,positions[name],texture(raw),rect)>=8)
    result,common=classify(masks);locations=np.argwhere(common)
    points=[[left+int(x)+.5,-(top+int(y)+.5)] for y,x in locations[:32]]
    bbox=None
    if len(locations):
        yy,xx=locations[:,0],locations[:,1]
        bbox=[left+int(xx.min()),top+int(yy.min()),int(xx.max()-xx.min()+1),int(yy.max()-yy.min()+1)]
    return dict(report,**result,roi=rect,common_world_samples=points,common_samples_truncated=len(locations)>32,
                common_raster_bbox=bbox,sampled_pixels=work,triangle_work=triangle_work),(masks,common)
