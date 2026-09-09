"""Parent-length-capped distal transition hypotheses, shared across characters."""
from copy import deepcopy
from .component_weight_transition import measure
from .component_partitions import validate as validate_partition
from .component_mesh import isolated_png
from ..joints.distal_width import reweight
from ..joints.partition_mesh_qa import evaluate
from ...resolved_project import canonical_sha256
import hashlib


def build(source,entries,skeleton):
    if (source['schema']!='autospine.component-weight-transition/v1' or source['skeleton_sha256']!=canonical_sha256(skeleton)
            or source.get('authority')!='none' or source.get('production_authorized') is not False):
        raise ValueError('parent_distal_source_mismatch')
    lookup={};bones={b['id']:b for b in skeleton['bones']}
    for layer,raw,candidate,_ in entries:
        validate_partition(layer,raw,candidate)
        for region in candidate['components']:lookup[layer['layer_id'],region['id']]=layer,raw,region
    rows=deepcopy(source['records']);evidence=[]
    for row in rows:
        mesh=row['mesh']
        if not mesh or not mesh['qa'] or len(mesh['bone_ids'])!=3:continue
        layer,raw,region=lookup[row['layer_id'],row['component_id']]
        if hashlib.sha256(isolated_png(raw,region)).hexdigest()!=row['isolated_image_sha256']:
            raise ValueError('parent_distal_mask_mismatch')
        chain=[bones[b] for b in mesh['bone_ids']];measurement=measure(region,layer['bbox'],chain)[1]
        if not measurement['sample_count']:continue
        # Reuse existing solver with its parent-segment cap; constant factor, no per-character search.
        trial,parameters=reweight(mesh,chain,{'transverse_radius_px':measurement['transverse_radius']},2)
        trial['qa']=evaluate(trial['vertices_xy'],trial['triangles'],trial['weights'],chain)
        trial['status']='candidate_requires_review' if trial['qa']['passed'] and not trial['raster_qa']['uncovered_alpha_pixels'] else 'blocked'
        trial['reason_codes']=['experimental_parent_distal_weights','binding_not_adopted']
        if trial['status']=='blocked':trial['reason_codes'].append('partition_deformation_qa_failed')
        row.update(mesh=trial,status=trial['status'],reason_codes=trial['reason_codes'])
        evidence.append(dict(layer_id=row['layer_id'],component_id=row['component_id'],measurement=measurement,
                             parameters=parameters,before_qa=mesh['qa'],trial_qa=trial['qa']))
    return dict(schema='autospine.component-parent-distal/v1',profile='alpha-parent-capped-distal-factor2-v1',
                project_id=source['project_id'],source_sha256=canonical_sha256(source),skeleton_sha256=canonical_sha256(skeleton),
                records=rows,evidence=evidence,authority='none',production_authorized=False,runtime_status='not_evaluated')


def export(state,output,source,entries,inputs):
    from ...benchmark.mesh_storage import publish_mesh_report,read_mesh_report,export_mesh
    from .component_mesh_review import render
    document=build(source,entries,inputs.skeleton);inputs.assert_current()
    digest=publish_mesh_report(state,'project-component-partitions',document)
    checked=read_mesh_report(state,'project-component-partitions',digest)
    if checked!=build(source,entries,inputs.skeleton):raise ValueError('parent_distal_replay_mismatch')
    inputs.assert_current();export_mesh(output/f'{digest}.json',checked)
    page=render(checked,inputs.skeleton,fk=True).replace('<main>',f'<p>固定因子2、前臂/小腿长度限制的末端权重候选，尚未采用。<a href="{digest}.json">完整数据</a></p><main>')
    (output/'distal.html').write_text(page,encoding='utf-8')
    return checked
