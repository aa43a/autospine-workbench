"""Run complete source-axis window sweeps against exact successful candidates."""
import argparse
import json
from copy import deepcopy
from pathlib import Path
from m4_direction_stage_probe import load_stages
from m4_support_window_verify import verify
from autospine_workbench.targets.character43.support_window_sequence import build
from autospine_workbench.targets.character43.support_row_tracks import apply
from autospine_workbench.targets.character43.motion_contacts import schedule


def run(job, folder, feedback=None):
    fitted, final, pose, review, files, artifact, motion = load_stages(job)
    contact = json.loads(files['motion-contact.json']); original = contact['phase_attempt']['rows']
    times=[];feedback_evidence=None
    if feedback is not None:
        from m4_support_feedback import load
        times,feedback_evidence=load(feedback,job,artifact)
        measured=deepcopy(motion)
        if contact['hypothesis']['ticks_per_second']!=motion['ticks_per_second']:
            raise ValueError('support_feedback_tick_rate_mismatch')
        measured['markers']=deepcopy(contact['hypothesis']['markers'])
        baseline_times=schedule(measured,[r['time'] for r in original])
        times=schedule(measured,sorted(set(baseline_times)|set(times)))
    def progress(row):
        print(json.dumps(dict(job=job, window=row['window'],status=row['status'])),flush=True)
    rows, report = build(fitted,'external-motion',original,contact['phase_attempt']['anchors'],
                        review['reference_length_px'],progress=progress,extra_times=times)
    report.update(job_id=job,parent_artifact_sha256=artifact,candidate_rows=rows)
    if feedback_evidence is not None:report.update(verification_time_grid=times,feedback=feedback_evidence)
    report['verification'] = verify(fitted,final,motion,pose,contact,report,review['reference_length_px'])
    check = report['verification']
    report['ready_for_mesh_rebuild'] = bool(report['accepted_windows'] and check['contact_after']['passed']
                                          and check['contact_not_increased'] and check['support_limits_passed'])
    (folder/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    if report['ready_for_mesh_rebuild']:
        (folder/'bone-candidate.json').write_text(json.dumps(apply(fitted,'external-motion',rows)),encoding='utf-8')
    print(json.dumps(dict(job=job,accepted=report['accepted_windows'],ready=report['ready_for_mesh_rebuild'],
                         contact=check['contact_after']['max_drift_px'],speed=check['rotation_speed_deg'])),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('output',type=Path);p.add_argument('jobs',nargs='+')
    p.add_argument('--feedback',type=Path)
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
    if a.feedback is not None and len(a.jobs)!=1:raise ValueError('feedback_requires_one_exact_job')
    for job in a.jobs:
        folder=a.output/job;folder.mkdir();run(job,folder,a.feedback)
