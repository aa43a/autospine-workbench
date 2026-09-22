"""Build synchronized explicit-yaw experiments on exact character/source requests."""
import argparse
import json
from pathlib import Path
from m4_source_pose_probe import run as pose_probe
from m4_source_pose_mesh import run as mesh_probe
from m4_experiment_player_export import export


def run(output,jobs,labels=None):
    if labels is not None and len(labels)!=len(jobs):raise ValueError('comparison_label_count')
    output.mkdir(parents=True,exist_ok=False);rows=[]
    for index,job in enumerate(jobs):
        pairs=[]
        for yaw in (0,45):
            relative=Path(str(index))/('yaw-'+str(yaw));folder=output/relative
            receipt=pose_probe(job,folder/'pose',yaw)
            mesh_probe(folder/'pose',folder/'mesh',capture=True)
            report=json.loads((folder/'mesh/report.json').read_bytes())
            export(folder/'mesh')
            pairs.append(dict(yaw=yaw,url=(relative/'mesh/runtime/player.html').as_posix(),
                artifact=report['candidate_bundle_sha256'],geometry_passed=report['geometry_passed'],
                runtime_status=report['runtime_status'],frames=report['sampled_frames'],
                scope='limbs_only_torso_root_artwork_not_reprojected',
                unreliable_samples=sum(len(r['unreliable_frames']) for r in receipt['records'])))
            print(json.dumps(dict(job=job,**pairs[-1])),flush=True)
        rows.append(dict(job=job,label=labels[index] if labels else job,views=pairs))
    (output/'comparison.json').write_text(json.dumps(dict(authority='none',selected=False,rows=rows),indent=2),encoding='utf-8')
    for source,target in [('m4-reach-comparison.html','index.html'),('m4-reach-comparison.js','comparison.js')]:
        (output/target).write_bytes((Path('tools')/source).read_bytes())


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('output',type=Path);p.add_argument('jobs',nargs='+')
    p.add_argument('--labels',nargs='+')
    a=p.parse_args();run(a.output,a.jobs,a.labels)
