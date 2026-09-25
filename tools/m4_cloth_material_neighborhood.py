"""Track a bounded source-material neighborhood; never infer GPU visibility."""
import argparse
from collections import Counter
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import numpy as np
from PIL import Image
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.targets.character43.affine_pose import sample
from autospine_workbench.targets.character43.skirt_motion_contact import locate, transport
from autospine_workbench.targets.character43.sliding_material_support import nearest
from m4_cloth_limb_coupling_probe import coverage


def anchors(points, triangles, center, radius=4, step=2):
    if radius < 0 or radius > 16 or step <= 0 or radius % step:
        raise ValueError('material_neighborhood_grid')
    rows=[]
    for dy in range(-radius, radius+1, step):
        for dx in range(-radius, radius+1, step):
            point=[center[0]+dx, center[1]+dy]
            try: anchor=locate(points, triangles, point)
            except ValueError:
                rows.append(dict(offset=[dx,dy], source=point, anchor=None));continue
            rows.append(dict(offset=[dx,dy], source=point, anchor=anchor))
    return rows


def classify(limb_alpha, source_alpha, current_alpha, support):
    if limb_alpha < 8:return 'low_alpha_limb_material'
    if source_alpha < 8:return 'originally_uncovered_material'
    if current_alpha >= 8:return 'currently_cloth_covered_material'
    return 'bounded_sliding_support' if support else 'no_bounded_sliding_support'


def duration(value):
    if isinstance(value, list):return max((duration(v) for v in value),default=0.)
    if isinstance(value, dict):
        return max([float(value.get('time',0.))]+[duration(v) for k,v in value.items() if k!='time'])
    return 0.


def run(source, evidence_path, output, times):
    if output.exists():raise ValueError('material_neighborhood_output_exists')
    receipt=json.loads((source/'report.json').read_bytes())
    files=AnimatedStore(source/'isolated-store').read(receipt['candidate_bundle_sha256'])
    evidence=json.loads(evidence_path.read_bytes());setup=json.loads(files['rig-setup-reference.json'])
    digest=sha256(files['skeleton.json']).hexdigest()
    if (evidence['candidate_bundle_sha256']!=receipt['candidate_bundle_sha256'] or
        evidence['skeleton_sha256']!=digest or setup['skeleton_sha256']!=digest):
        raise ValueError('material_neighborhood_identity')
    doc=json.loads(files['skeleton.json'])
    end=duration(doc['animations']['external-motion'])
    times=sorted(set(times+[evidence['time']]))
    if not times or len(times)>9 or not all(np.isfinite(t) and 0<=t<=end for t in times):
        raise ValueError('material_neighborhood_times')
    slots=doc['skins'][0]['attachments']
    limb,cloth=evidence['limb'],evidence['cloth'];lm,cm=slots[limb][limb],slots[cloth][cloth]
    def texture(mesh, slot):
        return Image.open(BytesIO(files['images/'+mesh.get('path',slot)+'.png'])).convert('RGBA')
    lt,ct=texture(lm,limb),texture(cm,cloth)
    seeds=[r for r in evidence['rows'] if r['exposure_kind']=='newly_exposed_source_covered_material']
    if len(seeds)!=1:raise ValueError('material_neighborhood_seed_count')
    grid=anchors(setup['vertices'][limb],lm['triangles'],seeds[0]['source_material_world'])
    for row in grid:
        row['limb_alpha']=coverage(lm,setup['vertices'][limb],lt,row['source'])
        row['source_cloth_alpha']=coverage(cm,setup['vertices'][cloth],ct,row['source'])
    frames=[]
    for time in times:
        posed=sample(doc,'external-motion',time)[0];rows=[]
        for index,row in enumerate(grid):
            if row['anchor'] is None:
                rows.append(dict(sample=index,status='outside_limb_mesh'));continue
            world=transport(posed[limb],row['anchor'])
            alpha=coverage(cm,posed[cloth],ct,world);support=None;reason=None
            if row['limb_alpha']>=8 and row['source_cloth_alpha']>=8 and alpha<8:
                support=nearest(cm,posed[cloth],ct,world)
                if support is None:
                    try:locate(posed[cloth],cm['triangles'],world)
                    except ValueError:reason='outside_current_cloth_mesh'
                    else:reason='no_opaque_support_within_declared_search'
            rows.append(dict(sample=index,world=world,current_cloth_alpha=alpha, support=support,unsupported_reason=reason,
                status=classify(row['limb_alpha'],row['source_cloth_alpha'],alpha,support)))
        frames.append(dict(time=time,counts=dict(Counter(r['status'] for r in rows)),rows=rows))
    result=dict(schema='autospine.material-neighborhood/v1',candidate_bundle_sha256=receipt['candidate_bundle_sha256'],
        skeleton_sha256=digest,evidence_sha256=sha256(evidence_path.read_bytes()).hexdigest(),
        limb=limb,cloth=cloth,grid=grid,frames=frames,authority='none',selected=False,
        scope='source_material_grid_cpu_alpha_and_local_support_not_gpu_visibility_or_joint_feasibility',
        limits=dict(source_radius_px=4,source_step_px=2,support_texture_radius_px=8,support_world_distance_px=8))
    output.write_bytes(canonical_bytes(result))
    print(json.dumps([dict(time=f['time'],counts=f['counts']) for f in frames]),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for name in ('source','evidence','output'):p.add_argument(name,type=Path)
    p.add_argument('--time',type=float,action='append',default=[])
    a=p.parse_args();run(a.source,a.evidence,a.output,a.time)
