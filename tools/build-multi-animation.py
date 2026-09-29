"""Build and capture an exact compatible multi-animation candidate from frozen artifacts."""
import argparse
import json
from pathlib import Path
from types import SimpleNamespace

from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.character_capture import capture
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.targets.character43.multi_animation import build


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--state-root', required=True)
    parser.add_argument('--workspace', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--source', action='append', required=True, help='name=artifact-sha256')
    args = parser.parse_args()
    store = AnimatedStore(Path(args.state_root))
    sources = []
    for item in args.source:
        name, digest = item.split('=', 1)
        sources.append(dict(name=name, artifact_sha256=digest, files=store.read(digest)))
    files, report = build(sources)
    artifact = store.publish(files)
    folder = Path(args.output); folder.mkdir(parents=True, exist_ok=True)
    runtime = capture(SimpleNamespace(workspace_root=Path(args.workspace)), store, artifact, folder,
                      progress=lambda step: print(step, flush=True), cancel_requested=lambda: False,
                      storage_reference=True)
    value = dict(artifact_sha256=artifact, merge=report, runtime=runtime,
                 authority='none', production_authorized=False, visual_status='not_reviewed')
    (folder/'multi-animation-result.json').write_bytes(canonical_bytes(value))
    print(json.dumps(dict(artifact_sha256=artifact, frames=runtime.get('frames'),
                         geometry_status=runtime.get('geometry_status'))), flush=True)


if __name__ == '__main__':
    main()
