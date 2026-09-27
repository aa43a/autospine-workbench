"""Screen the entire saved diagnostic grid without relaxing key storage limits."""
import argparse
from hashlib import sha256
import json
import math
from pathlib import Path
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.targets.character43.transverse_gain_feasibility import screen
from m4_transverse_gain_screen import prepare_poses


def validate_times(report, times, artifact, slot):
    if report['parent_artifact_sha256']!=artifact or report['slot']!=slot:
        raise ValueError('timeline_screen_source_mismatch')
    if not times or any(not math.isfinite(t) or t<0 for t in times) or times[0]!=0:
        raise ValueError('timeline_screen_times_invalid')
    if any(a>=b for a,b in zip(times,times[1:])):
        raise ValueError('timeline_screen_time_order')
    if sha256(canonical_bytes(times)).hexdigest()!=report['times_sha256']:
        raise ValueError('timeline_screen_time_identity')


def run(state, artifact, slot, source, output, boundary_rings=0, gains=None):
    raw=(source/'report.json').read_bytes();report=json.loads(raw)
    times=json.loads((source/'validation-times.json').read_bytes())
    validate_times(report,times,artifact,slot)
    document=json.loads(AnimatedStore(state).read(artifact)['skeleton.json'])
    gains=[i/32 for i in range(33)] if gains is None else sorted(gains)
    trials=[dict(gain=g,failures=[]) for g in gains];covered=[]
    for start in range(0,len(times),256):
        batch=times[start:start+256]
        result=screen(prepare_poses(document,slot,batch,boundary_rings),gains)
        for target,row in zip(trials,result['trials'],strict=True):
            if target['gain']!=row['gain']:raise ValueError('timeline_screen_gain_order')
            target['failures'].extend(row['failures'])
        covered.extend(batch)
        print(json.dumps(dict(checked=len(covered),total=len(times))),flush=True)
    if covered!=times:raise ValueError('timeline_screen_coverage')
    unexcluded=[r['gain'] for r in trials if not r['failures']]
    result=dict(profile='full-grid-constant-gain-necessary-screen-v1',
        parent_artifact_sha256=artifact,slot=slot,source_sha256=sha256(raw).hexdigest(),
        times_sha256=report['times_sha256'],times=times,poses=len(times),trials=trials,
        unexcluded_gains=unexcluded,suggested_gain=max(unexcluded) if unexcluded else None,
        boundary_rings=boundary_rings,
        authority='none',selected=False,production_authorized=False,
        scope='all_saved_grid_times_not_continuous_solution_or_runtime_acceptance')
    with output.open('xb') as handle:handle.write(canonical_bytes(result))
    print(json.dumps({k:v for k,v in result.items() if k not in ('times','trials')}))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('state',type=Path);parser.add_argument('artifact');parser.add_argument('slot')
    parser.add_argument('source',type=Path);parser.add_argument('output',type=Path)
    parser.add_argument('--boundary-rings',type=int,default=0)
    parser.add_argument('--gains',nargs='+',type=float)
    args=parser.parse_args();run(args.state,args.artifact,args.slot,args.source,args.output,args.boundary_rings,args.gains)
