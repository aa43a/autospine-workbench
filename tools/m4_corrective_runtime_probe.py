"""Capture an isolated corrective with rebuilt references and no inherited acceptance."""
import argparse
import json
from pathlib import Path
from types import SimpleNamespace

from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.character_capture import capture
from autospine_workbench.automation.storage_io import canonical_bytes
from m4_corrective_geometry_check import prepare
from m4_experiment_player_export import export


def render_inputs(files, evidence):
    # Carry only render inputs and newly verified geometry, never parent QA/acceptance.
    render_names = {'skeleton.json', 'skeleton.atlas', 'character-manifest.json',
                    'rig-setup-reference.json', 'numeric-reference.json'}
    files = {name: raw for name, raw in files.items() if name in render_names or
             name.startswith(('textures/', 'images/', 'editor/images/', 'numeric-reference/'))}
    files['deformation.json'] = canonical_bytes(evidence['geometry'])
    files['corrective-provenance.json'] = canonical_bytes(evidence)
    return files


def run(source, experiment, output):
    if output.exists():
        raise ValueError('corrective_runtime_output_exists')
    files, evidence = prepare(source, experiment)
    files = render_inputs(files, evidence)
    output.mkdir(parents=True, exist_ok=False)
    store = AnimatedStore(output/'isolated-store')
    digest = store.publish(files)
    report = dict(candidate_bundle_sha256=digest, source_candidate=evidence['source_candidate'],
                  skeleton_sha256=evidence['skeleton_sha256'], authority='none', selected=False,
                  production_authorized=False, geometry_passed=evidence['geometry']['passed'],
                  runtime_status='not_evaluated',
                  scope='isolated_corrective_geometry_and_runtime_not_full_motion_admission',
                  pending_checks=['contact_and_depth_revalidation', 'visual_review'])
    (output/'report.json').write_bytes(canonical_bytes(report))
    try:
        result = capture(SimpleNamespace(workspace_root=Path.cwd().parent), store, digest, output,
                         progress=lambda stage: print(stage, flush=True), cancel_requested=lambda: False,
                         storage_reference=True)
    except Exception as exc:
        report.update(runtime_status='failed', runtime_error=str(exc))
        (output/'report.json').write_bytes(canonical_bytes(report))
        raise
    report['runtime_status'] = result['status']
    (output/'report.json').write_bytes(canonical_bytes(report))
    if result['status'] == 'unavailable':
        return
    runtime = json.loads((output/'runtime/report.json').read_bytes())
    if runtime['passed'] is True:
        export(output)
    print(json.dumps(dict(geometry_passed=report['geometry_passed'],
                          runtime_status=result['status'], candidate_bundle_sha256=digest)), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    for name in ('source', 'experiment', 'output'):
        parser.add_argument(name, type=Path)
    args = parser.parse_args()
    run(args.source, args.experiment, args.output)
