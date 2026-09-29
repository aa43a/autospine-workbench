"""Read current project rasters for advisory geometry, without registering a rig."""
from pathlib import Path
from copy import deepcopy
from ..safe_input_files import read_real_file
from .route_geometry import analyze, eligible


def reviewed_project(projects, project_id, project):
    """Use current registered edits for geometry, without changing PSD authoring."""
    from .animated_joint_review import get_joint_review
    from .animated_inputs import AnimatedSourceError
    try:
        review = get_joint_review(projects, project_id)
    except AnimatedSourceError:
        return project, None
    result = deepcopy(project)
    joints = {j['id']: j for j in result['resolved'].get('skeleton', {}).get('joints', [])}
    reviewed = set(review['reviewed_joint_ids'])
    for row in review['records']:
        identifier = row['joint_id']
        # Registered coordinates supersede the initial inference, including an
        # explicitly unobservable point. Never retain an old point in its place.
        point = row['position'] if row['status'] == 'observed' else None
        joints[identifier] = dict(id=identifier, x=point[0] if point else None,
            y=point[1] if point else None, source='registered_model_assisted',
            review_state='reviewed' if identifier in reviewed else 'unreviewed')
    result['resolved'].setdefault('skeleton', {})['joints'] = list(joints.values())
    return result, review['input_identity_sha256']


def collect(projects, project_id, project):
    images, unreadable = {}, set()
    layers=[layer for layer in project['resolved']['layers'] if eligible(layer)]
    resolver=getattr(projects,'resolve_asset',None)
    for layer in layers[:16]:
        try:
            if not callable(resolver): continue
            images[layer['id']]=read_real_file(Path(resolver(project_id,'layer',layer['id'])),
                                               64 << 20,'route layer')
        except (OSError,ValueError,RuntimeError):
            unreadable.add(layer['id'])
    geometry_project, identity = reviewed_project(projects, project_id, project)
    result=analyze({**geometry_project,'id':project_id},images)
    if identity:
        result['joint_input_identity_sha256'] = identity
    limited={layer['id'] for layer in layers[16:]}
    for row in result['records']:
        if row['layer_id'] in unreadable:row['reason_codes'].append('layer_image_read_failed')
        if row['layer_id'] in limited:row['reason_codes'].append('route_layer_limit')
    return result


def supported_broad_rows(evidence):
    excluded={'arm_joints_unreviewed','alpha_severely_disconnected'}
    return [row for row in (evidence or {}).get('records',[])
            if row['classification']=='broad_off_axis_shape' and not excluded.intersection(row['reason_codes'])]
