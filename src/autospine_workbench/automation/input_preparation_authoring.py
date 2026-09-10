"""Import saved coordinates before initial registration without rewriting authoring."""
from copy import deepcopy
import math
from ..benchmark.joint_draft import JOINTS
from ..benchmark.assisted_joint_draft import validate_assisted_joint_draft
from .animated_inputs import AnimatedSourceError


def inspect(store, project_id, project):
    overrides=project['overrides'];items=[]
    for field in ('joint_decisions','split_decisions'):
        for identifier in overrides.get(field,{}):
            items.append(dict(id=identifier,field=field,reason_code='input_preparation_structure_unsupported'))
    changes=overrides.get('layer_overrides',{})
    if changes:
        base=store._build_project(store._record(project_id),include_overrides=False)
        layers={row['id']:row for row in base['layers']}
        for layer,fields in changes.items():
            for field,value in fields.items():
                if field=='notes' or value==layers.get(layer,{}).get(field):continue
                items.append(dict(id=layer,field=field,reason_code='input_preparation_layer_edit_unsupported'))
    points=overrides.get('joint_overrides',{})
    for joint,point in points.items():
        if (type(point) is not dict or any(type(point.get(k)) not in (int,float)
            or not math.isfinite(point[k]) for k in ('x','y'))):
            items.append(dict(id=joint,field='joint_overrides',reason_code='input_preparation_joint_invalid'))
    return dict(authored_joint_count=len(set(points).intersection(JOINTS)),
                ignored_joint_ids=sorted(set(points)-set(JOINTS)),unsupported_items=items)


def require_supported(store, project_id, project):
    result=inspect(store,project_id,project)
    if result['unsupported_items']:
        raise AnimatedSourceError('input_preparation_authoring_edits_unsupported')
    return result


def import_joints(candidate,baseline,pose,assisted,project):
    result=deepcopy(assisted);points=project['overrides'].get('joint_overrides',{})
    imported=[]
    for row in result['draft']['records']:
        joint=row['joint_id']
        if joint not in points:continue
        row.update(position=[points[joint]['x'],points[joint]['y']],status='observed',
                   notes='主工作台已保存人工校正；来源准备保留该位置，不作为独立真值')
        imported.append(joint)
    result['reviewed_joint_ids']=imported
    validate_assisted_joint_draft(candidate,baseline,pose,result)
    return result,imported,sorted(set(points)-set(JOINTS))
