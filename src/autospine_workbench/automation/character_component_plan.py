"""Source-bound canvas data for reviewing connected-component parent mappings."""
from base64 import b64encode
from io import BytesIO
import json
from ..asset.planning.component_mount import partition
from ..resolved_project import canonical_sha256
from .pipeline_run import PipelineRunError
from .storage_io import read_document


def prepare(manager, project, body):
    if set(body) != {'job_id','region_id'} or any(type(v) is not str for v in body.values()):
        raise PipelineRunError('character_mount_plan_invalid')
    result=manager.get(project,body['job_id'])
    if result['status'] != 'needs_review': raise PipelineRunError('pipeline_preview_not_ready')
    files=manager.verified_files(project,body['job_id']); slot=body['region_id']
    doc=json.loads(files['skeleton.json']); manifest=json.loads(files['character-manifest.json'])
    eligible=[r for l in manifest['layers'] for r in l['regions'] if r['region_id']==slot and r.get('state')=='static_reference']
    if len(eligible)!=1: raise PipelineRunError('character_mount_source_unsupported')
    from ..targets.character43.affine_pose import sample
    from ..targets.character43.skirt_contact import source_image
    from PIL import Image
    setup=dict(doc,animations={'setup':{}})
    positions,bones=sample(setup,'setup',0)
    image,origin=source_image(files,doc,positions,slot); width,height=image.size
    parents=sorted(bones)
    if len(parents)>64: raise PipelineRunError('character_mount_parent_limit')
    anchors={name:[bones[name][0]-origin[0],origin[1]-bones[name][1]] for name in parents}
    plan=partition(image.getchannel('A').tobytes(),width,height,anchors)
    def png(value):
        buffer=BytesIO(); value.save(buffer,format='PNG')
        return 'data:image/png;base64,'+b64encode(buffer.getvalue()).decode('ascii')
    parts=[]
    for row in plan['regions']:
        left,top,right,bottom=row['bbox']; mask=Image.new('RGBA',(right-left,bottom-top))
        for index in row['pixels']: mask.putpixel((index%width-left,index//width-top),(45,200,255,150))
        parts.append(dict(component_id=row['component_id'],bbox=row['bbox'],proposed_parent=row['proposed_parent'],
                          visible_pixels=len(row['pixels']),mask=png(mask)))
    manager._current(read_document(manager._path(body['job_id'])/'request.json'))
    return dict(schema='autospine.component-mount-canvas/v1',project_id=project,job_id=body['job_id'],
        source_bundle_sha256=result['artifact_sha256'],source_region_id=slot,plan_sha256=canonical_sha256(plan),
        authority='none',allowed_parents=parents,parts=parts,residual_pixels=len(plan['residual_pixels']),
        image=png(image),width=width,height=height,
        bones=[dict(name=b['name'],point=anchors[b['name']],parent=b.get('parent')) for b in doc['bones']])
