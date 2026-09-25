"""Bounded source-covered material-following hypothesis at one recorded pose."""
import argparse
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import numpy as np
from PIL import Image
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.targets.character43.affine_pose import sample
from autospine_workbench.targets.character43.deform_addition import entries
from autospine_workbench.targets.character43.material_anchor_field import solve
from autospine_workbench.asset.planning.component_local_solver import metrics
from m4_cloth_limb_coupling_probe import coverage


def run(source,coupling,output,sliding=False):
    if output.exists():raise ValueError('skirt_knee_output_exists')
    receipt=json.loads((source/'report.json').read_bytes());files=AnimatedStore(source/'isolated-store').read(receipt['candidate_bundle_sha256'])
    evidence=json.loads(coupling.read_bytes());setup=json.loads(files['rig-setup-reference.json']);digest=sha256(files['skeleton.json']).hexdigest()
    if evidence['candidate_bundle_sha256']!=receipt['candidate_bundle_sha256'] or evidence['skeleton_sha256']!=digest or setup['skeleton_sha256']!=digest:
        raise ValueError('skirt_knee_identity')
    doc=json.loads(files['skeleton.json']);slot=evidence['cloth'];mesh=doc['skins'][0]['attachments'][slot][slot]
    rest=setup['vertices'][slot];posed=sample(doc,'external-motion',evidence['time'])[0][slot]
    tri=np.asarray(mesh['triangles']).reshape(-1,3).tolist();influences=entries(mesh)
    waist={i for i,row in enumerate(influences) if any(doc['bones'][b]['name']=='chest' and w>0 for b,w in row)}
    candidates=[r for r in evidence['rows'] if r['exposure_kind']=='newly_exposed_source_covered_material']
    if len(candidates)!=1:raise ValueError('skirt_knee_single_supported_sample_required')
    query=candidates[0];matches=[]
    for index,ids in enumerate(tri):
        a,b,c=np.asarray(rest)[ids];matrix=np.column_stack((b-a,c-a))
        if abs(np.linalg.det(matrix))<1e-12:continue
        w=np.linalg.solve(matrix,np.asarray(query['source_material_world'])-a);w=np.r_[1-w.sum(),w]
        if min(w)>=-1e-8:matches.append((index,ids,w))
    if len(matches)!=1:raise ValueError('skirt_knee_material_triangle_ambiguous')
    index,ids,w=matches[0]
    texture=Image.open(BytesIO(files['images/'+mesh.get('path',slot)+'.png'])).convert('RGBA')
    support=None
    if sliding:
        from autospine_workbench.targets.character43.sliding_material_support import nearest
        support=nearest(mesh,posed,texture,np.asarray(query['current_world']))
        if support is None:raise ValueError('skirt_knee_no_bounded_sliding_support')
        index,ids,w=support['triangle'],support['vertices'],np.asarray(support['weights'])
    if not sliding and waist&set(ids):raise ValueError('skirt_knee_anchor_overlaps_waist')
    current=w@np.asarray(posed)[ids];delta=np.asarray(query['current_world'])-current
    moving=set(ids)
    for _ in range(3):moving|={v for t in tri if moving&set(t) for v in t}
    moving-=waist
    if sliding:
        from autospine_workbench.targets.character43.sliding_material_support import targets
        try:anchors=targets(posed,ids,w,waist,delta)
        except ValueError as error:
            if str(error) not in {'sliding_material_fixed_support','sliding_material_displacement_budget'}:raise
            result=dict(source_candidate=evidence['candidate_bundle_sha256'],skeleton_sha256=digest,
                time=evidence['time'],cloth=slot,sliding_support=support,error=str(error),
                support_bones={str(v):[{ 'bone':doc['bones'][b]['name'],'weight':weight} for b,weight in influences[v]] for v in ids},
                fixed_support_vertices=sorted(waist&set(ids)),candidate_generated=False,
                authority='none',selected=False,scope='sliding_support_feasibility_not_visual_acceptance')
            output.mkdir();(output/'report.json').write_bytes(canonical_bytes(result))
            print(json.dumps(result),flush=True);return
    else:anchors={v:(np.asarray(posed[v])+delta).tolist() for v in ids}
    points,field=solve(rest,posed,tri,anchors,sorted(moving))
    quality=metrics(rest,points,tri)
    comparisons=[dict(pixel=r['pixel'],kind=r['exposure_kind'],before=r['current_cloth_alpha'],
                      after=coverage(mesh,points,texture,r['current_world'])) for r in evidence['rows']]
    preserved=all(r['after']<8 for r in comparisons if r['kind']=='previously_visible_limb_material')
    result=dict(source_candidate=evidence['candidate_bundle_sha256'],skeleton_sha256=digest,time=evidence['time'],
        hypothesis='current_boundary_sliding_support' if sliding else 'source_covered_cloth_material_follows_knee_with_fixed_waist',cloth=slot,triangle=index,
        sliding_support=support,
        source_point=query['source_material_world'],current_material_point=current.tolist(),target=query['current_world'],
        movement=field,geometry=quality,coverage=comparisons,visible_limb_preserved=preserved,
        waist_error_px=max((float(np.linalg.norm(np.asarray(points[v])-posed[v])) for v in waist),default=0),
        passed=not quality['bad_triangles'] and quality['max_edge_stretch']<=2 and preserved and
               all(r['after']>=128 for r in comparisons if r['kind']=='newly_exposed_source_covered_material'),
        authority='none',selected=False,scope='one_material_sample_one_pose_not_garment_collision_or_visual_acceptance')
    output.mkdir();(output/'posed-cloth.json').write_bytes(canonical_bytes(points));(output/'report.json').write_bytes(canonical_bytes(result))
    print(json.dumps(result),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for n in ('source','coupling','output'):p.add_argument(n,type=Path)
    p.add_argument('--sliding',action='store_true')
    a=p.parse_args();run(a.source,a.coupling,a.output,a.sliding)
