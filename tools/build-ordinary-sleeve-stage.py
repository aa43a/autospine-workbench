"""Recoverable ordinary repair/deform/interpolation stages using explicit saved inputs."""
import argparse
from pathlib import Path
from autospine_workbench.project_store import ProjectStore
from autospine_workbench.automation.animated_inputs import load_inputs
from autospine_workbench.automation.ordinary_sleeve_stage import read_stage
from autospine_workbench.benchmark.mesh_storage import read_mesh_report,publish_mesh_report,export_mesh
from autospine_workbench.manifest_artifacts import require_safe_token


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage',required=True,choices=['repair','deform','interpolation'])
    parser.add_argument('--input',required=True,type=Path);parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--state-root',type=Path,default=Path('workspace'))
    parser.add_argument('--workspace',type=Path,default=Path('..'));parser.add_argument('project')
    args=parser.parse_args();require_safe_token(args.project,'project')
    read=lambda sha:read_mesh_report(args.state_root,'project-component-partitions',sha)
    current=read_stage(args.input,args.project,args.state_root)
    with load_inputs(ProjectStore(args.workspace.resolve(),args.state_root.resolve()),args.project) as inputs:
        if args.stage=='repair':
            from autospine_workbench.asset.planning.ordinary_sleeve_repair import build,HARMONIC_PROFILE
            source=current;draft=read(source['draft_sha256'])
            report=build(source,draft,inputs.skeleton,profile=HARMONIC_PROFILE);html=None
        elif args.stage=='deform':
            from autospine_workbench.asset.planning.ordinary_sleeve_deform import build
            from autospine_workbench.asset.planning.ordinary_sleeve_deform_review import render
            repair=current;source=read(repair['source_sha256']);draft=read(repair['draft_sha256'])
            report=build(repair,source,draft,inputs.skeleton)
            html=render(report,repair=repair,source=source,draft=draft,skeleton=inputs.skeleton)
        else:
            from autospine_workbench.asset.planning.ordinary_deform_interpolation import build
            deform=current;repair=read(deform['repair_sha256']);source=read(deform['source_sha256']);draft=read(deform['draft_sha256'])
            report=build(deform,repair=repair,source=source,draft=draft,skeleton=inputs.skeleton);html=None
        inputs.assert_current()
        sha=publish_mesh_report(args.state_root,'project-component-partitions',report)
        if read(sha)!=report:raise ValueError('sleeve_ordinary_stage_readback')
        output=args.output/args.project;output.mkdir(parents=True,exist_ok=True)
        export_mesh(output/(sha+'.json'),report)
        if html:(output/'index.html').write_text(html,encoding='utf-8')
        print(sha,flush=True)


if __name__=='__main__':main()
