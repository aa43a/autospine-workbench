"""Compare parent-relative floors at explicitly selected diagnostic poses."""
import argparse
import json
from hashlib import sha256
from pathlib import Path
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.targets.character43.limb_transverse_repair import build
from autospine_workbench.targets.character43.parent_pose_area_repair import compare


def run(state_root, artifact, slot, times, output, regressions=None, protect_setup=False, correction_frame='world', local_refinement=False, exact_poses=False, anchor_terminal=False, terminal_transition=None, distal_gain=1.):
    source=None
    if regressions is not None:
        raw=regressions.read_bytes();report=json.loads(raw)
        if report['parent_artifact_sha256']!=artifact or report['slot']!=slot:
            raise ValueError('parent_probe_regression_source_mismatch')
        times=sorted({r['time'] for r in report['failures'] if not r['fixed'] and r['regressed']})
        source=dict(sha256=sha256(raw).hexdigest(),selection='all_movable_regression_worst_times')
    if not times:raise ValueError('parent_probe_times_required')
    parent=json.loads(AnimatedStore(state_root).read(artifact)['skeleton.json'])
    candidate,compensation=build(parent,'external-motion',[slot],correction_frame=correction_frame,
                                  required_times=times if exact_poses else (),anchor_terminal=anchor_terminal,terminal_transition=terminal_transition,distal_gain=distal_gain)
    rows=[]
    for time in times:
        row=compare(parent,candidate,'external-motion',slot,time,protect_setup=protect_setup,local_refinement=local_refinement);rows.append(row)
        policies=('parent','transverse','projected_only','parent_floor')+(('parent_setup_floor',) if protect_setup else ())
        print(json.dumps(dict(time=time,results={key:{k:len(v) if isinstance(v,list) else v for k,v in row[key].items()
            if k not in ('setup_ratios','solver')} for key in policies})),flush=True)
    with output.open('xb') as handle:
        handle.write(canonical_bytes(dict(parent_artifact_sha256=artifact,rows=rows,regression_source=source,
            compensation=compensation,
            authority='none',selected=False,scope='selected_counterexample_poses_only')))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('state_root',type=Path);parser.add_argument('artifact');parser.add_argument('slot')
    parser.add_argument('output',type=Path)
    group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--times',nargs='+',type=float);group.add_argument('--regressions',type=Path)
    parser.add_argument('--protect-setup',action='store_true')
    parser.add_argument('--correction-frame',choices=('world','transverse'),default='world')
    parser.add_argument('--local-refinement',action='store_true')
    parser.add_argument('--exact-poses',action='store_true')
    parser.add_argument('--anchor-terminal',action='store_true')
    parser.add_argument('--terminal-transition',type=float)
    parser.add_argument('--distal-gain',type=float,default=1.)
    args=parser.parse_args();run(args.state_root,args.artifact,args.slot,args.times,args.output,args.regressions,args.protect_setup,args.correction_frame,args.local_refinement,args.exact_poses,args.anchor_terminal,args.terminal_transition,args.distal_gain)
