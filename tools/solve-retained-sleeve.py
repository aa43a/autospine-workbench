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
from autospine_workbench.asset.planning.sleeve_corrective_backtrack import backtrack
from autospine_workbench.asset.planning.sleeve_connection_domain import domain
from autospine_workbench.asset.planning.sleeve_regions import validate


def reviewed_domains(state,source):
    ancestor=source
    for _ in range(32):
        if 'draft_sha256' in ancestor:break
        ancestor=read_mesh_report(state,'project-component-partitions',ancestor['source_sha256'])
    else:raise ValueError('retained_solver_draft_ancestry')
    draft=read_mesh_report(state,'project-component-partitions',ancestor['draft_sha256'])
    candidate=read_mesh_report(state,'project-component-partitions',draft['candidate_sha256'])
    validate(draft,candidate)
    if draft['project_id']!=source['project_id'] or candidate['skeleton_sha256']!=source['skeleton_sha256']:
        raise ValueError('retained_solver_draft_identity')
    meshes={(r['layer_id'],r['component_id']):r for r in candidate['records']}
    labels={(r['layer_id'],r['component_id']):r for r in draft['records']}
    result={}
    for row in source['records']:
        if 'helper' not in row:continue
        key=row['layer_id'],row['component_id'];mesh=meshes[key]
        if mesh['triangles']!=row['triangles'] or mesh['vertices_xy']!=row['setup_vertices']:
            raise ValueError('retained_solver_draft_geometry')
        result[key]=domain(row['triangles'],labels[key]['assignments'])
    return result


def solve_track(candidate,chain,old,*,smooth,blend,passes):
    if passes not in (1,2,3):raise ValueError('retained_solver_passes')
    retained=old;seed_track=old;rounds=[]
    for index in range(passes):
        seeds=None
        if smooth and seed_track['correction_selected']:
            keys=seed_track['trial_keys'];seeds=deepcopy(keys)
            for i in range(1,32):
                seeds[i]=[[.25*keys[i-1][v][k]+.5*keys[i][v][k]+.25*keys[i+1][v][k]
                    for k in (0,1)] for v in range(len(candidate['setup_vertices']))]
        trial=track(candidate,chain,old['bone_id'],old['amplitudes'],key_seeds=seeds)
        # Rejected intermediate keys may seed the next solve, never the output.
        seed_track=dict(trial,correction_selected=True)
        reasons,gain=gate(retained['qa'],trial['qa']);selected=not reasons and gain
        attempts=[]
        if blend and not selected:
            blended,attempts=backtrack(candidate,chain,retained,trial)
            if blended is not retained:trial=blended;reasons=[];selected=True
        rounds.append(dict(round=index+1,selected=selected,reason_codes=reasons,
            baseline_failed_ticks=retained['failed_ticks'],trial_failed_ticks=trial['failed_ticks'],
            solver_trial_failed_ticks=seed_track['trial_failed_ticks'],solver_gate_reasons=seed_track['reason_codes'],backtrack_attempts=attempts))
        if selected:retained=trial
        print(candidate['layer_id'],old['bone_id'],'round',index+1,old['failed_ticks'],retained['failed_ticks'],selected,flush=True)
        if retained['failed_ticks']==0:break
    return retained,dict(track=old['bone_id'],selected=retained is not old,
        baseline_failed_ticks=old['failed_ticks'],retained_failed_ticks=retained['failed_ticks'],rounds=rounds)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--edge-budget',action='store_true',help='Use existing area/edge lower bounds with unchanged cap')
    p.add_argument('--smooth-seed',action='store_true',help='Project neighboring corrective-key averages within the same displacement budget')
    p.add_argument('--blend-backtrack',action='store_true',help='Try three bounded blends when the full correction regresses')
    p.add_argument('--reviewed-domain',action='store_true',help='Rebuild garment freedom from the exact source-linked reviewed draft')
    p.add_argument('--trial-passes',type=int,choices=(1,2,3),default=1,help='Bounded internal iterations; intermediate failures are not retained')
    p.add_argument('--state-root',type=Path,default=Path('workspace'));p.add_argument('--workspace',type=Path,default=Path('..'))
    a=p.parse_args();source=read_mesh_report(a.state_root,'project-component-partitions',a.source)
    if source['schema']!='autospine.sleeve-motion-envelope/v1' or source['authority']!='none' or source['production_authorized'] is not False:raise ValueError('retained_solver_source')
    result=deepcopy(source);result.update(source_sha256=a.source,baseline_sha256=a.source,profile='retained-weights-joint200-v1')
    if a.edge_budget:result['profile']='retained-weights-edge-budget-joint200-v1'
    if a.smooth_seed:result['profile']+='-neighbor-seed-v1'
    if a.blend_backtrack:result['profile']+='-backtrack-v1'
    domains=reviewed_domains(a.state_root,source) if a.reviewed_domain else None
    if domains is not None:result['profile']+='-reviewed-domain-v1'
    result['profile']+=f'-trial-passes{a.trial_passes}-v1'
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
            if domains is not None:candidate['correction_domain']=deepcopy(domains[row['layer_id'],row['component_id']])
            candidate.setdefault('correction_domain',dict(anchors=sorted({v for e in row['interface_root']['edges'] for v in e}),free_vertices=row['cloth_vertices']))
            candidate['correction_domain']['solver_profile']='joint-area-edge-sparse200-v1'
            if a.edge_budget:candidate['correction_domain']['budget_policy']='area-edge-displacement-bound-cap50-v1'
            evidence=[];tracks=[]
            for old in row['tracks']:
                chosen,receipt=solve_track(candidate,chain,old,smooth=a.smooth_seed,blend=a.blend_backtrack,passes=a.trial_passes)
                tracks.append(chosen);evidence.append(receipt)
            row['tracks']=tracks;row['retained_solver_trial']=evidence
            row['retained_solver_domain']=deepcopy(candidate['correction_domain'])
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
