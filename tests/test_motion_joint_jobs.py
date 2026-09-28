from copy import deepcopy
import json
from pathlib import Path
import tempfile
from threading import RLock
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from autospine_workbench.automation import motion_joint_jobs as jobs
from autospine_workbench.automation.motion_intake_routes import _methods
from autospine_workbench.automation.storage_io import canonical_bytes, read_document
from autospine_workbench.resolved_project import canonical_sha256
from autospine_workbench.targets.character43.joint_animation_config import defaults, normalize, controls
from autospine_workbench.targets.character43.joint_animation_qa import geometry_report, compare
from test_joint_face import fixture


class JointJobsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        def folder(job, create=False):
            value = root/job
            if create: value.mkdir(exist_ok=True)
            return value
        self.request = dict(kind='adapt', job_id='parent', name='body', project_id='alice',
                            character_job_id='rig', source_job_id='source', source_job_sha256='s'*64,
                            repair_execution=dict(profile='existing_body_fix'))
        self.parent = dict(kind='adapt', status='succeeded', project_id='alice',
                           character_job_id='rig', result=dict(artifact_sha256='a'*64))
        self.manager = SimpleNamespace(folder=folder, state_root=root, _closed=False, _lock=RLock(),
            _jobs={}, _cancel={}, _pool=Mock(), _execute=Mock(), get=Mock(return_value=self.parent))
        folder('parent', True).joinpath('request.json').write_bytes(canonical_bytes(self.request))
        self.provenance = dict(profile='joint-animation-body-source-v1', kind='main', parent_job_id='parent',
            baseline_artifact_sha256='a'*64, artifact_sha256='a'*64, registration_sha256=None,
            parent_request_sha256=canonical_sha256(self.request), related_evidence_sha256=None, related_receipt_sha256=None)
        self.context = (self.parent, self.request, {}, {'skins':[{}], 'animations':{'body':{}}}, 'body', 2., self.provenance)

    def submit(self, config=None, artifact='a'*64):
        with patch.object(jobs, 'context', return_value=self.context):
            return jobs.submit(self.manager, 'parent', dict(artifact_sha256=artifact, config=config or defaults()))

    def test_exact_body_and_config_are_frozen_without_changing_prior_repair(self):
        config = defaults(); config['face']['enabled'] = True
        value = self.submit(config)
        saved = read_document(self.manager.folder(value['job_id'])/'request.json')
        frozen = saved['joint_execution']
        self.assertEqual(frozen['parent_artifact_sha256'], 'a'*64)
        self.assertEqual(frozen['config_sha256'], canonical_sha256(frozen['config']))
        self.assertEqual(saved['repair_execution'], self.request['repair_execution'])
        config['face']['enabled'] = False
        self.assertTrue(frozen['config']['face']['enabled'])
        self.assertEqual(read_document(self.manager.folder('parent')/'request.json'), self.request)
        self.manager._pool.submit.assert_called_once_with(self.manager._execute, value['job_id'])

    def test_stale_artifact_invalid_parameters_and_full_queue_do_not_submit(self):
        with self.assertRaisesRegex(RuntimeError, 'body_changed'): self.submit(artifact='b'*64)
        bad = defaults(); bad['hair']['damping'] = 100
        with self.assertRaisesRegex(RuntimeError, 'config_invalid'): self.submit(bad)
        self.manager._jobs = {'x':dict(status='running'), 'y':dict(status='pending')}
        with self.assertRaisesRegex(RuntimeError, 'queue_full'): self.submit()
        self.manager._pool.submit.assert_not_called()

    def test_retry_reuses_frozen_joint_parameters_not_plain_body_retarget(self):
        request = dict(joint_execution=dict(parent_job_id='parent', parent_artifact_sha256='a'*64, config=defaults()))
        with patch.object(jobs, 'submit', return_value={'job_id':'retry'}) as call:
            self.assertEqual(jobs.retry(self.manager, request), {'job_id':'retry'})
        call.assert_called_once_with(self.manager, 'parent', dict(artifact_sha256='a'*64, config=defaults()))

    def test_joint_result_cannot_be_used_as_new_body_to_double_apply_effects(self):
        self.request['joint_execution'] = {'parent_job_id':'base'}
        self.manager.folder('parent').joinpath('request.json').write_bytes(canonical_bytes(self.request))
        with patch('autospine_workbench.automation.motion_target_jobs.assert_current'):
            with self.assertRaisesRegex(RuntimeError, 'original_body_required'): jobs.context(self.manager, 'parent')

    def test_joint_result_rejects_body_repair_instead_of_ignoring_new_request(self):
        self.request['joint_execution'] = {'parent_job_id':'base'}
        self.manager.folder('parent').joinpath('request.json').write_bytes(canonical_bytes(self.request))
        with self.assertRaisesRegex(RuntimeError, 'repair_original_body_required'):
            jobs.require_body_repair_parent(self.manager, 'parent')

    def test_mutation_route_and_query_route_are_explicit(self):
        self.assertEqual(_methods(['body', 'joint-animation']), 'GET, HEAD, POST, OPTIONS')
        self.assertIsNone(_methods(['body', 'joint-animation', 'write-file']))

    def test_attachment_switching_is_reported_and_rejected_before_submission(self):
        doc = self.context[3]
        doc['animations']['body']['slots'] = {'leg': {'attachment': [{'name':'bent'}]}}
        self.assertFalse(jobs.eligibility(doc)['supported'])
        with self.assertRaisesRegex(RuntimeError, 'body_unsupported'): self.submit()
        self.manager._pool.submit.assert_not_called()


