"""Compare two candidates on one world-pixel lattice and one corridor per time."""
from io import BytesIO
import math
from .continuous_pose import world
from .alpha_seam import position
from .seam_raster import mask,corridor,texture


def compare_frame(before,after,relation,boundaries,textures,time):
    import numpy as np
    docs=[before,after];poses=[world(d,time) for d in docs];a,b=relation['driver'],relation['follower']
    pairs=[[(position(boundaries[a]['samples'][p['driver_sample']],pose[a]),position(boundaries[b]['samples'][p['follower_sample']],pose[b])) for p in relation['pairs']] for pose in poses]
    points=[p for sample in pairs for pair in sample for p in pair]
    x=math.floor(min(p[0] for p in points))-4;y=math.floor(min(-p[1] for p in points))-4
    rect=[x,y,math.ceil(max(p[0] for p in points))+4-x,math.ceil(max(-p[1] for p in points))+4-y]
    if rect[2]*rect[3]>262144:raise ValueError('same_frame_roi_too_large')
    scan=corridor(pairs[0],rect)|corridor(pairs[1],rect);gaps=[];overlaps=[];alphas=[];images=[]
    for doc,pose in zip(docs,poses):
        attachments=doc['skins'][0]['attachments']
        ma=mask(attachments[a][a],pose[a],textures[a],rect);mb=mask(attachments[b][b],pose[b],textures[b],rect)
        pa,pb=ma>=8,mb>=8;gap=scan&~(pa|pb);overlap=scan&pa&pb;gaps.append(gap);overlaps.append(overlap)
        alphas.append(1-(1-ma/255)*(1-mb/255))
        rgb=np.full((*scan.shape,3),245,dtype=np.uint8);rgb[pa]=[99,175,232];rgb[pb]=[112,196,139];rgb[pa&pb]=[110,95,190];rgb[gap]=[235,65,45];images.append(rgb)
    diff=np.full((*scan.shape,3),245,dtype=np.uint8)
    diff[gaps[0]&gaps[1]]=[235,165,45];diff[gaps[0]&~gaps[1]]=[40,170,95];diff[gaps[1]&~gaps[0]]=[230,45,45]
    counts=lambda masks:[int(m.sum()) for m in masks]
    metrics={'time':time,'rect':rect,'corridor_pixels':int(scan.sum()),'gap_pixels':counts(gaps),'overlap_pixels':counts(overlaps),
        'fixed_gap_pixels':int((gaps[0]&~gaps[1]).sum()),'new_gap_pixels':int((gaps[1]&~gaps[0]).sum()),
        'added_overlap_pixels':int((overlaps[1]&~overlaps[0]).sum()),'lost_overlap_pixels':int((overlaps[0]&~overlaps[1]).sum()),
        'mean_union_alpha_change':float(np.abs(alphas[1]-alphas[0])[scan].mean()) if scan.any() else 0.}
    return metrics,images+[diff]


def analyze(before,after,files,boundaries,relations):
    from PIL import Image
    textures={n:texture(files['editor/images/'+n+'.png']) for n in boundaries};records=[];images={}
    for relation in relations:
        frames=[];worst=None
        for i in range(61):
            metrics,visual=compare_frame(before,after,relation,boundaries,textures,i/30);frames.append(metrics)
            if worst is None or (metrics['new_gap_pixels'],metrics['gap_pixels'][1])>(worst[0]['new_gap_pixels'],worst[0]['gap_pixels'][1]):worst=(metrics,visual)
        name=relation['driver']+'--'+relation['follower']
        for suffix,rgb in zip(('before','after','difference'),worst[1]):
            buf=BytesIO();Image.fromarray(rgb).save(buf,format='PNG');images[name+'-'+suffix+'.png']=buf.getvalue()
        records.append({'driver':relation['driver'],'follower':relation['follower'],'frames':frames,'heatmap_prefix':name,
            'selected_time':worst[0]['time'],'max_gap_pixels':[max(f['gap_pixels'][i] for f in frames) for i in (0,1)],
            'frames_with_new_gap':sum(f['new_gap_pixels']>0 for f in frames),'max_new_gap_pixels':max(f['new_gap_pixels'] for f in frames)})
    return {'profile':'same-frame-union-corridor-alpha8-v1','fps':30,'sample_count':61,'relations':records,
        'authority':'none','coverage':'candidate_corridors_only','runtime_raster_status':'not_evaluated'},images
