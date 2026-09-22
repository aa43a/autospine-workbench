"""Probe a fixed-end neighborhood of each real worst leg direction sample."""
import argparse
import json
from pathlib import Path
from m4_direction_stage_probe import load_stages
from autospine_workbench.targets.character43.motion_direction_audit import audit
from autospine_workbench.targets.character43.support_window_optimizer import optimize


def run(job, folder, preserve_endpoint=False):
    fitted, final, pose, review, files, artifact, motion = load_stages(job)
    audit_report = audit(final, 'external-motion', pose['vectors'], pose['times'])
    worst = max((r['worst_direction'] for r in audit_report['records'] if r['bone'].startswith(('calf','thigh'))),
                key=lambda r:r['error_deg'])
    contact = json.loads(files['motion-contact.json']); attempt = contact['phase_attempt']
    rows = attempt['rows']
    center = min(range(len(rows)), key=lambda i:abs(rows[i]['time']-worst['time']))
    selected = rows[max(0, center-16):center+17]
    changed, report = optimize(fitted, 'external-motion', selected, attempt['anchors'], review['reference_length_px'],
                               preserve_endpoint=preserve_endpoint)
    report.update(job_id=job, parent_artifact_sha256=artifact, target_time=worst['time'],
                  original_rows=selected, candidate_rows=changed,
                  scope='local_temporal_window_not_complete_clip_mesh_or_runtime_validation')
    if report['status'] == 'candidate':
        from m4_support_window_verify import verify
        report['full_fk_verification'] = verify(fitted,final,motion,pose,contact,report,review['reference_length_px'])
    (folder/'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k not in ('original_rows','candidate_rows','full_fk_verification')}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path); parser.add_argument('jobs', nargs='+')
    parser.add_argument('--preserve-endpoint',action='store_true')
    args = parser.parse_args(); args.output.mkdir(parents=True, exist_ok=False)
    for job in args.jobs:
        folder = args.output/job; folder.mkdir(); run(job, folder,args.preserve_endpoint)
