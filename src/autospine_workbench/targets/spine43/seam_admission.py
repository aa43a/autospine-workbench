"""Explain sampled relation gates without granting adoption or release authority."""
import itertools


def evaluate(direct, runtime, geometry, alpha):
    checks=runtime.get('regression',[])
    if len(checks)!=2 or {c.get('variant') for c in checks}!={'before','after'}:raise ValueError('admission_missing_runtime_regression')
    for c in checks:
        if (len(c['frames'])!=121 or any(f['channels_over_one']!=0 or f['visible_pixels']<=0 for f in c['frames']) or
            c['max_motion_error_px']>.001 or c['max_setup_error_px']>.001 or c['max_page_uv_error']>1e-6 or
            c['outside_viewport_coordinates']!=0 or not c['animation_changed']):raise ValueError('admission_runtime_regression_failed')
    if runtime['schema']=='autospine.seam-local-runtime/v1':
        matrix={'scales':[1,4],'atlases':['shared','reference'],'modes':['driver','follower','pair','all']}
    elif runtime['schema']=='autospine.seam-local-runtime/v2':matrix=runtime['capture_matrix']
    elif runtime['schema']=='autospine.seam-local-runtime/v3':
        if direct.get('schema')!='autospine.seam-boundary-probes/v1':raise ValueError('admission_probe_schema')
        matrix=runtime['capture_matrix']
    else:raise ValueError('admission_runtime_schema')
    if not all(matrix.get(k) for k in ('scales','atlases','modes')) or 1 not in matrix['scales'] or 'shared' not in matrix['atlases'] or not {'pair','all'}.issubset(matrix['modes']):
        raise ValueError('admission_capture_scope')
    for key,allowed in (('scales',{1,4}),('atlases',{'shared','reference'}),('modes',{'driver','follower','pair','all'})):
        if len(set(matrix[key]))!=len(matrix[key]) or not set(matrix[key]).issubset(allowed):raise ValueError('admission_capture_matrix')
    points=[(r,s) for r in direct['relations'] for s in r['samples']];index={}
    for c in runtime['captures']:
        i=c['sample_index']
        if not isinstance(i,int) or not 0<=i<len(points):raise ValueError('admission_sample_index')
        r,s=points[i]
        if c['point']!=s['world_point'] or abs(c['time']-s['frame']/30)>1e-12 or c['names']!=[r['driver'],r['follower']]:raise ValueError('admission_sample_identity')
        key=(i,c['variant'],c['scale'],c['atlas'],c['mode'])
        if key in index:raise ValueError('admission_duplicate_capture')
        if len(c['rgba'])!=c['scale']**2 or any(len(p)!=4 or any(type(v)!=int or not 0<=v<=255 for v in p) for p in c['rgba']):raise ValueError('admission_rgba')
        index[key]=c
    expected=set(itertools.product(range(len(points)),('before','after'),matrix['scales'],matrix['atlases'],matrix['modes']))
    if set(index)!=expected:raise ValueError('admission_incomplete_capture_matrix')
    rows=[];offset=0
    for r in direct['relations']:
        names=[r['driver'],r['follower']];counts={'pair_alpha_loss':0,'all_alpha_loss':0,'new_all_alpha_below8':0};loss=0
        for i in range(offset,offset+len(r['samples'])):
            for mode in ('pair','all'):
                a=index[i,'before',1,'shared',mode]['rgba'][0][3];b=index[i,'after',1,'shared',mode]['rgba'][0][3]
                counts[mode+'_alpha_loss']+=a-b>1
                if mode=='all':loss=max(loss,a-b);counts['new_all_alpha_below8']+=a>=8 and b<8
        offset+=len(r['samples'])
        relations=[a for a in alpha['relations'] if [a['driver'],a['follower']]==names]
        if len(relations)!=1 or any(n not in geometry['regions'] for n in names):raise ValueError('admission_missing_qa')
        growth=relations[0]['max_distance_growth_px'];shape=all(geometry['regions'][n]['passed'] for n in names)
        status=('blocked_geometry' if not shape else 'blocked_boundary_distance' if growth>2 else 'not_evaluated' if not r['samples'] else
                'review_runtime_alpha_loss' if counts['all_alpha_loss'] else 'review_pair_alpha_loss' if counts['pair_alpha_loss'] else 'sampled_no_new_regression')
        rows.append(dict(driver=names[0],follower=names[1],status=status,sample_count=len(r['samples']),geometry_passed=shape,
                         max_distance_growth_px=growth,max_all_alpha_loss=loss,**counts))
    result=dict(schema='autospine.seam-admission/v1',profile='geometry-distance-native-alpha-loss1-v1',authority='none',production_authorized=False,
                status='needs_review',coverage='recorded_points_native_density_only',relations=rows)
    if runtime['schema']=='autospine.seam-local-runtime/v3':
        result.update(schema='autospine.seam-boundary-comparison/v1',coverage='reference_boundary_representative_points_only')
    return result
