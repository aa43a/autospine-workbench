"""Measure exact-artifact diagnostic reuse, retaining content verification on hits."""
from argparse import ArgumentParser
from hashlib import sha256
import json
from pathlib import Path
from time import perf_counter

from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.motion_geometry_cache import GeometryCache


def run(state, artifact, output):
    store = AnimatedStore(state)
    cache = GeometryCache()
    measurements = []
    baseline = None
    for label in ('cold', 'repeat'):
        started = perf_counter()
        files = store.read(artifact)
        verified = perf_counter()
        raw = cache.read(files, artifact)
        finished = perf_counter()
        if baseline is not None:
            assert raw == baseline, 'diagnostic changed'
        baseline = raw
        report = json.loads(raw)
        assert report['artifact_sha256'] == artifact
        measurements.append(dict(kind=label, verify_seconds=verified-started,
            diagnostic_seconds=finished-verified, total_seconds=finished-started,
            report_sha256=sha256(raw).hexdigest(), report_bytes=len(raw),
            rows=len(report['rows']), status=report['status']))
        print(json.dumps(measurements[-1]), flush=True)
    result = dict(artifact_sha256=artifact, measurements=measurements,
                  scope='verified_store_and_diagnostic_not_browser_latency_or_quality_acceptance')
    output.write_text(json.dumps(result, indent=2), encoding='utf-8')


if __name__ == '__main__':
    parser = ArgumentParser()
    parser.add_argument('--state', type=Path, default=Path('workspace'))
    parser.add_argument('--artifact', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    run(args.state, args.artifact, args.output)
