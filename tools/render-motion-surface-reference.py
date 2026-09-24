"""Blender reference-only skin transfer with measured source head/tail fidelity."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
import bpy
from mathutils import Matrix, Vector
from bpy_extras.object_utils import world_to_camera_view


def name(value):
    return value.rsplit(':',1)[-1]


def load(path):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.fbx(filepath=str(path),use_image_search=False)
    rigs=[o for o in bpy.data.objects if o.type=='ARMATURE']
    if len(rigs)!=1:raise ValueError('single_rig_required')
    rig=rigs[0]
    if len({name(b.name) for b in rig.data.bones})!=len(rig.data.bones):raise ValueError('ambiguous_names')
    return rig


def capture_source(path,times):
    rig=load(path);scene=bpy.context.scene
    first,last=rig.animation_data.action.frame_range
    fps=scene.render.fps/scene.render.fps_base
    if any(t<0 or first+t*fps>last+1e-4 for t in times):raise ValueError('source_time_outside_clip')
    rest={name(b.name):b.matrix_local.copy() for b in rig.data.bones}
    samples=[]
    for t in times:
        f=first+t*fps;scene.frame_set(math.floor(f),subframe=f-math.floor(f))
        samples.append(dict(time=t,bones={name(b.name):dict(matrix=b.matrix.copy(),head=b.head.copy(),tail=b.tail.copy()) for b in rig.pose.bones}))
    return rest,samples,rig.matrix_world.copy(),dict(fps=fps,frame_range=[first,last])


def assign(rig,rest,sample):
    rows={name(b.name):b for b in rig.pose.bones}
    if set(rows)!=set(rest):raise ValueError('bone_inventory_mismatch')
    # Desired matrices are in the shared armature coordinate system. Preserve
    # source endpoints, calibrate reference rest roll, and scale only bone Y.
    for bone in rig.pose.bones:
        n=name(bone.name);source=sample['bones'][n]
        basis=source['matrix'].to_3x3() @ rest[n].to_3x3().inverted() @ bone.bone.matrix_local.to_3x3()
        direction=source['tail']-source['head']
        if direction.length<1e-8:raise ValueError('degenerate_source_bone')
        rotation=basis.to_quaternion()
        correction=(rotation @ Vector((0,1,0))).rotation_difference(direction.normalized())
        matrix=(correction @ rotation).to_matrix().to_4x4()
        matrix=matrix @ Matrix.Diagonal((1,direction.length/bone.bone.length,1,1))
        matrix.translation=source['head']
        bone.matrix=matrix
        bpy.context.view_layer.update()
    errors=[]
    for n,bone in rows.items():
        source=sample['bones'][n]
        errors.append(dict(bone=n,head_error=(rig.matrix_world @ bone.head-rig.matrix_world @ source['head']).length,
                          tail_error=(rig.matrix_world @ bone.tail-rig.matrix_world @ source['tail']).length))
    return errors


def run(motion,model,output,times):
    motion,model,output=(p.resolve() for p in (motion,model,output))
    if not 1<=len(times)<=64 or any(not math.isfinite(t) for t in times) or times!=sorted(set(times)):
        raise ValueError('finite_ordered_sample_times_required')
    if output.exists():raise ValueError('output_exists')
    hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (motion,model)}
    rest,samples,object_matrix,clock=capture_source(motion,times)
    rig=load(model)
    if max(abs(a-b) for r,s in zip(object_matrix,rig.matrix_world) for a,b in zip(r,s))>1e-7:
        raise ValueError('object_frame_mismatch')
    rig.animation_data_clear()
    meshes=[o for o in bpy.data.objects if o.type=='MESH']
    if not meshes or any(not any(m.type=='ARMATURE' and m.object==rig for m in o.modifiers) for o in meshes):
        raise ValueError('skinned_reference_required')
    for o in meshes:o.animation_data_clear()
    output.mkdir(parents=True)
    records=[];bounds=[]
    for sample in samples:
        errors=assign(rig,rest,sample)
        max_error=max(max(e['head_error'],e['tail_error']) for e in errors)
        records.append(dict(time=sample['time'],errors=errors,max_world_error=max_error))
        deps=bpy.context.evaluated_depsgraph_get()
        for o in meshes:
            evaluated=o.evaluated_get(deps);mesh=evaluated.to_mesh()
            bounds.extend(evaluated.matrix_world @ v.co for v in mesh.vertices)
            evaluated.to_mesh_clear()
    report=dict(schema='autospine.motion-surface-reference/v1',authority='none',sources=hashes,clock=clock,
                profile='source-endpoints-rest-roll-calibrated-reference-skin-v1',records=records,
                endpoint_fidelity_passed=all(r['max_world_error']<1e-5 for r in records),
                limitations=['reference_body_not_target_character','reference_skin_distortion_not_evaluated',
                             'source_endpoints_preserved_not_floor_contact_certification','sampled_poses_only_not_animation'])
    (output/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    if not report['endpoint_fidelity_passed']:raise ValueError('reference_endpoint_fidelity_failed')
    scene=bpy.context.scene;scene.render.engine='BLENDER_WORKBENCH'
    scene.render.resolution_x=640;scene.render.resolution_y=800;scene.render.resolution_percentage=100
    scene.render.image_settings.file_format='PNG'
    scene.display.shading.light='STUDIO';scene.display.shading.color_type='SINGLE'
    scene.display.shading.single_color=(.65,.75,.85);scene.display.shading.show_shadows=True
    scene.display.shading.show_cavity=True;scene.display.shading.background_type='WORLD'
    low=Vector([min(p[i] for p in bounds) for i in range(3)])
    high=Vector([max(p[i] for p in bounds) for i in range(3)])
    center=(low+high)/2;size=max(high-low)
    camera=bpy.data.objects.new('ReferenceCamera',bpy.data.cameras.new('ReferenceCamera'))
    scene.collection.objects.link(camera);scene.camera=camera
    camera.data.type='ORTHO';camera.data.ortho_scale=size*1.35
    images=[];captures=[]
    for view,direction in [('front',Vector((0,-1,0))),('side',Vector((1,0,0)))]:
        camera.location=center+direction*size*3
        camera.rotation_euler=(center-camera.location).to_track_quat('-Z','Y').to_euler()
        for i,sample in enumerate(samples):
            assign(rig,rest,sample)
            filename=f'{view}-{i}.png';scene.render.filepath=str(output/filename)
            bpy.ops.render.render(write_still=True)
            if not (output/filename).is_file():raise ValueError('capture_missing')
            captures.append(dict(view=view,time=sample['time'],image=filename,
                image_sha256=hashlib.sha256((output/filename).read_bytes()).hexdigest(),
                camera_world_matrix=[list(r) for r in camera.matrix_world],ortho_scale=camera.data.ortho_scale,
                joint_coordinates='normalized_image_xy_bottom_left_and_camera_depth',
                joints={name(b.name):dict(head=list(world_to_camera_view(scene,camera,rig.matrix_world @ b.head)),
                                         tail=list(world_to_camera_view(scene,camera,rig.matrix_world @ b.tail))) for b in rig.pose.bones}))
            images.append((view,sample['time'],filename))
    for p in (motion,model):
        if hashlib.sha256(p.read_bytes()).hexdigest()!=hashes[str(p)]:raise ValueError('source_changed')
    report['captures']=captures
    (output/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    html='<meta charset="utf-8"><title>下蹲三维表面参考</title><style>body{background:#16212b;color:white;font:16px system-ui}main{display:grid;grid-template-columns:repeat(3,1fr)}img{width:100%}</style><h1>三维表面参考 · 非目标角色验收</h1><p>同一相机与尺度。关节端点已核对；参考模型蒙皮轮廓不等于二维角色所需素材。</p><main>'
    html+=''.join(f'<figure><figcaption>{v} · {t:.6f} 秒</figcaption><img src="{f}"></figure>' for v,t,f in images)
    (output/'index.html').write_text(html+'</main>',encoding='utf-8')
    print(json.dumps(dict(passed=True,max_world_error=max(r['max_world_error'] for r in records),images=len(images))))


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for key in ('motion','model','output'):p.add_argument(key,type=Path)
    p.add_argument('--times',type=float,nargs='+',required=True)
    a=p.parse_args(sys.argv[sys.argv.index('--')+1:]);run(a.motion,a.model,a.output,a.times)
