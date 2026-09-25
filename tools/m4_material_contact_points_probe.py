"""Compare vertex constraints with exact source-material landmarks, without edits."""
import argparse
from hashlib import sha256
import json
import math
from pathlib import Path
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.targets.character43.shoulder_source import contexts
from autospine_workbench.targets.character43.shoulder_contact_regions import prepare_regions
from autospine_workbench.targets.character43.shoulder_region_validation import resolve_owners
from autospine_workbench.targets.character43.material_contact_points import bind, sample as sample_material
from autospine_workbench.targets.character43.affine_pose import sample
from autospine_workbench.targets.character43.material_affine_frame import fit
from autospine_workbench.targets.character43.numeric_reference import read
from autospine_workbench.targets.character43.skirt_contact import source_image
from autospine_workbench.targets.character43.skirt_candidate import inverse


def run(source, output, times):
    receipt=json.loads((source/'report.json').read_bytes()); identity=receipt['candidate_bundle_sha256']
    files=AnimatedStore(source/'isolated-store').read(identity); doc,rows=contexts(files)
    reference=read(files)['animations']['external-motion']
    if not times or any(not math.isfinite(t) or not reference[0]['time']<=t<=reference[-1]['time'] for t in times):
        raise ValueError('material_contact_probe_time_invalid')
    prepared=[(row,prepare_regions(row)) for row in rows]; owners=resolve_owners(prepared)
    setup=sample(dict(doc,animations={'setup':{}}),'setup',0)[0]
    records=[]
    for row,p in prepared:
        locations=[d['center'] for d in p['support']]
        image,origin=source_image(files,doc,setup,owners[row['slot']]);alpha=image.getchannel('A')
        def alpha_at(point):
            x=math.floor(point[0]-origin[0]+.5);y=math.floor(origin[1]-point[1]+.5)
            return alpha.getpixel((x,y)) if 0<=x<alpha.width and 0<=y<alpha.height else 0
        source_alpha=[alpha_at(point) for point in locations]
        if any(value<8 for value in source_alpha):raise ValueError('material_contact_reference_alpha_missing')
        binding=bind(row['points'],row['triangles'],locations)
        actual=sample_material(binding,row['points'],row['triangles'])
        ratios=[math.dist(row['points'][d['vertex']],d['center'])/d['radius'] for d in p['support']]
        frames=[]
        for time in times:
            world=sample(doc,'external-motion',time)[0]
            transform,residual=fit(setup[owners[row['slot']]],world[owners[row['slot']]])
            a,b,c,d,x,y=transform
            targets=[[a*u+b*v+x,c*u+d*v+y] for u,v in locations]
            moved=sample_material(binding,world[row['slot']],row['triangles'])
            frames.append(dict(time=time,material_fit_residual_px=residual,
                points=moved,reference_points=targets,
                owner_alpha_nearest=[alpha_at(inverse(transform,point)) for point in moved],
                displacement_from_reference_px=[math.dist(p,q) for p,q in zip(moved,targets,strict=True)]))
        records.append(dict(slot=row['slot'],owner=owners[row['slot']],landmarks=binding,
            source_owner_alpha=source_alpha,
            old_constraint_setup_ratios=ratios,old_constraint_setup_outside=sum(v>1+1e-7 for v in ratios),
            setup_reconstruction_error_px=max(math.dist(p,q) for p,q in zip(actual,locations,strict=True)),
            unsupported_vertex_ids=p['locked'],frames=frames))
    report=dict(candidate=identity,skeleton_sha256=sha256(files['skeleton.json']).hexdigest(),
        profile='material-contact-point-diagnostic-v1',records=records,selected=False,authority='none',
        scope='landmark_positions_only_not_sliding_alpha_coverage_or_visual_acceptance')
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('x',encoding='utf8') as f:json.dump(report,f,ensure_ascii=False,indent=2,allow_nan=False)
    print(json.dumps([dict(slot=r['slot'],landmarks=len(r['landmarks']['records']),
        old_setup_outside=r['old_constraint_setup_outside'],setup_error=r['setup_reconstruction_error_px'],
        unsupported=r['unsupported_vertex_ids'],peak_displacement=max(max(f['displacement_from_reference_px']) for f in r['frames'])) for r in records]))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source',type=Path);parser.add_argument('output',type=Path)
    parser.add_argument('--time',type=float,action='append',required=True)
    args=parser.parse_args();run(args.source,args.output,args.time)