class JointContractTests(unittest.TestCase):
    def test_normalization_is_idempotent_and_rejects_bad_timeline_keys(self):
        config = defaults(); config['face']['gaze']['keys'] = [dict(time=0,x=-1,y=0), dict(time=2,x=1,y=0)]
        normalized = normalize(config, 2.)
        self.assertEqual(normalize(normalized, 2.), normalized)
        config['face']['gaze']['keys'][1]['time'] = 3
        with self.assertRaises(ValueError): normalize(config, 2.)
        with self.assertRaises(ValueError): normalize(dict(config, surprise=True), 2.)
        with self.assertRaises(ValueError): normalize(dict(defaults(), fps=120), 2.)

    def test_controls_expose_valid_nested_endpoints(self):
        for row in controls():
            if row['type'] != 'number': continue
            for bound in ('min', 'max'):
                config = defaults(); target = config[row['group']]; path = row['key'].split('.')
                for field in path[:-1]: target = target[field]
                target[path[-1]] = row[bound]
                normalize(config, 120.)

    def test_blink_compression_is_scoped_and_never_excuses_inversion_or_body_collapse(self):
        row = dict(slot='eye', passed=False, min_area_ratio=.08, max_area_ratio=1,
                   max_edge_stretch=1, inversion_samples=0)
        raw = dict(records=[row, dict(row, slot='body')], passed=False)
        bounds = dict(face_report=dict(channels={'eye': dict(min_scale_x=1, min_scale_y=.08)}),
                      source_geometry=dict(records=[dict(row, passed=True, min_area_ratio=1)]))
        result = geometry_report(raw, dict(parts=[dict(slot='eye', role='white')]), True, **bounds)
        self.assertTrue(result['records'][0]['passed']); self.assertFalse(result['records'][1]['passed'])
        self.assertFalse(raw['records'][0]['passed'])
        row['inversion_samples']=1
        self.assertFalse(geometry_report(raw, dict(parts=[dict(slot='eye', role='white')]), True, **bounds)['records'][0]['passed'])

    def test_preservation_guard_rejects_body_motion_or_unowned_mesh_changes(self):
        _, doc = fixture(); changed = deepcopy(doc)
        changed['animations']['body']['bones']['head']['rotate'][1]['value'] = 8
        with self.assertRaisesRegex(ValueError, 'body_track_changed'):
            compare(doc, changed, 'body', [0,1,2], set())
        changed = deepcopy(doc); changed['skins'][0]['attachments']['layer-005']['layer-005']['vertices'][2] += 1
        with self.assertRaisesRegex(ValueError, 'unrelated_vertices_changed'):
            compare(doc, changed, 'body', [0,1,2], set())


if __name__ == '__main__': unittest.main()
