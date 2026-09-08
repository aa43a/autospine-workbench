"""Bounded low-alpha assignment proposals; ties and distant pixels stay residual."""
from array import array
from collections import deque
from io import BytesIO
import hashlib

from .partition_pixels import neighbors, png, MAX_PIXELS


def apply_policy(source_png, ownership_png, policy):
    from PIL import Image
    if policy not in ('pending','retain','nearest_4px'):
        raise ValueError('residual_policy_invalid')
    with Image.open(BytesIO(source_png)) as image, Image.open(BytesIO(ownership_png)) as mask:
        if image.mode!='RGBA' or mask.mode!='L' or image.size!=mask.size or image.width*image.height>MAX_PIXELS:
            raise ValueError('residual_input_invalid')
        size=image.size;raw=image.tobytes();owners=bytearray(mask.tobytes())
    if any(o not in (1,2,3) for o in owners):raise ValueError('residual_ownership_invalid')
    alpha=raw[3::4];n=len(alpha);w=size[0];before=bytes(owners)
    if any(not a and o!=3 for a,o in zip(alpha,owners)):
        raise ValueError('residual_transparent_owner_invalid')
    if policy=='nearest_4px':
        distance=array('b',[-1])*n;labels=bytearray(n);queue=deque()
        for i in range(n):
            if alpha[i]>=8 and owners[i] in (1,2):
                distance[i]=0;labels[i]=owners[i];queue.append(i)
        while queue:
            i=queue.popleft()
            if distance[i]>=4:continue
            for near in neighbors(i,w,n):
                d=distance[i]+1
                if distance[near]==-1:
                    distance[near]=d;labels[near]=labels[i];queue.append(near)
                elif distance[near]==d:
                    combined=labels[near]|labels[i]
                    if combined!=labels[near]:labels[near]=combined;queue.append(near)
        for i in range(n):
            if owners[i]==3 and 0<alpha[i]<8 and labels[i] in (1,2):owners[i]=labels[i]
    buffers={k:bytearray(len(raw)) for k in (1,2,3)}
    for i,owner in enumerate(owners):buffers[owner][i*4:i*4+4]=raw[i*4:i*4+4]
    rebuilt=bytes(a+b+c for a,b,c in zip(buffers[1],buffers[2],buffers[3]))
    if rebuilt!=raw:raise ValueError('residual_reconstruction_failed')
    def metrics(mask):
        residual=[a for a,o in zip(alpha,mask) if o==3 and a]
        return {'visible_pixels':len(residual),'alpha_sum':sum(residual),
                'alpha_mass_ratio':sum(residual)/sum(alpha) if sum(alpha) else 0.}
    qa={'before':metrics(before),'after':metrics(owners),'moved_pixels':sum(a!=b for a,b in zip(before,owners)),
        'rgba_reconstruction_exact':True,'source_rgba_sha256':hashlib.sha256(raw).hexdigest()}
    parts={name+'.png':png('RGBA',size,buffers[k]) for k,name in ((1,'left'),(2,'right'),(3,'residual'))}
    parts['ownership.png']=png('L',size,owners)
    return parts,qa
