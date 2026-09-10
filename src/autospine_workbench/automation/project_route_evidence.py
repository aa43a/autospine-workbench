"""Read current project rasters for advisory geometry, without registering a rig."""
from pathlib import Path
from ..safe_input_files import read_real_file
from .route_geometry import analyze, eligible


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
    result=analyze({**project,'id':project_id},images)
    limited={layer['id'] for layer in layers[16:]}
    for row in result['records']:
        if row['layer_id'] in unreadable:row['reason_codes'].append('layer_image_read_failed')
        if row['layer_id'] in limited:row['reason_codes'].append('route_layer_limit')
    return result


def supported_broad_rows(evidence):
    excluded={'arm_joints_unreviewed','alpha_severely_disconnected'}
    return [row for row in (evidence or {}).get('records',[])
            if row['classification']=='broad_off_axis_shape' and not excluded.intersection(row['reason_codes'])]
