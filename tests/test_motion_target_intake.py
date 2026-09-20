"""Target motion preserves reviewed rig data and reports unsuitable projections."""
from copy import deepcopy
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from autospine_workbench.automation.motion_intake_jobs import MotionIntakeJobs
from autospine_workbench.automation.motion_target_jobs import submit, assert_current
from autospine_workbench.automation.motion_target_worker import build_candidate, execute
from autospine_workbench.automation.motion_intake_worker import compile_source
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.pipeline_run import PipelineRunError
from autospine_workbench.automation.storage_io import canonical_bytes, publish_document, read_document
from autospine_workbench.bvh_parser import parse_bvh
from autospine_workbench.motion2d.mixamo_map import build_map
from test_character_motionir_candidate import fixture, motion
from test_mixamo_map import source


def inputs():
    document = fixture()
    document['skins'][0]['attachments']['point']['point'].update(
        triangles=[0, 1, 2], vertices=[1, 0, 0, 0, 1, 1, 0, 1, 0, 1, 1, 0, 0, 1, 1])
    files = {'skeleton.json': canonical_bytes(document),
             'character-manifest.json': canonical_bytes(dict(source_addresses={}, layers=[])),
             'skeleton.atlas': b'original atlas', 'images/point.png': b'original texture'}
    bvh = parse_bvh(source())
    mapping = build_map(bvh, clip_id='test', reference_length=10,
                        screen_x='+X', screen_y='-Y', depth='+Z')
    return files, motion(), bvh, mapping


class MotionTargetTests(unittest.TestCase):
    def test_worker_loads_exact_compiled_motion_and_retains_source_bundle(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            intake = root / 'intake'
            target = root / 'target'
            intake.mkdir(); target.mkdir()
            raw = source()
            (intake / 'source.bvh').write_bytes(raw)
            compiled = compile_source(raw, 'front', intake, root)['motion']
            files, _, _, _ = inputs()
            doc = json.loads(files['skeleton.json'])
            for name, parent in [('spine', 'root'), ('chest', 'spine'), ('neck', 'chest')]:
                doc['bones'].append(dict(name=name, parent=parent, x=0, y=10, rotation=0))
            files['skeleton.json'] = canonical_bytes(doc)
            store = AnimatedStore(root)
            original = store.publish(files)
            publish_document(target / 'request.json', dict(motion_identity=compiled, character_sha256=original),
                             staging=target / 'staging')
            with patch('autospine_workbench.automation.motion_target_worker.capture',
                       return_value={'status': 'unavailable'}) as capture:
                execute(target, root, root)
            receipt = read_document(target / 'worker-result.json')
            self.assertEqual(receipt['runtime']['status'], 'unavailable')
            self.assertEqual(store.read(original), files)
            self.assertIn('external-motion', json.loads(store.read(receipt['artifact_sha256'])['skeleton.json'])['animations'])
            capture.assert_called_once()

    def test_only_animation_changes_and_geometry_is_resampled(self):
        files, clip, bvh, mapping = inputs()
        before = deepcopy(files)
        result, evidence, geometry = build_candidate(files, clip, bvh, mapping,
            character_digest='a'*64, motion_digest='b'*64)
        self.assertEqual(files, before)
        original = json.loads(files['skeleton.json'])
        changed = json.loads(result['skeleton.json'])
        self.assertEqual({k:v for k,v in original.items() if k != 'animations'},
                         {k:v for k,v in changed.items() if k != 'animations'})
        self.assertEqual(result['images/point.png'], files['images/point.png'])
        self.assertEqual(set(changed['animations']), {'external-motion'})
        self.assertTrue(geometry['passed'], geometry)
        self.assertGreaterEqual(geometry['records'][0]['sample_count'], 257)
        self.assertEqual(evidence['contact_status'], 'unavailable_no_labels')
        self.assertFalse(json.loads(result['character-manifest.json'])['production_authorized'])

    def test_projection_failure_is_diagnostic_never_a_silent_success(self):
        with patch('autospine_workbench.targets.character43.projected_lengths.build',
                   side_effect=ValueError('character_length_projection_collapsed')):
            _, evidence, _ = build_candidate(*inputs(), character_digest='a'*64, motion_digest='b'*64)
        self.assertEqual(evidence['status'], 'needs_changes')
        self.assertEqual(evidence['issues'][0]['reason_code'], 'character_length_projection_collapsed')

    def test_source_bound_submission_and_character_change_invalidate_result(self):
        with tempfile.TemporaryDirectory() as temporary:
            projects = SimpleNamespace(state_root=Path(temporary), workspace_root=Path(temporary))
            manager = MotionIntakeJobs(projects)
            self.addCleanup(manager.close)
            raw = source()
            with patch.object(manager._pool, 'submit'):
                queued = manager.upload(BytesIO(raw), len(raw), 'source.bvh', 'front')
                manager._jobs[queued['job_id']].update(status='succeeded', step='complete',
                    result=dict(motion_status='compiled', frame_count=2, motion={'bundle_sha256':'a'*64}))
                character = dict(status='needs_review', artifact_sha256='b'*64)
                manager.character_manager = lambda: SimpleNamespace(verified_files=lambda *_: {}, get=lambda *_: character)
                value = submit(manager, queued['job_id'], dict(project_id='alice', character_job_id='job-'+'c'*32))
                request = read_document(manager.folder(value['job_id']) / 'request.json')
                self.assertTrue(request['contact_correction'])
                assert_current(manager, request)
                disabled = submit(manager, queued['job_id'], dict(project_id='alice',
                    character_job_id='job-'+'c'*32, contact_correction=False, clip=dict(start_frame=0, end_frame=1)))
                manager._jobs[disabled['job_id']].update(status='failed')
                with patch('autospine_workbench.automation.motion_target_jobs.submit') as retry:
                    manager.retry(disabled['job_id'])
                    self.assertFalse(retry.call_args.args[2]['contact_correction'])
                    self.assertEqual(retry.call_args.args[2]['clip'], dict(start_frame=0, end_frame=1))
                character['artifact_sha256'] = 'd'*64
                with self.assertRaisesRegex(PipelineRunError, 'motion_target_character_changed'):
                    assert_current(manager, request)
                manager._jobs[value['job_id']].update(status='succeeded', result={})
                self.assertEqual(manager.get(value['job_id'])['status'], 'outdated')
                with self.assertRaisesRegex(PipelineRunError, 'motion_request_invalid'):
                    submit(manager, queued['job_id'], dict(project_id='alice', path='arbitrary'))
            manager.close()


if __name__ == '__main__':
    unittest.main()
