"""Keep same-canvas replacement distinct from additional-view authoring needs."""
from .pipeline_run import PipelineRunError


def validate(action,views):
    if views is None:return None
    if (action!='pose_attachment' or not isinstance(views,list) or not 1<=len(views)<=3 or
            any(not isinstance(v,str) or v not in {'side','back','bent_joint'} for v in views) or
            len(set(views))!=len(views)):
        raise PipelineRunError('motion_material_view_needs_invalid')
    return sorted(views)


def context(request,views):
    return dict(schema='autospine.motion-additional-view-needs/v1',
        artifact_sha256=request['artifact_sha256'],draft_sha256=request['draft_sha256'],
        slot=request['slot'],animation=request['animation'],event=request['event'],views=views,
        status='awaiting_view_artwork_and_geometry_mapping',authority='none',
        same_canvas_return_supported=False,missing_art_proven=False,
        required_deliverables=['view_artwork_with_transparency','view_and_coordinate_convention',
                               'source_region_correspondence','pose_geometry_and_activation_interval'],
        acceptance_requires=['geometry_and_contact_checks','depth_and_material_seams',
                             'full_interval_runtime','stage_visual_review'])
