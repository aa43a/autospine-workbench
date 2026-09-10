"""Compare joint correction against exact retained weights, one variable at a time."""
import argparse
from copy import deepcopy
from pathlib import Path
from autospine_workbench.project_store import ProjectStore
from autospine_workbench.automation.animated_inputs import load_inputs
from autospine_workbench.benchmark.mesh_storage import read_mesh_report,publish_mesh_report,export_mesh
from autospine_workbench.asset.planning.sleeve_motion_envelope import track
from autospine_workbench.asset.planning.component_distal_guard import gate
from autospine_workbench.asset.planning.sleeve_helper_review import render
from autospine_workbench.resolved_project import canonical_sha256


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--edge-budget',action='store_true',help='Use existing area/edge lower bounds with unchanged cap')
    p.add_argument('--state-root',type=Path,default=Path('workspace'));p.add_argument('--workspace',type=Path,default=Path('..'))
    a=p.parse_args();source=read_mesh_report(a.state_root,'project-component-partitions',a.source)
    if source['schema']!='autospine.sleeve-motion-envelope/v1' or source['authority']!='none' or source['production_authorized'] is not False:raise ValueError('retained_solver_source')
    result=deepcopy(source);result.update(source_sha256=a.source,baseline_sha256=a.source,profile='retained-weights-joint200-v1')
    if a.edge_budget:result['profile']='retained-weights-edge-budget-joint200-v1'
    import numpy,scipy,platform
    result['solver_environment']=dict(numpy=numpy.__version__,scipy=scipy.__version__,python=platform.python_version())
    with load_inputs(ProjectStore(a.workspace,a.state_root),source['project_id']) as inputs:
        if source['skeleton_sha256']!=canonical_sha256(inputs.skeleton):raise ValueError('retained_solver_skeleton')
        bones={b['id']:b for b in inputs.skeleton['bones']}
        for row in result['records']:
            if 'helper' not in row:continue
            parent=bones[row['helper']['parent_id']];hand=bones[row['tracks'][0]['drivers'][1]]
            chain=[bones[parent['parent_id']],parent,hand,row['helper']]
            candidate=deepcopy(row)
            candidate.setdefault('correction_domain',dict(anchors=sorted({v for e in row['interface_root']['edges'] for v in e}),free_vertices=row['cloth_vertices']))
            candidate['correction_domain']['solver_profile']='joint-area-edge-sparse200-v1'
            if a.edge_budget:candidate['correction_domain']['budget_policy']='area-edge-displacement-bound-cap50-v1'
            evidence=[];tracks=[]
            for old in row['tracks']:
                trial=track(candidate,chain,old['bone_id'],old['amplitudes'])
                reasons,gain=gate(old['qa'],trial['qa']);selected=not reasons and gain
                tracks.append(trial if selected else old)
                evidence.append(dict(track=old['bone_id'],selected=selected,reason_codes=reasons,
                    baseline_failed_ticks=old['failed_ticks'],trial_failed_ticks=trial['failed_ticks'],
                    solver_trial_failed_ticks=trial['trial_failed_ticks'],solver_gate_reasons=trial['reason_codes']))
                print(row['layer_id'],old['bone_id'],old['failed_ticks'],trial['failed_ticks'],selected,flush=True)
            row['tracks']=tracks;row['retained_solver_trial']=evidence
            passed=all(t['failed_ticks']==0 for t in tracks)
            row['motion_envelope']['geometry_pass']=passed
            row['reason_codes']=[r for r in row['reason_codes'] if r!='motion_envelope_geometry_failure']
            if not passed:row['reason_codes'].append('motion_envelope_geometry_failure')
        inputs.assert_current()
        sha=publish_mesh_report(a.state_root,'project-component-partitions',result)
        checked=read_mesh_report(a.state_root,'project-component-partitions',sha)
        a.output.mkdir(parents=True,exist_ok=True);export_mesh(a.output/(sha+'.json'),checked)
        (a.output/'index.html').write_text(render(checked).replace('<main>',f'<a href="{sha}.json">完整工件</a><main>'),encoding='utf-8')
        print(sha,flush=True)


if __name__=='__main__':main()
