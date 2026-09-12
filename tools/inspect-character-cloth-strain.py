"""Measure sampled material strain of an immutable cloth trial without adopting it."""
import argparse
from pathlib import Path
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.targets.character43.cloth_strain_report import inspect


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state-root', type=Path, required=True)
    parser.add_argument('--bundle', required=True); parser.add_argument('--helper', required=True)
    parser.add_argument('--output', type=Path, required=True); args = parser.parse_args()
    report = inspect(AnimatedStore(args.state_root).read(args.bundle), args.helper)
    report['source_bundle_sha256'] = args.bundle
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical_bytes(report))
    print(report['passed'])
