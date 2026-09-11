"""Bridge source-closed ordinary deform targets to the existing sleeve evidence workflow."""
import argparse
from copy import deepcopy
import hashlib
from pathlib import Path
from autospine_workbench.project_store import ProjectStore
from autospine_workbench.automation.animated_inputs import load_inputs
from autospine_workbench.automation.ordinary_sleeve_stage import read_stage
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.benchmark.mesh_storage import read_mesh_report,publish_mesh_report,export_mesh
from autospine_workbench.benchmark.elbow_target_cli import export,archive
from autospine_workbench.asset.planning.component_partitions import build as partition
from autospine_workbench.asset.planning.component_mesh import isolated_png
from autospine_workbench.targets.spine43.ordinary_deform import build
from autospine_workbench.targets.spine43.continuous_pose import world
from autospine_workbench.resolved_project import canonical_sha256
from autospine_workbench.manifest_artifacts import require_safe_token

PROFILE='ordinary-deform-local129-quarter513-v1'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',required=True,type=Path);parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--state-root',type=Path,default=Path('workspace'))
    parser.add_argument('--workspace',type=Path,default=Path('..'));parser.add_argument('project')
    args=parser.parse_args();require_safe_token(args.project,'project')
    read=lambda sha:read_mesh_report(args.state_root,'project-component-partitions',sha)
    interpolation=read_stage(args.input,args.project,args.state_root);deform=read(interpolation['deform_sha256'])
    repair,source,draft=[read(deform[k]) for k in ('repair_sha256','source_sha256','draft_sha256')]
    with load_inputs(ProjectStore(args.workspace.resolve(),args.state_root.resolve()),args.project) as inputs:
        target,documents=build(interpolation,deform=deform,repair=repair,source=source,draft=draft,skeleton=inputs.skeleton)
        layers={r['layer_id']:r for r in inputs.candidate['layers']};rows=[];payloads={}
        for checked in target['records']:
            name=checked['layer_id']+'-'+checked['component_id'];require_safe_token(name,'region')
            row=dict(layer_id=checked['layer_id'],component_id=checked['component_id'],status='blocked',
                     reason_code=checked['reason_codes'][0],motion_profile=PROFILE,motion_source_sha256=canonical_sha256(deform))
            rows.append(row)
            if checked['status']!='target_sampled_passed':continue
            doc=documents[checked['target_sha256']];raw=inputs.images[checked['layer_id']];layer=layers[checked['layer_id']]
            parts=partition(layer,raw);region=next(r for r in parts['components']+[parts['residual']] if r['id']==checked['component_id'])
            image=isolated_png(raw,region)
            if hashlib.sha256(image).hexdigest()!=checked['isolated_image_sha256']:raise ValueError('sleeve_ordinary_texture_changed')
            w=layer['bbox'][2]-layer['bbox'][0];h=layer['bbox'][3]-layer['bbox'][1]
            atlas=f'images/{name}.png\nsize: {w},{h}\nfilter: Linear,Linear\npma: false\nrepeat: none\n{name}\nbounds: 0,0,{w},{h}\n'
            files={'skeleton.json':canonical_bytes(doc),'skeleton.atlas':atlas.encode(),f'images/{name}.png':image}
            animations={}
            for animation in doc['animations']:
                probe=deepcopy(doc);probe['animations']={animation:doc['animations'][animation]}
                animations[animation]=[dict(time=i/256,points=world(probe,i/256)[name]) for i in range(513)]
            reference=canonical_bytes(dict(skeleton_sha256=hashlib.sha256(files['skeleton.json']).hexdigest(),animations=animations))
            payloads[name]=(files,reference)
            row.update(status='candidate_exported',reason_code='runtime_and_alpha_contact_required',target_qa=checked['qa'],
                       files={n:hashlib.sha256(v).hexdigest() for n,v in files.items()})
        inputs.assert_current()
        target_sha=publish_mesh_report(args.state_root,'project-component-partitions',target)
        if read(target_sha)!=target:raise ValueError('sleeve_ordinary_target_readback')
        output=args.output/args.project
        for name,(files,reference) in payloads.items():
            for filename,data in files.items():export(output/name/filename,data)
            export(output/name/'numeric-reference.json',reference);export(output/name/'candidate.zip',archive(files))
        # The target report remains separate from the single export inventory.
        (output/'target').mkdir(parents=True,exist_ok=True);export_mesh(output/'target'/(target_sha+'.json'),target)
        report=dict(schema='autospine.sleeve-export-report/v2',source_sha256=canonical_sha256(deform),project_id=args.project,
                    records=rows,authority='none',production_authorized=False)
        export(output/(canonical_sha256(report)+'.json'),canonical_bytes(report))
        print(canonical_sha256(report),flush=True)


if __name__=='__main__':main()
