"""Check exact-source temporal inference changes and the actual graph energy."""
import argparse
from collections import Counter
import json
from pathlib import Path
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.targets.character43.depth_temporal_graph import build
from autospine_workbench.targets.character43.depth_block_cut import energy
from m4_surface_trace_audit import audit as surface_audit


def transition_context(report,models):
    regions={r['slot']:r for r in report['partition']['regions']};output=[]
    for failure in report['order']['failures']:
        if failure['reason_code']!='visible_depth_order_changes_within_interval':continue
        arm,body=failure['pair'];region=regions[arm];body=regions.get(body,{}).get('source_slot',body)
        frames=models[region['source_slot']][body]
        indices=[next(i for i,f in enumerate(frames) if abs(f['time']-s['overlap']['time'])<1e-12)
                 for s in failure['samples']]
        for triangle in region['triangles']:
            def endpoint(sequence):
                for i in sequence:
                    state=frames[i]['observed_states'][triangle]
                    if state in 'UMN':return dict(state=None,stop=state,time=frames[i]['time'])
                    if state in 'FB':return dict(state=state,time=frames[i]['time'])
                return dict(state=None,stop='clip_boundary')
            left=endpoint(range(indices[0],-1,-1));right=endpoint(range(indices[-1],len(frames)))
            kind=('opposite_hard_brackets' if left['state']!=right['state'] else 'same_hard_brackets') if left['state'] and right['state'] else 'incomplete_brackets'
            output.append(dict(pair=failure['pair'],time=failure['time'],source_triangle=triangle,
                               before=left,after=right,classification=kind))
    return output


def audit(trace,before,after):
    coverage=surface_audit(trace,after)
    old=json.loads((before/'report.json').read_bytes());new=json.loads((after/'report.json').read_bytes())
    for key in ('parent_report_sha256','source_artifact_sha256','observations_sha256','held_setup_pairs'):
        if old[key]!=new[key]:raise ValueError('temporal_audit_source_changed')
    a=json.loads((before/'inference.json').read_bytes());b=json.loads((after/'inference.json').read_bytes())
    checks=json.loads((trace/'checks.json').read_bytes())
    document=json.loads(AnimatedStore(Path('workspace')).read(old['source_artifact_sha256'])['skeleton.json'])
    if set(a)!=set(b):raise ValueError('temporal_audit_arm_inventory')
    results=[]
    for arm,models in a.items():
        if set(models)!=set(b[arm]):raise ValueError('temporal_audit_body_inventory')
        changed=Counter()
        for body,frames in models.items():
            if len(frames)!=len(b[arm][body]):raise ValueError('temporal_audit_frame_inventory')
            for x,y in zip(frames,b[arm][body]):
                for key in ('time','source_tick','observed_states','unresolved_triangles'):
                    if x[key]!=y[key]:raise ValueError('temporal_audit_evidence_changed')
                if x['labels']!=y['pre_temporal_labels']:raise ValueError('temporal_audit_prior_changed')
                for s,v,w in zip(x['observed_states'],x['labels'],y['labels']):
                    if v!=w:
                        if s!='A':raise ValueError('temporal_audit_nonambiguous_changed')
                        changed[body]+=1
        nodes,unary,edges=build(document['skins'][0]['attachments'][arm][arm],models,checks,arm)
        labels_before=[models[body][j]['labels'][i] for body,j,i in nodes]
        labels_after=[b[arm][body][j]['labels'][i] for body,j,i in nodes]
        e0,e1=energy(unary,edges,labels_before),energy(unary,edges,labels_after)
        if e1>e0:raise ValueError('temporal_audit_energy_increased')
        record=next(r for r in new['temporal_stabilization'] if r['arm']==arm)
        if record['changed_labels']!=sum(changed.values()):raise ValueError('temporal_audit_change_receipt')
        results.append(dict(arm=arm,changed_ambiguous_labels=dict(changed),energy_before=e0,energy_after=e1,
                            components=record['components'],nonambiguous_labels_changed=0))
    return dict(profile='source-bound-temporal-label-audit-v1',coverage=coverage,arms=results,
                remaining_transition_context=transition_context(new,b),
                previous_failure_counts=old['failure_counts'],authority='none',selected=False,runtime_recaptured=False)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('trace','before','after','output'):p.add_argument(name,type=Path)
    args=p.parse_args();result=audit(args.trace,args.before,args.after)
    args.output.write_bytes(canonical_bytes(result));print(json.dumps(result))
