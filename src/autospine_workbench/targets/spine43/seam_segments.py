"""Conservative open-chain readiness for selected alpha pixel samples."""
import math
from .alpha_seam import position
from .continuous_pose import world


def chains(samples,selected,vertices):
    pixels={tuple(samples[i]['pixel_xy']):i for i in sorted(set(selected))};neighbors={i:set() for i in pixels.values()}
    for (x,y),i in pixels.items():
        for dx in (-1,0,1):
            for dy in (-1,0,1):
                j=pixels.get((x+dx,y+dy))
                if j is not None and j!=i:neighbors[i].add(j)
    remaining=set(neighbors);result=[]
    while remaining:
        todo=[min(remaining)];component=set()
        while todo:
            i=todo.pop()
            if i in component:continue
            component.add(i);todo.extend(sorted(neighbors[i]-component))
        remaining-=component;ends=sorted(i for i in component if len(neighbors[i])==1)
        if len(component)<3:status='fragment'
        elif any(len(neighbors[i])>2 for i in component):status='branched_pixel_neighborhood'
        elif len(ends)!=2:status='closed_or_ambiguous'
        else:status='open_chain_candidate'
        row={'sample_indices':sorted(component),'status':status}
        if status=='open_chain_candidate':
            order=[];previous=None;current=ends[0]
            while current is not None:
                order.append(current);choices=sorted(neighbors[current]-{previous});previous,current=current,(choices[0] if choices else None)
            points=[position(samples[i],vertices) for i in order];lengths=[0.]
            for a,b in zip(points,points[1:]):lengths.append(lengths[-1]+math.dist(a,b))
            if lengths[-1]<=1e-12:raise ValueError('segment_zero_length')
            row.update(ordered_samples=order,setup_length_px=lengths[-1],u=[v/lengths[-1] for v in lengths])
        result.append(row)
    return result


def analyze(doc,boundary_report):
    setup=world(doc,0);result=[]
    for relation in boundary_report['relations']:
        row={'driver':relation['driver'],'follower':relation['follower']}
        for side in ('driver','follower'):
            name=relation[side];samples=boundary_report['boundaries'][name]['samples']
            row[side+'_components']=chains(samples,[p[side+'_sample'] for p in relation['pairs']],setup[name])
        row['status']='requires_segment_correspondence_review';result.append(row)
    return result
