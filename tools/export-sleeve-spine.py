"""Export geometry-admitted R3-S regions with exact isolated textures and target QA."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
from autospine_workbench.project_store import ProjectStore
from autospine_workbench.automation.animated_inputs import load_inputs
from autospine_workbench.benchmark.mesh_storage import read_mesh_report
from autospine_workbench.asset.planning.component_partitions import build as partition
from autospine_workbench.asset.planning.component_mesh import isolated_png
from autospine_workbench.targets.spine43.sleeve_deform import compile_region
from autospine_workbench.targets.spine43.continuous_pose import world
from autospine_workbench.benchmark.elbow_target_cli import archive,export
from autospine_workbench.resolved_project import canonical_sha256
from autospine_workbench.manifest_artifacts import require_safe_token


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--state-root',type=Path,default=Path('workspace'));p.add_argument('--workspace',type=Path,default=Path('..'))
    p.add_argument('projects',nargs='+');a=p.parse_args();store=ProjectStore(a.workspace,a.state_root)
    encode=lambda d:json.dumps(d,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
    for project in a.projects:
        require_safe_token(project,'project');page=(a.input/project/'index.html').read_text(encoding='utf-8')
        sha=re.search(r'href="([a-f0-9]{64})\.json"',page).group(1)
        read=lambda s:read_mesh_report(a.state_root,'project-component-partitions',s)
        source=read(sha);garment=source
        for _ in range(16):
            if garment['schema']=='autospine.sleeve-weights/v1':break
            garment=read(garment['source_sha256'])
        if garment['schema']!='autospine.sleeve-weights/v1' or source['project_id']!=project:raise ValueError('sleeve_export_source')
        meshes={(r['layer_id'],r['component_id']):r for r in garment['records']};results=[]
        with load_inputs(store,project) as inputs:
            layers={r['layer_id']:r for r in inputs.candidate['layers']}
            for row in source['records']:
                result=dict(layer_id=row['layer_id'],component_id=row['component_id'],status='blocked');results.append(result)
                if 'tracks' not in row or any(t['failed_ticks'] for t in row['tracks']):
                    result['reason_code']='motion_envelope_geometry_failure';continue
                saved=meshes[row['layer_id'],row['component_id']];layer=layers[row['layer_id']];raw=inputs.images[row['layer_id']]
                parts=partition(layer,raw);region=next(r for r in parts['components']+[parts['residual']] if r['id']==row['component_id'])
                image=isolated_png(raw,region)
                if hashlib.sha256(image).hexdigest()!=saved['isolated_image_sha256']:raise ValueError('sleeve_export_texture_mismatch')
                doc,qa=compile_region(source,row,saved['mesh'],inputs.skeleton);result['target_qa']=qa
                if not qa['passed']:result['reason_code']='target_interpolation_geometry_failure';continue
                name=row['layer_id']+'-'+row['component_id'];w=layer['bbox'][2]-layer['bbox'][0];h=layer['bbox'][3]-layer['bbox'][1]
                doc['skins'][0]['attachments'][name][name].update(width=w,height=h)
                atlas=f'images/{name}.png\nsize: {w},{h}\nfilter: Linear,Linear\npma: false\nrepeat: none\n{name}\nbounds: 0,0,{w},{h}\n'
                files={'skeleton.json':encode(doc),'skeleton.atlas':atlas.encode(),f'images/{name}.png':image}
                result.update(status='candidate_exported',reason_code='runtime_and_alpha_contact_required',files={k:hashlib.sha256(v).hexdigest() for k,v in files.items()})
                inputs.assert_current();out=a.output/project/name;out.mkdir(parents=True,exist_ok=True)
                for filename,data in files.items():
                    export(out/filename,data)
                export(out/'candidate.zip',archive(files))
                reference={}
                for animation in doc['animations']:
                    probe=deepcopy(doc);probe['animations']={animation:doc['animations'][animation]}
                    reference[animation]=[dict(time=i/128,points=world(probe,i/128)[name]) for i in range(257)]
                export(out/'numeric-reference.json',encode(dict(skeleton_sha256=hashlib.sha256(files['skeleton.json']).hexdigest(),animations=reference)))
            inputs.assert_current()
        report=dict(schema='autospine.sleeve-export-report/v1',source_sha256=sha,project_id=project,records=results,authority='none',production_authorized=False)
        export(a.output/project/(canonical_sha256(report)+'.json'),encode(report))
        print(json.dumps(report),flush=True)


if __name__=='__main__':main()
