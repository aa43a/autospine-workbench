"""Compare bone-only and actual-material shoulder support at explicit times."""
import argparse
from hashlib import sha256
import json
import math
from pathlib import Path

from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.targets.character43.affine_pose import sample, matrices
from autospine_workbench.targets.character43.material_affine_frame import fit
from autospine_workbench.targets.character43.shoulder_source import contexts
from autospine_workbench.targets.character43.shoulder_contact_regions import prepare_regions, constraints, solve
from autospine_workbench.targets.character43.torso_projection_candidate import multiply
from autospine_workbench.targets.character43.skirt_contact import source_image
from autospine_workbench.targets.character43.numeric_reference import read


def run(source, output, owner, times, perform_solve=False, continuation=False, harmonic_seed=False):
    if (continuation or harmonic_seed) and not perform_solve:raise ValueError('material_contact_seed_requires_solve')
    if continuation and harmonic_seed:raise ValueError('material_contact_seed_selection')
    receipt=json.loads((source/'report.json').read_bytes());identity=receipt['candidate_bundle_sha256']
    files=AnimatedStore(source/'isolated-store').read(identity);doc,rows=contexts(files)
    frames=read(files)['animations']['external-motion']
    if not times or any(not math.isfinite(t) or not frames[0]['time'] <= t <= frames[-1]['time'] for t in times):
        raise ValueError('material_contact_time_outside_candidate')
    manifest=json.loads(files['character-manifest.json'])
    eligible={r['region_id'] for layer in manifest['layers'] if layer['name'] in ('topwear','topwear-front')
              and layer['state']=='rigid_reviewed' for r in layer['regions']}
    if owner not in eligible:raise ValueError('material_contact_owner_not_reviewed_torso')
    setup=sample(dict(doc,animations={'setup':{}}),'setup',0)[0]
    image,origin=source_image(files,doc,setup,owner);alpha=image.getchannel('A')
    for row in rows:
        for x,y in row['contact']:
            px,py=x-origin[0],origin[1]-y
            if not (0 <= px < alpha.width and 0 <= py < alpha.height and alpha.getpixel((px,py)) >= 8):
                raise ValueError('material_contact_multiple_owners_require_separate_regions')
    rest=matrices(dict(doc,animations={'setup':{}}),'setup',0)['chest']
    prepared=[(row,prepare_regions(row)) for row in rows];records=[]
    for time in times:
        world=sample(doc,'external-motion',time)[0];bone=matrices(doc,'external-motion',time)['chest']
        material,residual=fit(setup[owner],world[owner]);effective=multiply(material,rest)
        for row,p in prepared:
            fixed,before=constraints(row,p,rest,bone,world[row['slot']])
            corrected,after=constraints(row,p,rest,effective,world[row['slot']])
            peak=max([math.dist(a['center'],b['center']) for a,b in zip(before,after)]+
                     [math.dist(fixed[v],corrected[v]) for v in p['locked']]+[0.])
            record=dict(slot=row['slot'],time=time,owner=owner,material_fit_residual_px=residual,
                        maximum_support_shift_px=peak,material_frame=list(material),
                        region_count=len(after),locked_count=len(p['locked']))
            if perform_solve:
                if continuation:
                    from autospine_workbench.targets.character43.boundary_contact_continuation import solve as continue_solve
                    points,evidence=continue_solve(row['points'],row['triangles'],world[row['slot']],corrected,
                                                  p['free'],after,p['context']['budget_px'])
                elif harmonic_seed:
                    from autospine_workbench.targets.character43.material_anchor_field import solve as field
                    from autospine_workbench.targets.character43.boundary_shape_feasible import refine
                    targets={v:corrected[v] for v in p['locked']}
                    targets.update({r['vertex']:r['center'] for r in after})
                    seed,seed_evidence=field(row['points'],world[row['slot']],row['triangles'],targets,
                                             sorted(set(p['free'])|set(p['locked'])))
                    points,evidence=refine(row['points'],row['triangles'],corrected,p['free'],world[row['slot']],
                                           seed,p['context']['budget_px'],regions=after)
                    evidence['seed']=seed_evidence
                    if evidence['status']!='feasible_candidate':points=world[row['slot']]
                else:points,evidence=solve(row,p,rest,effective,world[row['slot']])
                record.update(solver=evidence,points=points)
            records.append(record)
            print(json.dumps({k:v for k,v in record.items() if k!='points'}),flush=True)
    output.mkdir(parents=True,exist_ok=False)
    solver_path=Path('src/autospine_workbench/targets/character43/boundary_shape_feasible.py')
    (output/'report.json').write_bytes(canonical_bytes(dict(source_candidate=identity,
        skeleton_sha256=sha256(files['skeleton.json']).hexdigest(),records=records,authority='none',selected=False,
        solver_worktree_sha256=sha256(solver_path.read_bytes()).hexdigest() if perform_solve else None,
        scope='selected_pose_material_support_probe_not_baked_candidate_or_acceptance')))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('source',type=Path);p.add_argument('output',type=Path)
    p.add_argument('--owner',required=True);p.add_argument('--time',type=float,action='append',required=True)
    p.add_argument('--solve',action='store_true');strategy=p.add_mutually_exclusive_group()
    strategy.add_argument('--continuation',action='store_true');strategy.add_argument('--harmonic-seed',action='store_true')
    a=p.parse_args();run(a.source,a.output,a.owner,a.time,a.solve,a.continuation,a.harmonic_seed)
