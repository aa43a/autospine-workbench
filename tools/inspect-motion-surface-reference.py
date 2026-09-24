"""Blender-only read-only motion/model compatibility evidence, not retarget acceptance."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
import bpy
from mathutils import Matrix, Vector


def load(path):
    digest=hashlib.sha256(path.read_bytes()).hexdigest()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.fbx(filepath=str(path))
    rigs=[o for o in bpy.data.objects if o.type=='ARMATURE']
    if len(rigs)!=1:
        raise ValueError('one_armature_required')
    rig=rigs[0]
    bones={}
    for bone in rig.data.bones:
        name=bone.name.rsplit(':',1)[-1]
        if name in bones:
            raise ValueError('ambiguous_bone_name')
        bones[name]=dict(source_name=bone.name,parent=bone.parent.name.rsplit(':',1)[-1] if bone.parent else None,
                        head=list(bone.head_local),tail=list(bone.tail_local),
                        matrix=[list(row) for row in bone.matrix_local])
    meshes=[]
    for obj in bpy.data.objects:
        if obj.type!='MESH':continue
        modifiers=[m for m in obj.modifiers if m.type=='ARMATURE']
        meshes.append(dict(name=obj.name,vertices=len(obj.data.vertices),faces=len(obj.data.polygons),
                           uses_rig=bool(modifiers) and all(m.object==rig for m in modifiers),
                           groups=[g.name for g in obj.vertex_groups]))
    if hashlib.sha256(path.read_bytes()).hexdigest()!=digest:
        raise ValueError('source_changed')
    return dict(sha256=digest,bones=bones,meshes=meshes,object_matrix=[list(row) for row in rig.matrix_world])


def inspect(motion, model, output):
    if output.exists():raise ValueError('output_exists')
    source,target=load(motion),load(model)
    shared=sorted(set(source['bones'])&set(target['bones']))
    differences=[]; orientations=[]
    for name in shared:
        a,b=source['bones'][name],target['bones'][name]
        error=max(abs(x-y) for r,s in zip(a['matrix'],b['matrix']) for x,y in zip(r,s))
        qa,qb=(Matrix(v['matrix']).to_quaternion() for v in (a,b))
        angle=math.degrees(qa.rotation_difference(qb).angle)
        orientations.append(dict(bone=name,rest_rotation_difference_degrees=min(angle,360-angle),
            rest_head_distance=(Vector(a['head'])-Vector(b['head'])).length,
            length_ratio=(Vector(b['tail'])-Vector(b['head'])).length/(Vector(a['tail'])-Vector(a['head'])).length))
        if error>1e-5 or a['parent']!=b['parent']:
            differences.append(dict(bone=name,max_rest_matrix_difference=error,parent_matches=a['parent']==b['parent']))
    report=dict(schema='autospine.source-surface-reference-inspection/v1',authority='none',
                motion=source,model=target,shared_bones=shared,rest_differences=differences,rest_orientation=orientations,
                missing_model_bones=sorted(set(source['bones'])-set(target['bones'])),
                direct_action_copy_eligible=bool(target['meshes']) and all(m['uses_rig'] for m in target['meshes']) and not differences and
                  set(source['bones'])==set(target['bones']) and source['object_matrix']==target['object_matrix'] and
                  all(source['bones'][n]['source_name']==target['bones'][n]['source_name'] for n in shared),
                limitations=['matching_names_do_not_prove_rest_compatibility','not_a_target_character_surface',
                             'no_motion_transfer_or_visual_acceptance'])
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(dict(shared=len(shared),rest_differences=len(differences),
                         meshes=len(target['meshes']),direct_action_copy_eligible=report['direct_action_copy_eligible'])))


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    for name in ('motion','model','output'):parser.add_argument(name,type=Path)
    args=parser.parse_args(sys.argv[sys.argv.index('--')+1:])
    inspect(args.motion,args.model,args.output)
