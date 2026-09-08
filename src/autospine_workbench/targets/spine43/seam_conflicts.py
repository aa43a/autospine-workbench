"""Audit multi-to-one alpha correspondences without dropping difficult pairs."""
import math
from .alpha_seam import position,nearest_pairs
from .continuous_pose import world
from .seam_translation import influences,rotation,rotate


def analyze(doc,boundary_report):
    setup=world(doc,0);frames=[world(doc,i/30) for i in range(61)];rows=[]
    for relation in boundary_report['relations']:
        a,b=relation['driver'],relation['follower'];boundaries=boundary_report['boundaries']
        left=[position(s,setup[a]) for s in boundaries[a]['samples']];right=[position(s,setup[b]) for s in boundaries[b]['samples']]
        reverse={(p['follower_sample'],p['driver_sample']) for p in nearest_pairs(right,left)}
        groups={}
        for pair in relation['pairs']:groups.setdefault(pair['follower_sample'],[]).append(pair['driver_sample'])
        bone=next(iter(influences(doc['skins'][0]['attachments'][b][b])));base_angle=rotation(doc,bone,0);conflicts=[]
        for follower,drivers in sorted(groups.items()):
            if len(drivers)<2:continue
            spread=0.
            for frame,pose in enumerate(frames):
                targets=[]
                for driver in drivers:
                    rest=rotate([right[follower][k]-left[driver][k] for k in (0,1)],rotation(doc,bone,frame/30)-base_angle)
                    p=position(boundaries[a]['samples'][driver],pose[a]);targets.append([p[k]+rest[k] for k in (0,1)])
                spread=max(spread,max(math.dist(x,y) for x in targets for y in targets))
            conflicts.append({'follower_sample':follower,'driver_samples':drivers,'max_target_spread_px':spread})
        rows.append({'driver':a,'follower':b,'pair_count':len(relation['pairs']),
            'reciprocal_pair_count':sum((p['driver_sample'],p['follower_sample']) in reverse for p in relation['pairs']),
            'unique_follower_count':len(groups),'many_to_one':conflicts,
            'max_target_spread_px':max((g['max_target_spread_px'] for g in conflicts),default=0.),'decision':'retain_all_pending'})
    return rows
