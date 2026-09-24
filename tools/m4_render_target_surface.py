"""Render unchanged target textures on measured 3D LBS/DQ comparison surfaces."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import bpy
import numpy as np


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def material(path):
    mat=bpy.data.materials.new(path.stem);mat.use_nodes=True
    nodes=mat.node_tree.nodes;nodes.clear();links=mat.node_tree.links
    output=nodes.new('ShaderNodeOutputMaterial');mix=nodes.new('ShaderNodeMixShader')
    transparent=nodes.new('ShaderNodeBsdfTransparent');emission=nodes.new('ShaderNodeEmission')
    texture=nodes.new('ShaderNodeTexImage');texture.image=bpy.data.images.load(str(path))
    texture.interpolation='Linear';texture.extension='CLIP'
    links.new(texture.outputs['Color'],emission.inputs['Color'])
    links.new(texture.outputs['Alpha'],mix.inputs[0])
    links.new(transparent.outputs[0],mix.inputs[1]);links.new(emission.outputs[0],mix.inputs[2])
    links.new(mix.outputs[0],output.inputs['Surface'])
    return mat


def run(surface_path,poses_path,output,diagnostic=False):
    surface_path,poses_path,output=(p.resolve() for p in (surface_path,poses_path,output))
    surface_raw=surface_path.read_bytes();poses_raw=poses_path.read_bytes()
    surfaces=json.loads(surface_raw);poses=json.loads(poses_raw)
    if digest(surface_raw)!=poses['surface_sha256']:raise ValueError('render_surface_identity')
    times=[0.,.9];records=[r for r in poses['records'] if any(abs(r['time']-t)<1e-8 for t in times)]
    if len(records)!=2*len(surfaces['surfaces']):raise ValueError('render_samples_missing')
    for s in surfaces['surfaces'].values():
        if digest(Path(s['texture_path']).read_bytes())!=s['texture_sha256']:raise ValueError('render_texture_changed')
    output.mkdir(parents=True,exist_ok=False)
    bpy.ops.wm.read_factory_settings(use_empty=True);scene=bpy.context.scene
    scene.render.engine='CYCLES';scene.cycles.device='CPU';scene.cycles.samples=8
    scene.cycles.use_denoising=False;scene.render.film_transparent=True
    scene.render.resolution_x=640;scene.render.resolution_y=800;scene.render.resolution_percentage=100
    scene.render.image_settings.file_format='PNG';scene.render.image_settings.color_mode='RGBA'
    scene.view_settings.view_transform='Standard';scene.view_settings.look='None'
    scene.view_settings.exposure=0;scene.view_settings.gamma=1
    objects={}
    for slot,s in surfaces['surfaces'].items():
        mesh=bpy.data.meshes.new(slot);mesh.from_pydata(s['vertices'],[],s['triangles']);mesh.update()
        uv=mesh.uv_layers.new(name='OriginalUV')
        for polygon in mesh.polygons:
            for loop_id in polygon.loop_indices:
                u,v=s['uvs'][mesh.loops[loop_id].vertex_index];uv.data[loop_id].uv=(u,1-v)
        obj=bpy.data.objects.new(slot,mesh);scene.collection.objects.link(obj)
        obj.data.materials.append(material(Path(s['texture_path'])));objects[slot]=obj
    all_points=np.concatenate([np.asarray(r[key]) for r in records for key in ('vertices','dq_vertices')])
    low=all_points.min(axis=0);high=all_points.max(axis=0);center=(low+high)/2
    scale=max(high[1]-low[1],(high[0]-low[0])*800/640)*1.1
    camera=bpy.data.objects.new('FixedComparisonCamera',bpy.data.cameras.new('Camera'))
    scene.collection.objects.link(camera);scene.camera=camera
    camera.data.type='ORTHO';camera.data.ortho_scale=float(scale)
    camera.data.clip_end=100000;camera.location=(float(center[0]),float(center[1]),float(high[2]+2000))
    camera.rotation_euler=(0,0,0)
    captures=[]
    for t in times:
        for mode,key in [('lbs','vertices'),('dq','dq_vertices')]:
            for row in records:
                if abs(row['time']-t)>1e-8:continue
                for v,p in zip(objects[row['slot']].data.vertices,row[key],strict=True):v.co=p
                objects[row['slot']].data.update()
            bpy.context.view_layer.update()
            name=f'{mode}-{t:g}.png';scene.render.filepath=str(output/name)
            bpy.ops.render.render(write_still=True)
            captures.append(dict(time=t,mode=mode,image=name,sha256=digest((output/name).read_bytes())))
    if diagnostic:
        # Last pose above is DQ at .9. Isolate each leg; opaque pass retains all
        # original triangles, including transparent texture support margins.
        for slot,obj in objects.items():
            for other in objects.values():other.hide_render=other!=obj
            mat=obj.data.materials[0];nodes=mat.node_tree.nodes;links=mat.node_tree.links
            mix=next(n for n in nodes if n.type=='MIX_SHADER')
            alpha_link=next(l for l in links if l.to_node==mix and l.to_socket==mix.inputs[0])
            source_socket=alpha_link.from_socket
            for opaque in (False,True):
                if opaque:links.remove(alpha_link);mix.inputs[0].default_value=1
                name=f'{slot}-dq-0.9-'+('opaque' if opaque else 'texture')+'.png'
                scene.render.filepath=str(output/name);bpy.ops.render.render(write_still=True)
                captures.append(dict(time=.9,mode='dq-isolated',slot=slot,opaque=opaque,
                                     image=name,sha256=digest((output/name).read_bytes())))
            links.new(source_socket,mix.inputs[0])
        for obj in objects.values():obj.hide_render=False
    for s in surfaces['surfaces'].values():
        if digest(Path(s['texture_path']).read_bytes())!=s['texture_sha256']:raise ValueError('render_texture_changed_during_capture')
    if digest(surface_path.read_bytes())!=digest(surface_raw) or digest(poses_path.read_bytes())!=digest(poses_raw):
        raise ValueError('render_input_changed_during_capture')
    report=dict(surface_sha256=digest(surface_raw),poses_sha256=digest(poses_raw),captures=captures,
                textures={k:s['texture_sha256'] for k,s in surfaces['surfaces'].items()},
                renderer='Blender Cycles CPU',samples=8,filter='Linear',view_transform='Standard',
                camera_location=list(camera.location),ortho_scale=scale,accepted=False,
                rotation_mode=poses.get('rotation_mode','source_full_rotation'),
                scope='isolated_two_legs_original_front_material_not_Spine_Runtime',
                limitations=['two_sided_front_texture_not_back_material','hip_fixed_no_ground_contact',
                             'no_character_occlusion_or_seam_acceptance'])
    (output/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    cards=''.join(f'<figure><img src="{r["image"]}"><figcaption>{r["image"]}</figcaption></figure>' for r in captures)
    (output/'index.html').write_text('<!doctype html><meta charset="utf-8"><title>目标表面贴图对照</title>'
        '<style>body{background:#18232e;color:white;font:16px sans-serif}.grid{display:grid;grid-template-columns:1fr 1fr}'
        'img{max-width:100%;background:#46525e}figure{margin:12px}</style><h1>原贴图三维蒙皮对照</h1>'
        '<p>固定同一相机。前四图左 LBS、右 DQ；0 秒与 0.9 秒。后续诊断图按单腿显示原 alpha 与不透明几何；不透明不代表有效材料。尚未通过。</p>'
        '<p>'+('诊断：本组已移除源绕轴旋转，不是原动作候选。' if poses.get('rotation_mode')=='swing_control_source_twist_removed'
                  else '本组保留源完整旋转。')+'</p><div class="grid">'+cards+'</div>',encoding='utf-8')
    print(json.dumps(report))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('surface','poses','output'):p.add_argument(key,type=Path)
    p.add_argument('--diagnostic',action='store_true')
    a=p.parse_args(sys.argv[sys.argv.index('--')+1:]);run(a.surface,a.poses,a.output,a.diagnostic)
