"""Run complete source-axis window sweeps against exact successful candidates."""
import argparse
import json
from pathlib import Path
from m4_direction_stage_probe import load_stages
from m4_support_window_verify import verify
from autospine_workbench.targets.character43.support_window_sequence import build
from autospine_workbench.targets.character43.support_row_tracks import apply


def run(job, folder):
    fitted, final, pose, review, files, artifact, motion = load_stages(job)
    contact = json.loads(files['motion-contact.json']); original = contact['phase_attempt']['rows']
    def progress(row):
        print(json.dumps(dict(job=job, window=row['window'],status=row['status'])),flush=True)
    rows, report = build(fitted,'external-motion',original,contact['phase_attempt']['anchors'],
                        review['reference_length_px'],progress=progress)
    report.update(job_id=job,parent_artifact_sha256=artifact,candidate_rows=rows)
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
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
    for job in a.jobs:
        folder=a.output/job;folder.mkdir();run(job,folder)
