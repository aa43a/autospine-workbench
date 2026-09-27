"""Create an isolated full-animation diagnostic retaining source and time identity."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.targets.character43.limb_transverse_repair import build as compensate
from autospine_workbench.targets.character43.joint_boundary_animation import build
from m4_transverse_timeline_screen import validate_times


def run(state,artifact,slot,source,output):
    raw=(source/'report.json').read_bytes();declaration=json.loads(raw)
    times=json.loads((source/'validation-times.json').read_bytes())
    validate_times(declaration,times,artifact,slot)
    output.mkdir(parents=True,exist_ok=False)
    parent=json.loads(AnimatedStore(state).read(artifact)['skeleton.json'])
    candidate,compensation=compensate(parent,'external-motion',[slot],correction_frame='transverse',anchor_terminal=True)
    def progress(value):
        (output/'progress.json').write_bytes(canonical_bytes(value));print(json.dumps(value),flush=True)
    result,report=build(parent,candidate,'external-motion',slot,times,progress=progress)
    skeleton=canonical_bytes(result)
    report.update(parent_artifact_sha256=artifact,slot=slot,source_sha256=sha256(raw).hexdigest(),
                  skeleton_sha256=sha256(skeleton).hexdigest(),compensation=compensation)
    (output/'skeleton.json').write_bytes(skeleton)
    (output/'report.json').write_bytes(canonical_bytes(report))
    progress(dict(stage='complete',local_constraints_passed=report['local_constraints_passed'],
                  keys=report['key_count'],samples=len(report['times']),failures=len(report['failures'])))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('state',type=Path);p.add_argument('artifact');p.add_argument('slot')
    p.add_argument('source',type=Path);p.add_argument('output',type=Path)
    a=p.parse_args();run(a.state,a.artifact,a.slot,a.source,a.output)
