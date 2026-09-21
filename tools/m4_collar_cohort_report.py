"""Verify cross-character proximal-ring evidence against prior collar candidates."""
import argparse
import json
from pathlib import Path
from autospine_workbench.automation.animated_store import AnimatedStore

CELLS=[('alice','squat-alice-collar-v1','squat-alice-proximal-ring-v1'),
       ('hongmeiling','squat-ankle-collar-full-v1','squat-hongmeiling-proximal-ring-v1'),
       ('huiye','squat-huiye-collar-v1','squat-huiye-proximal-ring-v1')]


def load(path):
    report=json.loads((path/'report.json').read_bytes())
    files=AnimatedStore(path/'isolated-store').read(report['candidate_bundle_sha256'])
    return report,files,json.loads(files['skeleton.json'])


def run(root,output):
    rows=[]
    for name,old,new in CELLS:
        before,bf,bd=load(root/old);after,af,ad=load(root/new)
        if before['source_candidate_sha256']!=after['source_candidate_sha256']:raise ValueError('collar_cohort_source_changed')
        if {k:v for k,v in bd.items() if k!='animations'}!={k:v for k,v in ad.items() if k!='animations'}:
            raise ValueError('collar_cohort_setup_changed')
        if bd['animations']['external-motion']['bones']!=ad['animations']['external-motion']['bones']:
            raise ValueError('collar_cohort_bone_tracks_changed')
        textures=lambda f:{k:v for k,v in f.items() if k.endswith('.png') or k=='skeleton.atlas'}
        if textures(bf)!=textures(af):raise ValueError('collar_cohort_textures_changed')
        runtime=json.loads((root/new/'runtime/report.json').read_bytes())
        if runtime['bundle_sha256']!=after['candidate_bundle_sha256'] or not runtime['passed'] or len(runtime['results'])!=after['sampled_frames']:
            raise ValueError('collar_cohort_capture_mismatch')
        correction=json.loads((root/new/'correction.json').read_bytes())
        for r in correction['records']:
            if r['max_displacement_px']>r['budget_px']+1e-7:raise ValueError('collar_cohort_budget_exceeded')
        rows.append(dict(character=name,previous_candidate=before['candidate_bundle_sha256'],
            candidate=after['candidate_bundle_sha256'],sampled_frames=after['sampled_frames'],
            previous_inversions=before['sampled_inversions'],inversions=after['sampled_inversions'],
            projected_area_failures=after['projected_area_failure_samples'],
            ankle_drift_px=after['maximum_ankle_drift_px'],geometry_passed=after['original_geometry_passed'],
            contact_passed=after['contact_passed'],runtime_numeric_passed=runtime['passed'],
            depth_status=after['depth_status'],unchanged_setup_bones_textures=True))
    report=dict(profile='proximal-ring-three-character-regression-v1',authority='none',selected=False,
        rows=rows,total_sampled_frames=sum(r['sampled_frames'] for r in rows),
        limitations=['different_sample_grids_not_direct_error_rate_comparison',
                     'runtime_numeric_not_visual_acceptance','knee_skirt_depth_not_checked'])
    with output.open('x',encoding='utf-8') as f:json.dump(report,f,indent=2)
    print(json.dumps(report))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('root',type=Path);p.add_argument('output',type=Path)
    a=p.parse_args();run(a.root,a.output)
