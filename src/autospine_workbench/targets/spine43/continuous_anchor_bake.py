"""Bake continuous target anchors using the frozen local displacement solver."""
from copy import deepcopy
import math
from .alpha_seam import position
from .alpha_seam_bake import bake_from_report
from .continuous_pose import world


def bake(source,files,baseline,parameters):
    if len(baseline['relations'])!=len(parameters['analysis']['relations']):raise ValueError('anchor_bake_relation_count')
    mapped=deepcopy(baseline);setup=world(source,0);replaced=[]
    for relation,proposal in zip(mapped['relations'],parameters['analysis']['relations']):
        if (relation['driver'],relation['follower'])!=(proposal['driver'],proposal['follower']):
            raise ValueError('anchor_bake_relation_identity')
        driver,follower=relation['driver'],relation['follower'];samples=mapped['boundaries'][follower]['samples']
        seen=set()
        for group in proposal['groups']:
            if group['status']!='candidate_requires_review':continue
            if len(group['pairs'])!=len(group['samples']):raise ValueError('anchor_bake_sample_count')
            for pi,sample in zip(group['pairs'],group['samples']):
                if pi in seen or not 0<=pi<len(relation['pairs']):raise ValueError('anchor_bake_pair_identity')
                seen.add(pi)
                pair=relation['pairs'][pi];anchor={**deepcopy(sample['embedding']),'pixel_xy':sample['pixel_xy']}
                pair['follower_sample']=len(samples);samples.append(anchor)
                left=position(mapped['boundaries'][driver]['samples'][pair['driver_sample']],setup[driver])
                pair['setup_distance_px']=math.dist(left,position(anchor,setup[follower]))
                replaced.append({'driver':driver,'follower':follower,'pair':pi})
    doc,qa=bake_from_report(source,files,mapped)
    doc['animations']={'continuous-anchor-inspection':doc['animations'].pop('alpha-seam-inspection')}
    qa.update(profile='continuous-anchor-frozen-local-solver-v1',replacement_count=len(replaced),
              replacements=replaced,source_pair_count=sum(len(r['pairs']) for r in baseline['relations']),
              tangent_solver='not_run',area_protection='post_bake_geometry_gate')
    return doc,qa
