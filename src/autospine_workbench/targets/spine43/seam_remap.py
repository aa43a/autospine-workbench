"""Local injective remapping only for observed conflicting target groups."""
from copy import deepcopy
import math
from functools import lru_cache
from .alpha_seam import analyze,position
from .continuous_pose import world
from .seam_conflicts import analyze as conflicts
from .alpha_seam_bake import bake_from_report


def assignment(options):
    """Bounded minimum squared-distance assignment; never partial adoption."""
    drivers=sorted(options);targets=sorted({t for row in options.values() for t,_ in row})
    if len(drivers)>8 or len(targets)>16:return None
    bits={t:1<<i for i,t in enumerate(targets)}
    @lru_cache(None)
    def visit(index,used):
        if index==len(drivers):return 0.,()
        best=None
        for target,distance in options[drivers[index]]:
            if used&bits[target]:continue
            tail=visit(index+1,used|bits[target])
            if tail is None:continue
            candidate=(distance*distance+tail[0],(target,)+tail[1])
            if best is None or candidate<best:best=candidate
        return best
    result=visit(0,0)
    return None if result is None else dict(zip(drivers,result[1]))


def remap(source,baseline):
    report=deepcopy(baseline);setup=world(source,0);changes=[]
    for relation,audit in zip(report['relations'],conflicts(source,baseline)):
        a,b=relation['driver'],relation['follower'];bounds=report['boundaries']
        for group in audit['many_to_one']:
            if group['max_target_spread_px']<=2:continue
            drivers=set(group['driver_samples']);reserved={p['follower_sample'] for p in relation['pairs'] if p['driver_sample'] not in drivers}
            anchor=bounds[b]['samples'][group['follower_sample']]['pixel_xy'];options={}
            for driver in sorted(drivers):
                p=position(bounds[a]['samples'][driver],setup[a]);available=[]
                for j,sample in enumerate(bounds[b]['samples']):
                    if j in reserved or math.dist(anchor,sample['pixel_xy'])>8:continue
                    distance=math.dist(p,position(sample,setup[b]))
                    if distance<=4:available.append((j,distance))
                options[driver]=sorted(available,key=lambda row:(row[1],row[0]))
            chosen=assignment(options)
            change={'driver':a,'follower':b,'source_follower_sample':group['follower_sample'],
                'driver_samples':sorted(drivers),'source_target_spread_px':group['max_target_spread_px'],
                'status':'blocked_no_complete_assignment' if chosen is None else 'candidate_requires_review','replacements':[]}
            if chosen is not None:
                for pair in relation['pairs']:
                    i=pair['driver_sample']
                    if i not in drivers:continue
                    pair['follower_sample']=chosen[i]
                    pair['setup_distance_px']=dict(options[i])[chosen[i]]
                    change['replacements'].append(deepcopy(pair))
            changes.append(change)
    return report,changes


def bake(source,files):
    if set(source['animations'])!={'continuous-corrective-inspection'}:raise ValueError('remap_source_animation_invalid')
    baseline=analyze(source,files);mapped,changes=remap(source,baseline)
    doc,qa=bake_from_report(source,files,mapped)
    qa['before']=baseline
    qa['remapping']={'profile':'conflict2-local8-injective-v1','changes':changes,
        'after_conflicts':conflicts(source,mapped),'removed_driver_pairs':0,'authority':'none'}
    # Existing all-pair QA uses the original correspondence set, so remapping
    # cannot manufacture a pass by excluding the old difficult boundaries.
    qa['profile']='alpha-local-conflict-remap-v1'
    doc['animations']={'remapped-seam-inspection':doc['animations'].pop('alpha-seam-inspection')}
    return doc,qa
