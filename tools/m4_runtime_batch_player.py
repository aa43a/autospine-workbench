"""Give a batch-verified animation one viewport covering all capture bounds."""
import argparse
from hashlib import sha256
import json
import math
from pathlib import Path
from autospine_workbench.automation.storage_io import canonical_bytes
from m4_runtime_batch_audit import audit


def viewport(infos):
    if not infos:raise ValueError('batch_player_viewports_empty')
    for info in infos:
        if any(not math.isfinite(info[k]) for k in ('left','bottom','width','height')) or min(info['width'],info['height'])<=0:
            raise ValueError('batch_player_viewport_invalid')
    left=min(r['left'] for r in infos);bottom=min(r['bottom'] for r in infos)
    right=max(r['left']+r['width'] for r in infos);top=max(r['bottom']+r['height'] for r in infos)
    return dict(left=left,bottom=bottom,width=right-left,height=top-bottom)


def run(root):
    coverage=audit(root);manifest=json.loads((root/'report.json').read_bytes())
    infos=[json.loads((root/r['folder']/'runtime/report.json').read_bytes())['info'] for r in manifest['batch_records']]
    bounds=viewport(infos);scene_path=root/'batch-000/runtime/player-assets/scene.json'
    scene=json.loads(scene_path.read_bytes())
    if sha256(canonical_bytes(scene['skeleton'])).hexdigest()!=manifest['skeleton_sha256']:
        raise ValueError('batch_player_skeleton_identity')
    scene['info'].update(bounds);scene_path.write_bytes(canonical_bytes(scene))
    result=dict(coverage=coverage,viewport=bounds,source_viewports=[{k:r[k] for k in bounds} for r in infos],
        player='batch-000/runtime/player.html',scene_sha256=sha256(scene_path.read_bytes()).hexdigest(),
        authority='none',selected=False,scope='playback_viewport_union_not_visual_acceptance')
    (root/'player-report.json').write_bytes(canonical_bytes(result))
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);a=p.parse_args()
    print(json.dumps(run(a.root)),flush=True)
