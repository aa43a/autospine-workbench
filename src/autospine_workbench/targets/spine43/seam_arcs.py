"""Local supported contour arcs and conservative order-preserving pair candidates."""
import math
from .alpha_seam import position
from .continuous_pose import world


def local_arcs(record,max_gap=4):
    """Bridge at most max_gap texture edges; never cross ambiguous path endpoints."""
    if not isinstance(max_gap,int) or max_gap<1:raise ValueError('arc_gap_invalid')
    result=[]
    for ci,curve in enumerate(record['curves']):
        supported=sorted({o['edge'] for a in record['anchors'] for o in a['options'] if o['curve']==ci})
        if not supported:continue
        n=len(curve['edge_pixels']);closed=curve['status']=='closed_contour'
        if len(supported)==1:
            result.append({'curve':ci,'edges':supported,'status':'single_edge'});continue
        if closed:
            breaks=[i for i,e in enumerate(supported) if (supported[(i+1)%len(supported)]-e)%n>max_gap]
            if not breaks:
                result.append({'curve':ci,'edges':list(range(n)),'status':'whole_contour_unsupported'});continue
            start=(breaks[0]+1)%len(supported);supported=supported[start:]+supported[:start]
        groups=[[supported[0]]]
        for e in supported[1:]:
            gap=(e-groups[-1][-1])%n if closed else e-groups[-1][-1]
            if gap>max_gap:groups.append([e])
            else:groups[-1].append(e)
        for group in groups:
            length=(group[-1]-group[0])%n+1 if closed else group[-1]-group[0]+1
            edges=[(group[0]+i)%n for i in range(length)]
            result.append({'curve':ci,'edges':edges,'status':'local_arc_candidate' if len(group)>1 else 'single_edge',
                           'supported_edges':group,'inserted_edges':len(edges)-len(group)})
    return result


def ordered_paths(rows):
    """Two best distinct monotone paths, including both follower orientations."""
    solutions=[]
    for sign in (1,-1):
        states=[[(o['cost'],[o])] for o in rows[0]] if rows else []
        for options in rows[1:]:
            next_states=[]
            for option in options:
                choices=[]
                for histories in states:
                    for cost,path in histories:
                        last=path[-1]
                        if option['d']>last['d'] and sign*(option['f']-last['f'])>=0:
                            choices.append((cost+option['cost'],path+[option]))
                next_states.append(sorted(choices,key=lambda v:(v[0],[(x['d'],x['f']) for x in v[1]]))[:2])
            states=next_states
        for histories in states:
            for cost,path in histories:solutions.append((cost,sign,path))
    unique={}
    for cost,sign,path in solutions:
        key=tuple((o['d'],o['f']) for o in path)
        unique.setdefault(key,(cost,sign,path))
    return sorted(unique.values(),key=lambda s:(s[0],s[1],[(o['d'],o['f']) for o in s[2]]))[:2]


def analyze(doc,curve_report,boundary):
    records={r['attachment']:r for r in curve_report['curves']['attachments']}
    arcs={n:local_arcs(r) for n,r in records.items()};setup=world(doc,0);relations=[]
    for relation in boundary['relations']:
        names=[relation['driver'],relation['follower']];maps=[]
        for name in names:
            locations={(a['curve'],e):(ai,ei) for ai,a in enumerate(arcs[name]) for ei,e in enumerate(a['edges'])
                       if a['status']=='local_arc_candidate'}
            by_sample={}
            for anchor in records[name]['anchors']:
                choices=[]
                for oi,o in enumerate(anchor['options']):
                    loc=locations.get((o['curve'],o['edge']))
                    if loc is not None and o['embedding'] is not None:
                        choices.append({'arc':loc[0],'parameter':loc[1]+.5,'option':oi,'point':position(o['embedding'],setup[name])})
                by_sample[anchor['source_sample']]=choices
            maps.append(by_sample)
        groups={};blocked=[]
        for pi,pair in enumerate(relation['pairs']):
            left=maps[0][pair['driver_sample']];right=maps[1][pair['follower_sample']]
            memberships={(d['arc'],f['arc']) for d in left for f in right}
            if len(memberships)!=1:
                blocked.append({'pair':pi,'reason_code':'arc_missing_or_ambiguous'});continue
            key=next(iter(memberships));options=[]
            for d in left:
                for f in right:
                    options.append({'pair':pi,'d':d['parameter'],'f':f['parameter'],'driver_option':d['option'],
                                    'follower_option':f['option'],'driver_point':d['point'],'follower_point':f['point'],
                                    'cost':math.dist(d['point'],f['point'])**2})
            groups.setdefault(key,[]).append(options)
        outputs=[]
        for key,rows in sorted(groups.items()):
            rows.sort(key=lambda opts:(min(o['d'] for o in opts),opts[0]['pair']))
            result={'driver_arc':key[0],'follower_arc':key[1],'pairs':[r[0]['pair'] for r in rows]}
            solutions=ordered_paths(rows)
            if len(rows)<3:result.update(status='blocked',reason_code='insufficient_arc_pairs')
            elif not solutions:result.update(status='blocked',reason_code='nonmonotone_correspondence')
            else:
                cost,sign,path=solutions[0];plateaus=sum(a['f']==b['f'] for a,b in zip(path,path[1:]))
                result.update(status='candidate_requires_review',direction=sign,cost=cost,path=path,
                              alternative_margin=solutions[1][0]-cost if len(solutions)>1 else None,
                              many_to_one_steps=plateaus,reason_code='many_to_one_requires_review' if plateaus else 'ordered_arc_candidate')
            outputs.append(result)
        relations.append({'driver':names[0],'follower':names[1],'source_pair_count':len(relation['pairs']),
                          'groups':outputs,'blocked_pairs':blocked})
    return {'profile':'alpha8-local-gap4-ordered-pairs-v1','arcs':arcs,'relations':relations,
            'authority':'none','shape_solver':'not_run','max_support_gap_edges':4}
