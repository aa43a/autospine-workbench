"""Probe semantic sleeve contacts in exact exported poses; no GPU claim."""
import argparse
import hashlib
import json
from pathlib import Path
from autospine_workbench.benchmark.mesh_storage import read_mesh_report
from autospine_workbench.benchmark.elbow_target_cli import export
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.safe_input_files import read_real_file,strict_json_object
from autospine_workbench.resolved_project import canonical_sha256
from autospine_workbench.manifest_artifacts import require_safe_token
from autospine_workbench.targets.spine43.seam_raster import texture
from autospine_workbench.targets.spine43.sleeve_contact_samples import probes,analyze
from autospine_workbench.targets.spine43.continuous_pose import world
from autospine_workbench.automation.sleeve_motion_inventory import motion_names, metadata, evidence_schema, frame_count


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--state-root',type=Path,default=Path('workspace'));p.add_argument('projects',nargs='+');args=p.parse_args()
    def read(path):return strict_json_object(read_real_file(path,128<<20,'contact input'),'contact input')
    repo=Path(__file__).resolve().parents[1]
    algorithms=[Path(__file__).resolve()]+[repo/'src/autospine_workbench/targets/spine43'/name for name in ('sleeve_contact_samples.py','continuous_pose.py','seam_raster.py')]
    algorithms.append(repo/'src/autospine_workbench/asset/planning/sleeve_motion_envelope.py')
    algorithms.append(repo/'src/autospine_workbench/automation/sleeve_motion_inventory.py')
    identity=lambda:{path.relative_to(repo).as_posix():hashlib.sha256(path.read_bytes()).hexdigest() for path in algorithms}
    engine=identity()
    for project in args.projects:
        require_safe_token(project,'project');root=args.input/project;reports=list(root.glob('*.json'))
        if len(reports)!=1:raise ValueError('sleeve_contact_export_inventory')
        source=read(reports[0])
        if (reports[0].stem!=canonical_sha256(source) or source['schema'] not in ('autospine.sleeve-export-report/v1','autospine.sleeve-export-report/v2')
                or source['project_id']!=project or source['authority']!='none' or source['production_authorized'] is not False):raise ValueError('sleeve_contact_source')
        envelope=read_mesh_report(args.state_root,'project-component-partitions',source['source_sha256']);garment=envelope
        for _ in range(16):
            if garment['schema']=='autospine.sleeve-weights/v1':break
            garment=read_mesh_report(args.state_root,'project-component-partitions',garment['source_sha256'])
        if garment['schema']!='autospine.sleeve-weights/v1':raise ValueError('sleeve_contact_lineage')
        draft=read_mesh_report(args.state_root,'project-component-partitions',garment['draft_sha256'])
        if any(d['project_id']!=project or d['authority']!='none' or d['production_authorized'] is not False for d in (envelope,garment,draft)):
            raise ValueError('sleeve_contact_lineage')
        labels={(r['layer_id'],r['component_id']):r['assignments'] for r in draft['records']};rows=[]
        for row in source['records']:
            if row['status']!='candidate_exported':continue
            name=row['layer_id']+'-'+row['component_id'];bundle=root/name;files={}
            require_safe_token(name,'sleeve region')
            for filename,digest in row['files'].items():
                path=bundle/filename
                if bundle.resolve() not in path.resolve().parents:raise ValueError('sleeve_contact_path')
                raw=read_real_file(path,128<<20,'contact asset')
                if hashlib.sha256(raw).hexdigest()!=digest:raise ValueError('sleeve_contact_asset_changed')
                files[filename]=raw
            doc=strict_json_object(files['skeleton.json'],'skeleton')
            if source['schema'].endswith('/v2') and doc.get('skeleton',{}).get('hash')!=row.get('motion_source_sha256'):
                raise ValueError('sleeve_contact_motion_source')
            if set(doc['animations'])!=set(motion_names(source,row)):raise ValueError('sleeve_contact_motion_inventory')
            animations={}
            count=frame_count(source,row); rate=(count-1)/2
            for animation in doc['animations']:
                pose_doc=dict(doc,animations={animation:doc['animations'][animation]})
                animations[animation]=[dict(time=i/rate,points=world(pose_doc,i/rate)[name]) for i in range(count)]
            attachment=doc['skins'][0]['attachments'][name][name];alpha=texture(files['images/'+name+'.png'])
            result=analyze(attachment,alpha,probes(attachment,labels[row['layer_id'],row['component_id']],alpha,profile='source-length-v2'),animations)
            result['probe_profile']='source-length-v2'
            result.update(metadata(source,row))
            result.update(layer_id=row['layer_id'],component_id=row['component_id'],asset_sha256=row['files'],pose_sha256=canonical_sha256(animations))
            rows.append(result);print(project,name,result['status'],result['tested_samples'],result['failed_samples'],flush=True)
        result=dict(schema=evidence_schema(source,'sleeve-contact-coverage'),project_id=project,source_sha256=canonical_sha256(source),draft_sha256=garment['draft_sha256'],
            records=rows,algorithm_files=engine,authority='none',production_authorized=False,framebuffer_status='not_evaluated')
        if identity()!=engine:raise ValueError('sleeve_contact_code_changed')
        export(args.output/project/(canonical_sha256(result)+'.json'),canonical_bytes(result))


if __name__=='__main__':main()
