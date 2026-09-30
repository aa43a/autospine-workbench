"""Opt-in real private Blender conversion in one fresh caller-owned test state.

No server, saved global tool configuration, user project, review or candidate
acceptance is modified. This validates source motion intake, not 2D retargeting.
"""
import argparse
from hashlib import sha256
import importlib.util
from io import BytesIO
import json
import os
from pathlib import Path
import time
from types import SimpleNamespace

from autospine_workbench.automation.blender_process import BLENDER_BUNDLE_PROFILE
from autospine_workbench.automation.motion_intake_jobs import MotionIntakeJobs, MAX_UPLOAD
from autospine_workbench.automation.storage_io import canonical_bytes, directory
from autospine_workbench.safe_input_files import read_real_file


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('output', 'runtime-root', 'source'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--manifest-sha256', required=True)
    parser.add_argument('--source-sha256', required=True)
    parser.add_argument('--expected-frames', type=int, required=True)
    parser.add_argument('--expected-joints', type=int, required=True)
    args = parser.parse_args()
    root, runtime, source = (p.absolute() for p in (args.output, args.runtime_root, args.source))
    if root.exists():
        raise ValueError('fixture_output_exists')
    module_file = Path(__file__).resolve().parents[2] / 'packaging/prepare_blender_runtime.py'
    spec = importlib.util.spec_from_file_location('fixed_blender_runtime_builder', module_file)
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    started = time.monotonic()
    manifest_file = runtime / builder.MANIFEST
    manifest_raw = read_real_file(manifest_file, 4 << 20, 'Blender distribution manifest')
    assert sha256(manifest_raw).hexdigest() == args.manifest_sha256
    manifest = json.loads(manifest_raw)
    before = builder.inventory(runtime)
    builder.verify_software_inventory(before)
    assert manifest == builder.distribution_manifest(before)
    assert manifest['conversion_profile'] == BLENDER_BUNDLE_PROFILE
    original = read_real_file(source, MAX_UPLOAD, 'Fixed FBX fixture input')
    assert sha256(original).hexdigest() == args.source_sha256
    directory(root.parent, create=True)
    root.mkdir()
    executable = runtime / manifest['blender_path']
    os.environ['AUTOSPINE_BLENDER'] = str(executable)
    os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
    projects = SimpleNamespace(state_root=root / 'empty-state')
    stages = []
    jobs = MotionIntakeJobs(projects)
    try:
        assert jobs.blender == str(executable)
        assert jobs.blender_config['source'] == 'environment'
        queued = jobs.upload(BytesIO(original), len(original), source.name, 'front')
        deadline = time.monotonic() + 245
        while True:
            result = jobs.get(queued['job_id'])
            step = result.get('step')
            if not stages or stages[-1] != step:
                stages.append(step)
            if result['status'] not in ('pending', 'running'):
                break
            if time.monotonic() > deadline:
                jobs.cancel(queued['job_id'])
                raise RuntimeError('fixture_motion_timeout')
            time.sleep(.1)
        assert result['status'] == 'succeeded', result
        receipt = result['result']
        assert receipt['motion_status'] == 'compiled', receipt
        assert receipt['frame_count'] == args.expected_frames
        assert receipt['joint_count'] == args.expected_joints
        assert receipt['fbx_bridge']['passed'] is True
        assert receipt['fbx_bridge']['source_sha256'] == args.source_sha256
        assert receipt['character_animation_status'] == 'not_built'
        preview = jobs.preview(queued['job_id'])
        folder = jobs.folder(queued['job_id'])
        inspection = json.loads((folder / 'source.inspection.json').read_bytes())
        assert inspection['blender_version'].startswith('5.2.1')
        assert (folder / 'blender-runtime/temporary').is_dir()
        assert (folder / 'blender-runtime/user/config').is_dir()
        assert not (projects.state_root / 'config/motion-tools.json').exists()
    finally:
        jobs.close()
    reopened = MotionIntakeJobs(projects)
    try:
        assert reopened.get(queued['job_id']) == result
        assert reopened.preview(queued['job_id']) == preview
    finally:
        reopened.close()
    assert read_real_file(source, MAX_UPLOAD, 'Fixed FBX fixture input') == original
    after = builder.inventory(runtime)
    builder.verify_software_inventory(after)
    assert after == before
    assert read_real_file(manifest_file, 4 << 20, 'Blender distribution manifest') == manifest_raw
    report = dict(ok=True, scope='private-blender-real-fbx-intake-bridge-motionir-and-reopen-only',
        elapsed_seconds=time.monotonic()-started, profile=BLENDER_BUNDLE_PROFILE,
        blender_version=inspection['blender_version'], manifest_sha256=args.manifest_sha256,
        software_tree=builder.tree_identity(after), software_files=len(after),
        software_bytes=sum(row['bytes'] for row in after), software_unchanged=True,
        source_sha256=args.source_sha256, source_unchanged=True, job_id=queued['job_id'],
        frame_count=receipt['frame_count'], joint_count=receipt['joint_count'],
        bridge=receipt['fbx_bridge'], stages=stages, manager_reopen_identical=True,
        saved_global_tool_configuration_written=False, user_project_state_touched=False,
        human_visual_acceptance=False, authority='none')
    (root / 'report.json').write_bytes(canonical_bytes(report))
    print(json.dumps({key:report[key] for key in ('ok','scope','elapsed_seconds','blender_version',
        'frame_count','joint_count','software_unchanged','source_unchanged','manager_reopen_identical')}))


if __name__ == '__main__':
    main()
