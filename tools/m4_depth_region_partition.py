"""Build an isolated render-partition prototype and verify sampled vertex identity."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import re

from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import read_document
from autospine_workbench.targets.character43.depth_region_partition import build
from autospine_workbench.targets.character43.affine_pose import sample


def run(job, slots, output):
    if not re.fullmatch(r'motion-[a-f0-9]{32}', job):
        raise ValueError('job_invalid')
    root = Path('workspace')
    result = read_document(root/'jobs/motion-intake-v1'/job/'result.json')['result']
    files = AnimatedStore(root).read(result['artifact_sha256'])
    document = json.loads(files['skeleton.json'])
    candidate, report = build(document, slots)
    depth = json.loads(files['motion-depth.json'])
    ticks = sorted({r['tick'] for p in depth['pairs'] for r in p['samples']})
    if not ticks or len(ticks) > 512:
        raise ValueError('partition_sample_scope_invalid')
    times = sorted({t/1e6 for t in ticks} | {(a+b)/2e6 for a,b in zip(ticks,ticks[1:])})
    peak = 0.
    for time in times:
        before = sample(document, 'external-motion', time)[0]
        after = sample(candidate, 'external-motion', time)[0]
        for row in report['regions']:
            a, b = before[row['source_slot']], after[row['slot']]
            if len(a) != len(b):
                raise ValueError('partition_vertex_count_changed')
            peak = max(peak, max(abs(x-y) for p,q in zip(a,b) for x,y in zip(p,q)))
    if peak != 0:
        raise ValueError('partition_vertex_position_changed')
    encoded = json.dumps(candidate, ensure_ascii=False, separators=(',', ':')).encode()
    report.update(source_job_id=job, source_artifact_sha256=result['artifact_sha256'],
                  skeleton_sha256=sha256(encoded).hexdigest(), sampled_frames=len(times),
                  max_vertex_error=peak, runtime_status='not_run', depth_order_status='unchanged')
    output.mkdir(parents=True, exist_ok=True)
    (output/'skeleton.json').write_bytes(encoded)
    (output/'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(dict(regions=len(report['regions']), sampled_frames=len(times), max_vertex_error=peak)))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('job'); parser.add_argument('output', type=Path)
    parser.add_argument('--slot', action='append', required=True)
    args = parser.parse_args()
    run(args.job, args.slot, args.output)
