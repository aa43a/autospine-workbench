"""A user-requested visual inspection is not a detected geometry failure."""
import json
import math
from .pipeline_run import PipelineRunError
from ..targets.character43.region_order_interval import duration


def validate(manager,job,body):
    if (body.get('visual_inspection') is not True or body['triangle']!=-1
            or body['action'] not in {'contact_scope','region_order','garment_follow','transverse_repair','withdraw'}):
        raise PipelineRunError('motion_visual_inspection_invalid')
    from .motion_target_jobs import context
    result,files=context(manager,job)
    if result['artifact_sha256']!=body['artifact_sha256']:
        raise PipelineRunError('motion_visual_inspection_changed')
    document=json.loads(files['skeleton.json'])
    animation=document['animations'].get(body['animation'])
    choices=document['skins'][0]['attachments'].get(body['slot'],{})
    mesh=choices.get(body['slot'])
    time=body['time']
    if (animation is None or mesh is None or mesh.get('type')!='mesh'
            or type(time) not in (int,float) or not math.isfinite(time) or not 0<=time<=duration(animation)):
        raise PipelineRunError('motion_visual_inspection_scope_invalid')
    return dict(triangle=-1,time=time,reason='user_visual_inspection',detected_failure=False)
