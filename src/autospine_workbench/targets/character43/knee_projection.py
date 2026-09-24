"""Separate 3D knee bending from observable 2D bend-side disagreement."""
import math


def measure(upper, lower):
    if (len(upper)!=3 or len(lower)!=3
            or any(not math.isfinite(v) for v in (*upper,*lower))):
        raise ValueError('knee_vectors_invalid')
    a,b=math.hypot(*upper),math.hypot(*lower)
    if min(a,b)<=1e-10:raise ValueError('knee_segment_degenerate')
    chord=[x+y for x,y in zip(upper,lower)];square=sum(x*x for x in chord)
    if square<1e-12*(a+b)**2:
        return dict(status='folded_chord_unobservable')
    u=sum(x*y for x,y in zip(upper,chord))/square
    residual=[x-u*y for x,y in zip(upper,chord)]
    screen=math.hypot(chord[0],chord[1])
    unit_a=[x/a for x in upper];unit_b=[x/b for x in lower]
    cross=[unit_a[1]*unit_b[2]-unit_a[2]*unit_b[1],unit_a[2]*unit_b[0]-unit_a[0]*unit_b[2],unit_a[0]*unit_b[1]-unit_a[1]*unit_b[0]]
    cross_length=math.hypot(*cross)
    plane=[x/cross_length for x in cross] if cross_length>1e-8 else None
    # Positive/negative are screen-coordinate signs, never anatomical front/back.
    signed=((chord[0]*upper[1]-chord[1]*upper[0])/screen/(a+b)) if screen>1e-8*(a+b) else None
    return dict(status='measured',bend_degrees=math.degrees(math.acos(max(-1,min(1,sum(x*y for x,y in zip(upper,lower))/(a*b))))),
        knee_depth_offset_ratio=residual[2]/(a+b),screen_bend_ratio=signed,
        bend_plane_normal=plane,screen_plane_alignment=abs(plane[2]) if plane else None,
        projection_visibility=[math.hypot(v[0],v[1])/length for v,length in ((upper,a),(lower,b))])


def compare(upper,lower,target_upper,target_lower):
    source=measure(upper,lower);target=measure(target_upper,target_lower)
    if source['status']!='measured' or target['status']!='measured':status='unobservable'
    elif source['screen_bend_ratio'] is None or abs(source['screen_bend_ratio'])<.01:
        status='source_bend_hidden_in_depth' if abs(source['knee_depth_offset_ratio'])>=.01 else 'source_nearly_straight'
    elif target['screen_bend_ratio'] is None or abs(target['screen_bend_ratio'])<.01:status='target_bend_flattened'
    elif source['screen_bend_ratio']*target['screen_bend_ratio']<0:status='projected_bend_reversed'
    else:status='projected_side_consistent'
    return dict(status=status,source=source,target=target)


def inspect(document,name,vectors,times,yaw=0):
    from .affine_pose import matrices
    from .oblique_motion import project
    if len(times)>2049:raise ValueError('knee_sample_limit')
    rows=[]
    for index,time in enumerate(times):
        world=matrices(document,name,time)
        for side,suffix in [('left','l'),('right','r')]:
            source=[project(vectors[f'humanoid.leg.{part}.{side}'][index],yaw) for part in ('upper','lower')]
            hip,knee,ankle=[world[n+'_'+suffix][4:] for n in ('thigh','calf','foot')]
            # World target uses screen-up, source vectors use screen-down.
            target=[(b[0]-a[0],a[1]-b[1],0) for a,b in ((hip,knee),(knee,ankle))]
            rows.append(dict(time=time,side=side,**compare(*source,*target)))
    return dict(profile='knee-projection-observation-v1',rows=rows,authority='none',selected=False,
        scope='source_samples_bone_axes_only_not_mesh_or_skirt_occlusion',
        thresholds=dict(screen_bend_ratio=.01,depth_offset_ratio=.01),
        limitations=['camera_depth_sign_is_not_anatomical_forward','no_order_or_motion_changes'])


def build(files,artifact,bundle,request):
    import json
    from .knee_source_samples import read
    name,vectors,times,source_times=read(files,bundle,request)
    report=inspect(json.loads(files['skeleton.json']),name,vectors,times,
                   (request.get('projection') or {}).get('yaw_degrees',0))
    for row in report['rows']:
        row['source_time']=source_times[times.index(row['time'])]
    report['artifact_sha256']=artifact
    report.update(animation=name,clip=request.get('clip'),projection=request.get('projection'),
                  motion_identity=request['motion_identity'],animation_modified=False)
    return report
