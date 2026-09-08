"""Disjoint pixel ownership with explicit unresolved residuals; no raster editing."""
from array import array
from collections import deque
from io import BytesIO
import hashlib
import math

MAX_PIXELS = 4*1024*1024


def png(mode, size, pixels):
    from PIL import Image
    stream = BytesIO()
    Image.frombytes(mode, size, bytes(pixels)).save(stream, format='PNG')
    return stream.getvalue()


def neighbors(index, w, n):
    if index % w: yield index-1
    if index % w != w-1: yield index+1
    if index >= w: yield index-w
    if index+w < n: yield index+w


def partition(raw, source, proposal):
    from PIL import Image
    if type(raw) is not bytes or len(raw)>128*1024*1024 or hashlib.sha256(raw).hexdigest() != source['image_sha256']:
        raise ValueError('partition_image_changed')
    with Image.open(BytesIO(raw)) as image:
        w, h = image.size; x, y, right, bottom = source['bbox']
        if image.format != 'PNG' or image.mode != 'RGBA' or (w,h) != (right-x,bottom-y):
            raise ValueError('partition_image_invalid')
        if w*h > MAX_PIXELS:
            raise ValueError('partition_resource_limit')
        pixels = image.tobytes()
    major = {c['id']: c for c in proposal['components']}
    if len(major) != 2 or {c.get('side') for c in major.values()} != {'l','r'}:
        raise ValueError('partition_components_invalid')
    alpha = pixels[3::4]; n = w*h
    owners, visited = bytearray(n), bytearray(n)
    components, run_id, found, component_count = [], -1, set(), 0
    for start in range(n):
        if alpha[start] < 8: continue
        if start % w == 0 or alpha[start-1] < 8: run_id += 1
        if visited[start]: continue
        component_count+=1
        if component_count>4096: raise ValueError('partition_resource_limit')
        queue = deque([start]); visited[start] = 1; members = array('I')
        sx = sy = 0; left = right = start%w; top = bottom = start//w
        while queue:
            index = queue.popleft(); members.append(index)
            px, py = index%w, index//w; sx += px; sy += py
            left=min(left,px);right=max(right,px);top=min(top,py);bottom=max(bottom,py)
            for near in neighbors(index,w,n):
                if not visited[near] and alpha[near] >= 8:
                    visited[near]=1;queue.append(near)
        center = [sx/len(members)+x, sy/len(members)+y]
        if run_id in major:
            c=major[run_id];found.add(run_id)
            if c['area'] != len(members) or c['bbox'] != [left+x,top+y,right+x+1,bottom+y+1] or c['centroid'] != center:
                raise ValueError('partition_component_changed')
            owner = 1 if c['side']=='l' else 2
        else:
            distances = sorted((math.dist(center,c['centroid']),c['side']) for c in major.values())
            owner = (1 if distances[0][1]=='l' else 2) if distances[1][0]-distances[0][0] > 1 else 3
            components.append({'component_id':run_id,'area':len(members),'owner':owner,
                               'distance_margin_px':distances[1][0]-distances[0][0]})
        for index in members: owners[index]=owner
    if found != set(major): raise ValueError('partition_component_missing')
    # Propagate only through low-alpha pixels. Equal shortest paths retain both
    # labels and become residual, so a tie never silently chooses a side.
    distance=array('i',[-1])*n; queue=deque()
    for index, owner in enumerate(owners):
        if owner in (1,2):
            distance[index]=0;queue.append(index)
    while queue:
        index=queue.popleft()
        for near in neighbors(index,w,n):
            if not 0 < alpha[near] < 8: continue
            next_distance=distance[index]+1
            if distance[near] == -1:
                distance[near]=next_distance;owners[near]=owners[index];queue.append(near)
            elif distance[near] == next_distance:
                combined=owners[near]|owners[index]
                if combined != owners[near]: owners[near]=combined;queue.append(near)
    buffers={owner:bytearray(len(pixels)) for owner in (1,2,3)}
    counts={owner:0 for owner in (1,2,3)};low={owner:0 for owner in (1,2,3)}
    for index in range(n):
        owner=owners[index] or 3;owners[index]=owner
        buffers[owner][index*4:index*4+4]=pixels[index*4:index*4+4]
        if alpha[index]: counts[owner]+=1
        if 0 < alpha[index] < 8: low[owner]+=1
    rebuilt=bytes(a+b+c for a,b,c in zip(buffers[1],buffers[2],buffers[3]))
    if rebuilt != pixels: raise ValueError('partition_reconstruction_failed')
    files={side+'.png':png('RGBA',(w,h),buffers[owner]) for owner,side in ((1,'left'),(2,'right'),(3,'residual'))}
    files['ownership.png']=png('L',(w,h),owners)
    qa={'rgba_reconstruction_exact':True,'source_rgba_sha256':hashlib.sha256(pixels).hexdigest(),
        'reconstructed_rgba_sha256':hashlib.sha256(rebuilt).hexdigest(),
        'visible_pixel_counts':{str(k):v for k,v in counts.items()},
        'low_alpha_pixel_counts':{str(k):v for k,v in low.items()},'satellite_components':components}
    return files,qa
