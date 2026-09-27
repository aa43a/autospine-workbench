"""Evaluate one bounded multi-point garment patch on retained material samples."""
import argparse
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
from PIL import Image
import numpy as np
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.targets.character43.affine_pose import sample
from autospine_workbench.targets.character43.skirt_motion_contact import locate,transport
from autospine_workbench.targets.character43.regional_material_support import candidates,assign,solve
from autospine_workbench.asset.planning.component_local_solver import metrics
from m4_cloth_limb_coupling_probe import coverage
from m4_skirt_waist_support import fixed_region,contact_change


def run(source,evidence,guards,waist_source,output,continuous_support=False,refine_report=None,geometry=False):
    receipt=json.loads((source/'report.json').read_bytes())
    files=AnimatedStore(source/'isolated-store').read(receipt['candidate_bundle_sha256'])
    old=json.loads(evidence.read_bytes());doc=json.loads(files['skeleton.json'])
    protected=json.loads(guards.read_bytes())
    if old['candidate_bundle_sha256']!=receipt['candidate_bundle_sha256'] or old['skeleton_sha256']!=sha256(files['skeleton.json']).hexdigest():
        raise ValueError('regional_cloth_identity')
    if any(protected[k]!=old[k] for k in ('candidate_bundle_sha256','skeleton_sha256','limb','cloth')):
        raise ValueError('regional_cloth_guard_identity')
    refinement=None
    if refine_report:
        refinement=json.loads(refine_report.read_bytes())
        if (refinement['source_candidate']!=old['candidate_bundle_sha256'] or refinement['skeleton_sha256']!=old['skeleton_sha256'] or
            refinement['evidence_sha256']!=sha256(evidence.read_bytes()).hexdigest() or
            refinement['guards_sha256']!=sha256(guards.read_bytes()).hexdigest()):
            raise ValueError('regional_cloth_refinement_identity')
    fixed,waist=fixed_region(AnimatedStore(Path('workspace')).read(waist_source),files,old['cloth'])
    setup=sample(dict(doc,animations={'setup':{}}),'setup',0)[0]
    mesh=doc['skins'][0]['attachments'][old['cloth']][old['cloth']]
    tri=np.asarray(mesh['triangles']).reshape(-1,3).tolist()
    texture=Image.open(BytesIO(files['images/'+mesh.get('path',old['cloth'])+'.png'])).convert('RGBA')
    limb=doc['skins'][0]['attachments'][old['limb']][old['limb']]
    anchors=[locate(setup[old['limb']],limb['triangles'],r['source_material_world'])
             for r in protected['rows'] if r['exposure_kind']=='previously_visible_limb_material']
    if not anchors:raise ValueError('regional_cloth_visible_guard_missing')
    frames=[];points={}
    for frame in old['frames']:
        time=frame['time'];world=sample(doc,'external-motion',time)[0];posed=world[old['cloth']]
        exposed=[r for r in frame['rows'] if r['status'] in ('bounded_sliding_support','no_bounded_sliding_support')]
        item=dict(time=time,exposed_samples=[r['sample'] for r in exposed],before=metrics(setup[old['cloth']],posed,tri))
        if not exposed:item.update(status='no_exposed_samples');frames.append(item);continue
        groups=[candidates(mesh,posed,texture,r['world']) for r in exposed]
        if continuous_support:
            from autospine_workbench.targets.character43.material_reachability import inspect
            alpha=np.asarray(texture.getchannel('A'),float);continuous=[]
            for row,group in zip(exposed,groups):
                if group:continue
                check=inspect(mesh,posed,alpha,row['world'],threshold=128)
                continuous.append(dict(sample=row['sample'],**check))
                if check['status']=='material_witness_within_budget':
                    witness=check['witness'];group.append(dict(witness,pixel=witness['texture_point'],
                        support_kind='continuous_bilinear_alpha_128'))
            item['continuous_support']=continuous
        item['support_counts']=[len(g) for g in groups]
        item['unsupported_samples']=[r['sample'] for r,g in zip(exposed,groups) if not g]
        supported=[(r,g) for r,g in zip(exposed,groups) if g]
        if not supported:item.update(status='missing_regional_support');frames.append(item);continue
        # Unsupported points stay in the independent all-point coverage check below.
        # A partial fit is diagnostic only; no target silently disappears from acceptance.
        try:selected=assign([g for r,g in supported])
        except ValueError as error:item.update(status=str(error));frames.append(item);continue
        failed=None if refinement is None else {r['sample'] for f in refinement['frames'] if f['time']==time for r in f.get('coverage',[]) if not r['passed']}
        exact=[i for i,s in enumerate(selected) if s.get('support_kind')=='continuous_bilinear_alpha_128' and (failed is None or supported[i][0]['sample'] in failed)]
        corrected,field=solve(setup[old['cloth']],posed,tri,selected,[r['world'] for r,g in supported],fixed,exact=exact,geometry=geometry)
        item.update(supports=selected,movement=field)
        if corrected is None:item.update(status='joint_solver_rejected');frames.append(item);continue
        quality=metrics(setup[old['cloth']],corrected,tri)
        checks=[]
        for row in frame['rows']:
            if 'world' not in row:continue
            alpha=coverage(mesh,corrected,texture,row['world']);original=old['grid'][row['sample']]
            target=original['limb_alpha']>=8 and original['source_cloth_alpha']>=8
            preserved=original['limb_alpha']>=8 and original['source_cloth_alpha']<8
            checks.append(dict(sample=row['sample'],before=row['current_cloth_alpha'],after=alpha,
                required_coverage=target,required_uncovered=preserved,
                passed=(alpha>=8 if target else alpha<8 if preserved else True)))
        waist_error=contact_change(posed,corrected,waist['anchors'])
        guard_checks=[]
        for anchor in anchors:
            query=transport(world[old['limb']],anchor)
            before=coverage(mesh,posed,texture,query);after=coverage(mesh,corrected,texture,query)
            guard_checks.append(dict(before=before,after=after,world=query,passed=after<8 if before<8 else after<=before+1e-7))
        passed=not quality['bad_triangles'] and quality['max_edge_stretch']<=2 and waist_error<=1e-7 and all(r['passed'] for r in checks+guard_checks)
        item.update(status='sampled_patch_passed' if passed else 'sampled_patch_failed',after=quality,coverage=checks,visible_limb_guards=guard_checks,waist_error_px=waist_error)
        points[str(time)]=corrected;frames.append(item)
        print(json.dumps(dict(time=time,status=item['status'],maximum_displacement_px=field['maximum_displacement_px'],
                             coverage_failed=sum(not r['passed'] for r in checks),geometry_failed=len(quality['bad_triangles']))),flush=True)
    report=dict(profile='regional-cloth-material-patch-v1',source_candidate=old['candidate_bundle_sha256'],
        skeleton_sha256=old['skeleton_sha256'],evidence_sha256=sha256(evidence.read_bytes()).hexdigest(),
        guards_sha256=sha256(guards.read_bytes()).hexdigest(),
        waist_source=waist_source,waist_support=waist,frames=frames,authority='none',selected=False,
        animation_modified=False,candidate_generated=False,posed_cloth_sha256=sha256(canonical_bytes(points)).hexdigest(),
        support_mode='discrete_and_continuous_alpha128' if continuous_support else 'discrete_opaque_neighborhood',
        refinement_report_sha256=None if refine_report is None else sha256(refine_report.read_bytes()).hexdigest(),geometry_constraints=geometry,
        limits=dict(world_support_px=8,texture_search_px=8,vertex_displacement_px=8,neighborhood_rings=3),
        scope='retained_material_grid_at_declared_poses_not_animation_or_visual_acceptance')
    output.mkdir(parents=True,exist_ok=False)
    (output/'report.json').write_bytes(canonical_bytes(report));(output/'posed-cloth.json').write_bytes(canonical_bytes(points))
    print(json.dumps([dict(time=r['time'],status=r['status'],unsupported=r.get('unsupported_samples',[])) for r in frames]),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('source',type=Path);p.add_argument('evidence',type=Path);p.add_argument('guards',type=Path)
    p.add_argument('waist_source');p.add_argument('output',type=Path)
    p.add_argument('--continuous-support',action='store_true')
    p.add_argument('--refine-report',type=Path);p.add_argument('--geometry-constraints',action='store_true')
    a=p.parse_args();run(a.source,a.evidence,a.guards,a.waist_source,a.output,a.continuous_support,a.refine_report,a.geometry_constraints)
