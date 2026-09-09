"""Actual bone-angle interpolation plus canvas-space corrective offsets."""
from .component_mesh_tracks import tracks
from .component_temporal_qa import sample, passed
from .component_local_solver import metrics
from ..joints.mesh_weights import _rotate, _deform
from ...resolved_project import canonical_sha256


def sample_fk(mesh, bones, joint, angle):
    pivot=bones[joint]['head_xy'];frames={}
    for index,bone in enumerate(bones):
        head,rotation=bone['head_xy'],bone['world_rotation_degrees']
        if index>=joint:
            delta=_rotate([head[k]-pivot[k] for k in (0,1)],angle)
            head=[pivot[k]+delta[k] for k in (0,1)];rotation+=angle
        frames[bone['id']]=head,rotation
    return _deform(mesh['weights'],frames)


def sample_track(mesh,bones,track,time,corrected=False):
    t=max(0.,min(8.,time));index=min(int(t),7);f=t-index
    angle=track['angles'][index]+(track['angles'][index+1]-track['angles'][index])*f
    points=sample_fk(mesh,bones,[b['id'] for b in bones].index(track['bone_id']),angle)
    if corrected:
        offsets=[[[a[k]-b[k] for k in (0,1)] for a,b in zip(after,before)]
                 for after,before in zip(track['corrected'],track['original'])]
        delta=sample(offsets,t)
        points=[[p[k]+d[k] for k in (0,1)] for p,d in zip(points,delta)]
    return points


def build(source,correction,skeleton):
    if correction['source_sha256']!=canonical_sha256(source) or correction['skeleton_sha256']!=canonical_sha256(skeleton):
        raise ValueError('component_fk_source_mismatch')
    overrides={(r['layer_id'],r['component_id']):r['poses'] for r in correction['rows']}
    bones={b['id']:b for b in skeleton['bones']};rows=[]
    for row in source['records']:
        key=row['layer_id'],row['component_id']
        if key not in overrides:continue
        mesh=row['mesh'];chain=[bones[b] for b in mesh['bone_ids']]
        for track in tracks(mesh,skeleton,overrides[key]):
            ticks=[]
            for tick in range(33):
                t=tick/4
                linear=metrics(mesh['vertices_xy'],sample(track['corrected'],t),mesh['triangles'])
                before=metrics(mesh['vertices_xy'],sample_track(mesh,chain,track,t),mesh['triangles'])
                after=metrics(mesh['vertices_xy'],sample_track(mesh,chain,track,t,True),mesh['triangles'])
                ticks.append(dict(time=t,linear=linear,before=before,after=after,
                                  new_failure=passed(before) and not passed(after)))
            rows.append(dict(layer_id=row['layer_id'],component_id=row['component_id'],bone_id=track['bone_id'],ticks=ticks,
                             interpolation_disagreements=sum(passed(t['linear'])!=passed(t['after']) for t in ticks),
                             new_failure_count=sum(t['new_failure'] for t in ticks)))
    return dict(schema='autospine.component-fk-qa/v1',profile='bone-angle-canvas-offset-quarter-second-v1',
                source_sha256=canonical_sha256(source),correction_sha256=canonical_sha256(correction),
                skeleton_sha256=canonical_sha256(skeleton),project_id=source['project_id'],rows=rows,
                authority='none',production_authorized=False,runtime_status='not_evaluated',continuous_time_proven=False)
