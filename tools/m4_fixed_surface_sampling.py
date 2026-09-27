import argparse
from hashlib import sha256
import json
from pathlib import Path
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.targets.character43.fixed_surface_sampling import build


def run(state,artifact,slot,source,output,rounds=6):
    raw=source.read_bytes();report=json.loads(raw)
    if report['parent_artifact_sha256']!=artifact or report['slot']!=slot:raise ValueError('fixed_sampling_source')
    parent=json.loads(AnimatedStore(state).read(artifact)['skeleton.json'])
    output.mkdir(parents=True,exist_ok=False)
    def progress(row):
        (output/'progress.json').write_bytes(canonical_bytes(row));print(json.dumps(row),flush=True)
    result,evidence=build(parent,'external-motion',slot,report['times'],progress=progress,rounds=rounds)
    skeleton=canonical_bytes(result)
    evidence.update(parent_artifact_sha256=artifact,slot=slot,source_sha256=sha256(raw).hexdigest(),
                    skeleton_sha256=sha256(skeleton).hexdigest())
    (output/'skeleton.json').write_bytes(skeleton);(output/'report.json').write_bytes(canonical_bytes(evidence))
    print(json.dumps(dict(status=evidence['status'],samples=len(evidence['times']))))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('state',type=Path);p.add_argument('artifact');p.add_argument('slot')
    p.add_argument('source',type=Path);p.add_argument('output',type=Path)
    p.add_argument('--rounds',type=int,default=6)
    a=p.parse_args();run(a.state,a.artifact,a.slot,a.source,a.output,a.rounds)
