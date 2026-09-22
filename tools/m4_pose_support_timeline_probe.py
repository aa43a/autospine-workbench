"""Validate source-axis support over exact source clips without publishing it."""
import argparse
from copy import deepcopy
import json
from pathlib import Path

from m4_direction_stage_probe import load_stages
from autospine_workbench.targets.character43.support_timeline import build
from autospine_workbench.targets.character43.motion_contacts import analyze, schedule
from autospine_workbench.targets.character43.motion_direction_audit import audit


def run(job, output, *, matched_contact=False):
    fitted, final, pose, review, files, artifact, motion = load_stages(job)
    contact = json.loads(files['motion-contact.json'])
    measured = deepcopy(motion)
    hypothesis = contact['hypothesis']
    if hypothesis['ticks_per_second'] != motion['ticks_per_second']:
        raise ValueError('support_probe_tick_rate_mismatch')
    measured['markers'] = deepcopy(hypothesis['markers'])
    reference = review['reference_length_px']
    residual = min(.01*reference, contact['after']['max_drift_px']) if matched_contact else 1e-4
    candidate, report = build(fitted, 'external-motion', measured, pose['times'], reference,
                               preserve_pose=True, maximum_error_px=residual)
    result = dict(profile='source-axis-support-timeline-probe-v1', job_id=job,
                  parent_artifact_sha256=artifact, selected=False, authority='none', support=report,
                  requested_endpoint_limit_px=residual,
                  scope='bone_timeline_experiment_without_mesh_runtime_or_visual_acceptance')
    if candidate is not None:
        times = schedule(measured, [r['time'] for r in report['rows']])
        old = analyze(final, 'external-motion', measured, times, reference)
        new = analyze(candidate, 'external-motion', measured, times, reference)
        result.update(original_contact=old, candidate_contact=new,
            contact_maximum_not_increased=new['max_drift_px'] <= old['max_drift_px'],
            original_direction=audit(final, 'external-motion', pose['vectors'], pose['times']),
            candidate_direction=audit(candidate, 'external-motion', pose['vectors'], pose['times']))
        (output/'skeleton.json').write_text(json.dumps(candidate), encoding='utf-8')
    (output/'report.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(dict(job=job, status=report['status'], rows=len(report['rows']),
        failure=report.get('failure'), contact=result.get('candidate_contact', {}).get('max_drift_px'),
        contact_maximum_not_increased=result.get('contact_maximum_not_increased'))), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('jobs', nargs='+')
    parser.add_argument('--matched-contact', action='store_true')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    for job in args.jobs:
        folder = args.output/job
        folder.mkdir()
        run(job, folder, matched_contact=args.matched_contact)
