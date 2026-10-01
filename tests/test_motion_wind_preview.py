"""Draft calculation has exact candidate identity and never publishes a job."""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import Mock, patch

from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.motion_intake_routes import _methods, dispatch_motions
from autospine_workbench.automation.motion_wind_preview import preview, HASHES
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.resolved_project import canonical_sha256
from autospine_workbench.targets.character43 import joint_secondary
from autospine_workbench.targets.character43.joint_animation_config import defaults, PROFILE
from autospine_workbench.targets.character43.joint_wind_preview import compute, validate_template
from autospine_workbench.targets.character43.joint_spring import interpolate
from test_joint_secondary import scene


class MotionWindPreviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.store = AnimatedStore(self.root)
        self.job = 'motion-'+'1'*32; self.parent_job = 'motion-'+'2'*32
        files, source = scene(); self.config = defaults()
        self.config['hair'].update(enabled=True, cascade=True)
        self.config['cloth']['enabled'] = True
        self.config['wind'].update(enabled=True, strength=33., direction=20., seed=712, gust=.4)
        secondary = {k:self.config[k] for k in ('hair', 'cloth', 'objects', 'wind', 'loop')}
        self.document, applied = joint_secondary.apply(files, source, 'idle', secondary, [0., 2.])
        self.template = applied.pop('preview_data')
        self.parent_sha = sha256(canonical_bytes(source)).hexdigest()
        self.parent_artifact = self.store.publish({'skeleton.json':canonical_bytes(source)})
        self.skeleton_sha = sha256(canonical_bytes(self.document)).hexdigest()
        config_sha = canonical_sha256(self.config)
        self.template.update(skeleton_sha256=self.skeleton_sha, parent_skeleton_sha256=self.parent_sha, config_sha256=config_sha)
        raw_template = canonical_bytes(self.template); self.template_sha = sha256(raw_template).hexdigest()
        applied['wind_preview'] = dict(file='wind-preview.json', sha256=self.template_sha)
        self.report = dict(schema='autospine.joint-animation/v1', profile=PROFILE, config=self.config,
            config_sha256=config_sha, skeleton_sha256=self.skeleton_sha, parent_skeleton_sha256=self.parent_sha,
            duration=2., animation='idle', inventory=joint_secondary.inventory(files, source), secondary=applied)
        self.artifact = self.store.publish({'skeleton.json':canonical_bytes(self.document),
            'joint-animation.json':canonical_bytes(self.report), 'wind-preview.json':raw_template})
        self.source_job = 'motion-'+'3'*32; source_raw = b'fixture body motion, never executed'
        self.source_row = dict(job_id=self.source_job, kind='import', status='succeeded', format='bvh', source_sha256=sha256(source_raw).hexdigest())
        parent_request = dict(kind='adapt', project_id='character', character_job_id='rig', name='body',
            source_job_id=self.source_job, source_job_sha256=canonical_sha256(self.source_row), character_sha256='c'*64)
        self.provenance = dict(profile='joint-animation-body-source-v1', kind='main', parent_job_id=self.parent_job,
            baseline_artifact_sha256=self.parent_artifact, artifact_sha256=self.parent_artifact,
            registration_sha256=None, parent_request_sha256=canonical_sha256(parent_request),
            related_evidence_sha256=None, related_receipt_sha256=None)
        self.request = dict(parent_request, joint_execution=dict(profile=PROFILE, config=self.config,
            config_sha256=config_sha, parent_job_id=self.parent_job, parent_artifact_sha256=self.parent_artifact,
            source_provenance=self.provenance, animation='idle', duration=2.))
        self.row = dict(kind='adapt', status='succeeded', result=dict(artifact_sha256=self.artifact,
            joint_animation_profile=PROFILE, joint_config_sha256=config_sha, joint_parent_job_id=self.parent_job,
            joint_parent_artifact_sha256=self.parent_artifact, joint_source_provenance=self.provenance))
        self.parent_row = dict(kind='adapt', status='succeeded', result=dict(artifact_sha256=self.parent_artifact))
        for job, request in ((self.job, self.request), (self.parent_job, parent_request)):
            folder = self.root/'jobs'/job; folder.mkdir(parents=True)
            (folder/'request.json').write_bytes(canonical_bytes(request))
            (folder/'result.json').write_bytes(canonical_bytes(self.row if job == self.job else self.parent_row))
        source_folder = self.root/'jobs'/self.source_job; source_folder.mkdir()
        (source_folder/'source.bvh').write_bytes(source_raw)
        (source_folder/'request.json').write_bytes(canonical_bytes(dict(job_id=self.source_job, source_sha256=self.source_row['source_sha256'])))
        (source_folder/'result.json').write_bytes(canonical_bytes(self.source_row))
        self.character_folder = self.root/'character'/'rig'; self.character_folder.mkdir(parents=True)
        (self.character_folder/'request.json').write_bytes(canonical_bytes(dict(project_id='character')))
        (self.character_folder/'result.json').write_bytes(canonical_bytes(dict(project_id='character', job_id='rig', status='needs_review', artifact_sha256='c'*64)))
        self.manager = SimpleNamespace(state_root=self.root,
            get=lambda job, **options:{self.job:self.row, self.parent_job:self.parent_row, self.source_job:self.source_row}[job],
            folder=lambda job:self.root/'jobs'/job,
            character_manager=lambda:SimpleNamespace(application=SimpleNamespace(store=self.store), _path=lambda job:self.character_folder),
            _pool=Mock(), _jobs={})
        self.body = dict(schema='autospine.wind-preview-request/v1', artifact_sha256=self.artifact,
            skeleton_sha256=self.skeleton_sha, parent_skeleton_sha256=self.parent_sha, config_sha256=config_sha,
            wind_preview_sha256=self.template_sha, config=deepcopy(self.config), no_wind=False, request_id=3)

    def run_preview(self, body=None):
        return preview(self.manager, self.job, self.body if body is None else body)

    def test_same_config_matches_baked_and_does_not_mutate_files_or_body_channels(self):
        before = {p.relative_to(self.root):p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        original = deepcopy(self.document)
        value = self.run_preview()
        self.assertFalse(value['validated']); self.assertFalse(value['production_authorized'])
        self.assertEqual(value['authority'], 'none'); self.assertFalse(value['changed'])
        self.assertEqual(value['basis'], 'frozen_candidate')
        self.assertEqual(value['pending'], ['基于已构建角色；修改骨架或区域归属后需重建'])
        self.assertEqual(value['request_id'], 3)
        self.assertEqual(value['preview_config_sha256'], canonical_sha256(self.config))
        for row in value['tracks']:
            baked = self.document['animations']['idle']['bones'][row['bone']]['rotate']
            for key in baked:
                self.assertAlmostEqual(interpolate(row['times'], row['values'], key['time']), key['value'], places=12)
            seeks = [1.7, .11, 1.7, 0., 2., .11]
            offsets = [interpolate(row['times'], row['values'], t) for t in seeks]
            self.assertEqual(offsets[0], offsets[2]); self.assertEqual(offsets[1], offsets[5])
        self.assertEqual(self.document, original)
        self.assertEqual(before, {p.relative_to(self.root):p.read_bytes() for p in self.root.rglob('*') if p.is_file()})
        self.assertEqual(self.manager._jobs, {}); self.manager._pool.submit.assert_not_called()

    def test_off_reverse_local_zero_and_anchor_rebuild_are_drafts(self):
        built = self.run_preview()
        body = deepcopy(self.body); body['no_wind'] = True
        off = self.run_preview(body)
        self.assertTrue(off['changed']); self.assertTrue(off['no_wind'])
        self.assertNotEqual(built['tracks'], off['tracks'])
        body = deepcopy(self.body); body['config']['wind']['direction'] += 180
        self.assertNotEqual(built['tracks'], self.run_preview(body)['tracks'])
        body['config']['hair']['root_fraction'] += .1
        self.assertTrue(any('固定根部' in p for p in self.run_preview(body)['pending']))
        body['config']['cloth']['response_profile'] = 'helper-local-v1'
        self.assertTrue(any('固定边缘过渡' in p for p in self.run_preview(body)['pending']))
        body = deepcopy(self.body); body['config']['hair']['wind_response'] = 0.
        zero = self.run_preview(body)
        self.assertTrue(any(a['values'] != b['values'] for a,b in zip(built['tracks'], zero['tracks'])))

    def test_every_hash_and_closed_request_shape_are_enforced(self):
        for key in HASHES:
            body = deepcopy(self.body); body[key] = '0'*64
            with self.subTest(key=key), self.assertRaisesRegex(RuntimeError, 'source_mismatch'):
                self.run_preview(body)
        for key,value in [('schema','arbitrary'), ('no_wind',1), ('request_id',-1),
                          ('request_id',True), ('request_id',9007199254740992), ('extra','path')]:
            body = deepcopy(self.body); body[key] = value
            with self.subTest(key=key), self.assertRaisesRegex(RuntimeError, 'request_invalid'):
                self.run_preview(body)
        body = deepcopy(self.body); body['config']['wind']['keys'] = [dict(time=3., strength=20., direction=0.)]
        with self.assertRaisesRegex(RuntimeError, 'config_invalid'): self.run_preview(body)
        body = deepcopy(self.body); body['config']['hair']['slots'] = ['unknown']
        with self.assertRaisesRegex(RuntimeError, 'config_invalid'): self.run_preview(body)
        self.row['status'] = 'running'
        (self.manager.folder(self.job)/'result.json').write_bytes(canonical_bytes(self.row))
        with self.assertRaisesRegex(RuntimeError, 'candidate_unavailable'): self.run_preview()

    def test_used_bytes_and_complete_inventory_tree_are_verified(self):
        folder = self.store.root/self.artifact
        path = folder/'wind-preview.json'; raw = path.read_bytes(); path.write_bytes(raw+b' ')
        with self.assertRaisesRegex(RuntimeError, 'artifact_invalid'): self.run_preview()
        path.write_bytes(raw)
        (folder/'unlisted.json').write_bytes(b'{}')
        with self.assertRaisesRegex(RuntimeError, 'artifact_invalid'): self.run_preview()

    def test_change_during_solve_rechecks_inventory_and_source_request(self):
        original_compute = compute
        def modified(*args, **kwargs):
            result = original_compute(*args, **kwargs)
            path = self.root/'jobs'/self.parent_job/'request.json'
            path.write_bytes(canonical_bytes(dict(changed=True)))
            return result
        with patch('autospine_workbench.automation.motion_wind_preview.compute', side_effect=modified):
            with self.assertRaisesRegex(RuntimeError, 'parent_changed'): self.run_preview()

    def test_change_during_solve_rechecks_input_bytes_and_parent_skeleton(self):
        original_compute = compute
        for artifact, reason in ((self.artifact, 'source_changed'), (self.parent_artifact, 'artifact_invalid')):
            path = self.store.root/artifact/'skeleton.json'; original = path.read_bytes()
            def modified(*args, **kwargs):
                result = original_compute(*args, **kwargs); path.write_bytes(original+b' ')
                return result
            with self.subTest(artifact=artifact), patch('autospine_workbench.automation.motion_wind_preview.compute', side_effect=modified):
                with self.assertRaisesRegex(RuntimeError, reason): self.run_preview()
            path.write_bytes(original)

    def test_change_during_solve_rechecks_character_journal_and_source_motion_bytes(self):
        original_compute = compute
        for path, reason in ((self.character_folder/'request.json', 'source_changed'),
                             (self.manager.folder(self.job)/'result.json', 'candidate_unavailable'),
                             (self.manager.folder(self.source_job)/'request.json', 'source_changed'),
                             (self.root/'jobs'/self.source_job/'source.bvh', 'source_mismatch')):
            original = path.read_bytes()
            def modified(*args, **kwargs):
                result = original_compute(*args, **kwargs)
                path.write_bytes(canonical_bytes(dict(project_id='character', changed=True)) if path.suffix == '.json' else b'changed motion')
                return result
            with self.subTest(path=path), patch('autospine_workbench.automation.motion_wind_preview.compute', side_effect=modified):
                with self.assertRaisesRegex(RuntimeError, reason): self.run_preview()
            path.write_bytes(original)

    def test_response_budget_fails_without_clipping_or_submitting_tracks(self):
        with patch('autospine_workbench.automation.motion_wind_preview.RESPONSE_LIMIT', 100):
            with self.assertRaisesRegex(RuntimeError, 'response_limit'): self.run_preview()
        self.manager._pool.submit.assert_not_called()

    def test_template_refuses_mismatched_helpers_duplicate_owners_and_nonfinite_matrices(self):
        for mutate in (lambda t:t['bones'].pop(next(iter(t['bones']))),
                       lambda t:t['regions'].append(deepcopy(t['regions'][0])),
                       lambda t:t['matrices'][next(iter(t['matrices']))][0].__setitem__(0,float('nan'))):
            template = deepcopy(self.template); mutate(template)
            with self.assertRaises(ValueError): validate_template(template, self.report, self.document)

    def test_route_is_fixed_post_only_and_returns_200_without_submission(self):
        self.assertEqual(_methods([self.job, 'wind-preview']), 'POST, OPTIONS')
        self.assertIsNone(_methods([self.job, 'wind-preview', 'write-file']))
        handler = SimpleNamespace(server=object(), headers=object(), connection=Mock(), _send_visual_json=Mock())
        with patch('autospine_workbench.automation.motion_intake_routes.manager_for', return_value=self.manager), \
             patch('autospine_workbench.automation.web_routes._require_mutation') as intent, \
             patch('autospine_workbench.automation.motion_intake_routes.read_json_object_request', return_value=self.body) as read:
            self.assertTrue(dispatch_motions(['api','motions',self.job,'wind-preview'], handler, 'POST'))
        intent.assert_called_once_with(handler.headers)
        read.assert_called_once_with(handler, maximum_bytes=128000)
        self.assertEqual(handler._send_visual_json.call_args.args[0], 200)
        self.manager._pool.submit.assert_not_called()


if __name__ == '__main__':
    unittest.main()
