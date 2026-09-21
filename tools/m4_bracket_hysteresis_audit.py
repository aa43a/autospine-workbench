"""Verify every held label belongs to an equally bracketed ambiguous run."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
from autospine_workbench.automation.storage_io import canonical_bytes
from m4_surface_trace_audit import audit as surface_audit
from m4_temporal_label_audit import transition_context


def audit(trace,before,after):
    coverage=surface_audit(trace,after)
    previous_raw=(before/'report.json').read_bytes();old=json.loads(previous_raw)
    new=json.loads((after/'report.json').read_bytes())
    for key in ('parent_report_sha256','source_artifact_sha256','observations_sha256','held_setup_pairs'):
        if old[key]!=new[key]:raise ValueError('bracket_audit_source_changed')
    a=json.loads((before/'inference.json').read_bytes());b=json.loads((after/'inference.json').read_bytes())
    if set(a)!=set(b):raise ValueError('bracket_audit_arm_inventory')
    results=[]
    for arm,models in a.items():
        if set(models)!=set(b[arm]):raise ValueError('bracket_audit_body_inventory')
        actual=set()
        for body,frames in models.items():
            if len(frames)!=len(b[arm][body]):raise ValueError('bracket_audit_frame_inventory')
            for j,(x,y) in enumerate(zip(frames,b[arm][body])):
                for key in ('time','source_tick','observed_states','unresolved_triangles'):
                    if x[key]!=y[key]:raise ValueError('bracket_audit_evidence_changed')
                if x['labels']!=y['pre_bracket_labels']:raise ValueError('bracket_audit_prior_changed')
                for i,(s,v,w) in enumerate(zip(x['observed_states'],x['labels'],y['labels'])):
                    if v!=w:
                        if s!='A':raise ValueError('bracket_audit_nonambiguous_changed')
                        actual.add((body,j,i))
        receipt=next(r for r in new['bracket_hysteresis'] if r['arm']==arm);declared=set()
        for run in receipt['runs']:
            body=run['body'];rows=models[body];start,end=run['start'],run['end'];i=run['triangle']
            if not 0<start<end<len(rows):raise ValueError('bracket_audit_run_range')
            state=rows[start-1]['observed_states'][i]
            if state not in 'FB' or state!=rows[end]['observed_states'][i]:raise ValueError('bracket_audit_boundary')
            if any(rows[j]['observed_states'][i]!='A' or b[arm][body][j]['labels'][i]!=int(state=='F')
                   for j in range(start,end)):raise ValueError('bracket_audit_run_content')
            expected=[j for j in range(start,end) if rows[j]['labels'][i]!=int(state=='F')]
            if expected!=run['changed_indices']:raise ValueError('bracket_audit_changed_indices')
            declared.update((body,j,i) for j in expected)
        if actual!=declared or len(actual)!=receipt['changed_labels']:raise ValueError('bracket_audit_change_receipt')
        results.append(dict(arm=arm,changed_ambiguous_labels=len(actual),changed_runs=len(receipt['runs']),
                            run_counts=receipt['run_counts'],nonambiguous_labels_changed=0))
    old_failures={f['time']:f['reason_code'] for f in old['order']['failures']}
    new_failures={f['time']:f['reason_code'] for f in new['order']['failures']}
    comparable=all(r.get('strict_interval_evidence') and r.get('relation_pair_count',0)>0 for r in (old,new))
    introduced=sorted(new_failures.keys()-old_failures.keys()) if comparable else None
    regression=dict(status='not_comparable' if not comparable else 'reject_regression' if introduced else 'no_new_sampled_failures',
                    introduced_failure_times=introduced,
                    resolved_failure_times=sorted(old_failures.keys()-new_failures.keys()) if comparable else None,
                    adoption_allowed=False)
    return dict(profile='source-bound-bracket-hysteresis-audit-v1',coverage=coverage,arms=results,regression_guard=regression,
                previous_report_sha256=sha256(previous_raw).hexdigest(),previous_failure_counts=old['failure_counts'],
                remaining_transition_context=transition_context(new,b),authority='none',selected=False,runtime_recaptured=False)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('trace','before','after','output'):p.add_argument(name,type=Path)
    args=p.parse_args();result=audit(args.trace,args.before,args.after)
    args.output.write_bytes(canonical_bytes(result));print(json.dumps(result))
