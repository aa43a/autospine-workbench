"""Export the exact audited transverse curve with a viewport spanning every batch."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
from autospine_workbench.automation.storage_io import canonical_bytes
from m4_transverse_batch_audit import audit
from m4_experiment_player_export import export
from m4_runtime_batch_player import viewport


def run(state,probe,root):
    coverage=audit(state,probe,root)
    if coverage['runtime_status']!='passed':raise ValueError('transverse_player_runtime_required')
    manifest=json.loads((root/'report.json').read_bytes())
    if not manifest['rows']:raise ValueError('transverse_player_batches_missing')
    row=manifest['rows'][0];folder=root/row['folder']
    infos=[json.loads((root/r['folder']/'runtime/report.json').read_bytes())['info'] for r in manifest['rows']]
    bounds=viewport(infos)
    export(folder,candidate_bundle_sha256=row['candidate_bundle_sha256'])
    scene_path=folder/'runtime/player-assets/scene.json';scene=json.loads(scene_path.read_bytes())
    if sha256(canonical_bytes(scene['skeleton'])).hexdigest()!=manifest['skeleton_sha256']:
        raise ValueError('transverse_player_skeleton_identity')
    scene['info'].update(bounds);scene_path.write_bytes(canonical_bytes(scene))
    report=dict(coverage=coverage,viewport=bounds,player=f"{row['folder']}/runtime/player.html",
        skeleton_sha256=manifest['skeleton_sha256'],scene_sha256=sha256(scene_path.read_bytes()).hexdigest(),
        authority='none',selected=False,production_authorized=False,
        pending_checks=['contact','depth','visual'],scope='audited_curve_playback_not_visual_acceptance')
    (root/'player-report.json').write_bytes(canonical_bytes(report))
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('state','probe','root'):parser.add_argument(name,type=Path)
    args=parser.parse_args();print(json.dumps(run(args.state,args.probe,args.root)))
