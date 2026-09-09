"""Sample exactly the viewer's linear vertex tracks, not Spine bone interpolation."""
import math
from .component_mesh_tracks import tracks
from .component_local_solver import metrics
from ...resolved_project import canonical_sha256


def sample(frames, position):
    t=max(0.,min(len(frames)-1,position)); index=min(int(t),len(frames)-2); f=t-index
    return [[v+(frames[index+1][i][axis]-v)*f for axis,v in enumerate(p)] for i,p in enumerate(frames[index])]


def passed(qa):
    return qa['inversions']==0 and qa['min_area_ratio']>=.5 and qa['max_area_ratio']<=2 and qa['max_edge_stretch']<=2


def velocity_jump(frames):
    # One second per interval, as in the diagnostic timeline.
    return max(math.hypot(*(frames[i+1][v][k]-2*frames[i][v][k]+frames[i-1][v][k] for k in (0,1)))
               for i in range(1,len(frames)-1) for v in range(len(frames[i])))


def build(source, correction, skeleton):
    if (correction['source_sha256'] != canonical_sha256(source)
            or correction['skeleton_sha256'] != canonical_sha256(skeleton)):
        raise ValueError('component_temporal_source_mismatch')
    overrides={(r['layer_id'],r['component_id']):r['poses'] for r in correction['rows']}
    rows=[]
    for row in source['records']:
        key=row['layer_id'],row['component_id']
        if key not in overrides: continue
        mesh=row['mesh']; corrected=overrides[key]
        for track in tracks(mesh,skeleton,corrected):
            ticks=[]
            for tick in range(33):
                t=tick/4
                before=metrics(mesh['vertices_xy'],sample(track['original'],t),mesh['triangles'])
                after=metrics(mesh['vertices_xy'],sample(track['corrected'],t),mesh['triangles'])
                ticks.append(dict(time=t,before=before,after=after,new_failure=passed(before) and not passed(after)))
            hidden=[]
            for segment in range(8):
                if passed(ticks[segment*4]['after']) and passed(ticks[(segment+1)*4]['after']):
                    hidden.extend(t['time'] for t in ticks[segment*4+1:(segment+1)*4] if not passed(t['after']))
            rows.append(dict(layer_id=row['layer_id'],component_id=row['component_id'],bone_id=track['bone_id'],ticks=ticks,
                             new_failure_count=sum(t['new_failure'] for t in ticks),interior_failure_times=hidden,
                             max_velocity_jump_before=velocity_jump(track['original']),max_velocity_jump_after=velocity_jump(track['corrected'])))
    return dict(schema='autospine.component-temporal-qa/v1',profile='linear-vertex-quarter-second-v1',
                source_sha256=canonical_sha256(source),correction_sha256=canonical_sha256(correction),
                skeleton_sha256=canonical_sha256(skeleton),project_id=source['project_id'],rows=rows,
                authority='none',production_authorized=False,continuous_time_proven=False,runtime_status='not_evaluated')
