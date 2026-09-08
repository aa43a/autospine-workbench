"""Do not let order diagnostics silently lose source correspondences."""
import math


def validate(report):
    if (report.get('schema')!='autospine.seam-arc-pairs/v1' or report.get('authority')!='none'
            or report.get('production_authorized') is not False or report.get('status')!='needs_review'):
        raise ValueError('arc_authority_invalid')
    analysis=report['analysis']
    for relation in analysis['relations']:
        ids=[p['pair'] for p in relation['blocked_pairs']]
        for group in relation['groups']:
            ids.extend(group['pairs'])
            for side in ('driver','follower'):
                arcs=analysis['arcs'][relation[side]];index=group[side+'_arc']
                if not 0<=index<len(arcs) or arcs[index]['status']!='local_arc_candidate':raise ValueError('arc_reference')
            if group['status']=='blocked':continue
            path=group['path'];sign=group['direction']
            if [o['pair'] for o in path]!=group['pairs'] or sign not in (-1,1):raise ValueError('arc_path_identity')
            for a,b in zip(path,path[1:]):
                if b['d']<=a['d'] or sign*(b['f']-a['f'])<0:raise ValueError('arc_path_order')
            for o in path:
                if any(not math.isfinite(v) for v in [o['d'],o['f'],o['cost']]+o['driver_point']+o['follower_point']):raise ValueError('arc_nonfinite')
            if abs(sum(o['cost'] for o in path)-group['cost'])>1e-8:raise ValueError('arc_path_cost')
            margin=group['alternative_margin']
            if margin is not None and (not math.isfinite(margin) or margin<0):raise ValueError('arc_alternative_margin')
            if sum(a['f']==b['f'] for a,b in zip(path,path[1:]))!=group['many_to_one_steps']:raise ValueError('arc_plateau_count')
        if sorted(ids)!=list(range(relation['source_pair_count'])):raise ValueError('arc_source_pair_coverage')
    return report
