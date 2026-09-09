"""Project audit preparation is independent of benchmark mappings and user approval."""
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tests import test_benchmark_r2a_cli as fixtures
from autospine_workbench.automation import animated_inputs as inputs
from autospine_workbench.automation.input_preparation_sources import prepare_source, publish_prepared_source, SourceStore
from autospine_workbench.automation.animated_joint_review import get_joint_review, save_joint_review
from autospine_workbench.automation.animated_input_index import inspect_registration
from autospine_workbench.automation.animated_application import AnimatedApplication
from autospine_workbench.resolved_project import canonical_sha256


class ProjectInputPreparationTests(unittest.TestCase):
    def setUp(self):
        f = fixtures.R2aCliTests()
        f.setUp()
        self.addCleanup(f.doCleanups)
        self.f = f
        self.audit = f.fixture.fixture.audit
        self.project = {'overrides': {'revision': 0}, 'layers': [
            dict(id=row['layer_id'], source_index=row['traversal_index'], name=row['name'])
            for row in f.candidate['layers']]}
        self.checkpoint = dict(resolved_project_sha256='a' * 64, input_identity_sha256='b' * 64)
        self.store = SimpleNamespace(state_root=f.state, workspace_root=f.root,
            get_project=lambda _: deepcopy(self.project), _record=lambda _: SimpleNamespace(audit=self.audit),
            resolve_asset=lambda _, kind, layer=None: f.root / (
                'composite.png' if kind == 'composite' else f'layer-{int(layer[-3:])}.png'))
        patcher = patch.object(inputs, '_checkpoint', lambda *_: (deepcopy(self.project), deepcopy(self.checkpoint)))
        patcher.start()
        self.addCleanup(patcher.stop)

    def prepare(self):
        return prepare_source(self.store, 'new-project', self.checkpoint['resolved_project_sha256'])

    def pose(self, source):
        pose = json.loads(self.f.pose_path.read_bytes())
        pose['project_id'] = 'new-project'
        pose['source']['image_sha256'] = source.candidate['composite_sha256']
        return pose

    def test_new_audit_to_all_points_zero_review_and_exact_replay_after_explicit_review(self):
        source = self.prepare()
        self.assertEqual(source.manifest, self.prepare().manifest)
        self.assertNotIn('characters', source.manifest)
        self.assertNotIn('source_png_sha256', source.candidate)
        result = publish_prepared_source(self.store, 'new-project', source, self.pose(source))
        self.assertEqual(result['reviewed_joint_count'], 0)
        self.assertEqual(result['skeleton_status'], 'blocked')
        self.check_schemas(source)
        review = get_joint_review(self.store, 'new-project')
        self.assertEqual(len(review['records']), 17)
        self.assertEqual(review['reviewed_joint_ids'], [])
        with inputs.load_inputs(self.store, 'new-project') as current:
            self.assertEqual(current.skeleton['reason_codes'], ['all_joint_reviews_required'])
            self.assertTrue(all(r['action'] == 'pending' for r in current.draft['records']))
        review['records'][0]['notes'] = 'Explicit single-point review'
        save_joint_review(self.store, 'new-project', review['input_identity_sha256'], review['records'], ['root'])
        with inputs.load_inputs(self.store, 'new-project') as current:
            self.assertEqual(current.assisted['reviewed_joint_ids'], ['root'])
        before = inputs._registrations(self.store, 'new-project')
        with self.assertRaisesRegex(inputs.AnimatedSourceError, 'already_registered'):
            publish_prepared_source(self.store, 'new-project', source, self.pose(source))
        self.assertEqual(before, inputs._registrations(self.store, 'new-project'))

    def check_schemas(self, source):
        try:
            from jsonschema import Draft202012Validator
            from referencing import Registry, Resource
        except ImportError:
            return
        names = ('project-audit-source-v1', 'project-semantic-candidates-v1',
                 'animated-input-registration-v1', 'animated-input-registration-v3', 'animated-authoring-rebase-v1')
        folder = Path(__file__).resolve().parents[1] / 'schemas'
        schemas = {name: json.loads((folder / (name + '.schema.json')).read_bytes()) for name in names}
        registry = Registry().with_resources((schema['$id'], Resource.from_contents(schema)) for schema in schemas.values())
        for name, value in [('project-audit-source-v1', source.manifest),
                            ('project-semantic-candidates-v1', source.candidate),
                            ('animated-input-registration-v3', inputs._registrations(self.store, 'new-project')[-1][1])]:
            Draft202012Validator.check_schema(schemas[name])
            validator = Draft202012Validator(schemas[name], registry=registry)
            validator.validate(value)
            forged = dict(value, authority='approved')
            self.assertTrue(list(validator.iter_errors(forged)))

    def test_pose_identity_stale_current_and_authoring_edits_fail_without_registration(self):
        self.project['overrides']['revision'] = 1
        with self.assertRaisesRegex(inputs.AnimatedSourceError, 'authoring_edits_unsupported'):
            self.prepare()
        self.project['overrides']['revision'] = 0
        source = self.prepare()
        pose = self.pose(source)
        pose['source']['image_sha256'] = 'f' * 64
        with self.assertRaises(ValueError):
            publish_prepared_source(self.store, 'new-project', source, pose)
        with self.assertRaisesRegex(inputs.AnimatedSourceError, 'animated_source_missing'):
            inputs._registrations(self.store, 'new-project')
        self.checkpoint['resolved_project_sha256'] = 'c' * 64
        with self.assertRaisesRegex(inputs.AnimatedSourceError, 'source_stale'):
            publish_prepared_source(self.store, 'new-project', source, self.pose(source))

    def test_all_explicit_joint_reviews_reach_actual_animation_compilation(self):
        source = self.prepare()
        publish_prepared_source(self.store, 'new-project', source, self.pose(source))
        review = get_joint_review(self.store, 'new-project')
        w, h = source.candidate['canvas']
        points = {'root': [.50, .96], 'pelvis': [.48, .60], 'chest': [.52, .34],
                  'neck': [.51, .26], 'head': [.50, .16]}
        for side, sign in (('left', 1), ('right', -1)):
            for joint, dx, y in (('shoulder', .20, .35), ('elbow', .28, .46), ('wrist', .35, .57),
                                 ('hip', .10, .60), ('knee', .12, .74), ('ankle', .14, .88)):
                points[f'{joint}.{side}'] = [.50 + sign * dx, y]
        for row in review['records']:
            x, y = points[row['joint_id']]
            row.update(position=[x * w, y * h], status='observed', notes='Synthetic explicit review only')
        save_joint_review(self.store, 'new-project', review['input_identity_sha256'],
                          review['records'], list(points))
        with inputs.load_inputs(self.store, 'new-project') as current:
            self.assertEqual(current.skeleton['status'], 'candidate_requires_review')
            self.assertEqual(len(current.skeleton['bones']), 20)
            self.assertTrue(any(row['options'] for row in current.bindings['bindings']))
            original_draft = deepcopy(current.draft)
        app = AnimatedApplication(self.store)
        run = app.preview('new-project', self.checkpoint['resolved_project_sha256'], 'limb-flex-15')
        self.assertTrue(run['preview_available'])
        self.assertEqual(run['status'], 'needs_review')
        self.assertEqual([s['status'] for s in run['steps'][:3]], ['succeeded'] * 3)
        self.assertTrue(run['review_items'])
        files = app.store.read(run['steps'][2]['outputs']['bundle_sha256'])
        scope = json.loads(files['preview-manifest.json'])
        self.assertFalse(scope['production_authorized'])
        self.assertEqual(len(json.loads(files['playback.json'])['frames']), 61)
        with inputs.load_inputs(self.store, 'new-project') as current:
            self.assertEqual(current.draft, original_draft)
        self.assertEqual(app.preview('new-project', self.checkpoint['resolved_project_sha256'], 'limb-flex-15'), run)

    def test_snapshot_and_current_pixels_are_both_checked(self):
        source = self.prepare()
        publish_prepared_source(self.store, 'new-project', source, self.pose(source))
        folder = SourceStore(self.store.state_root).root / source.manifest['source_bundle_sha256']
        (folder / 'layers/layer-000.png').write_bytes(b'changed')
        with self.assertRaises(ValueError):
            with inputs.load_inputs(self.store, 'new-project'):
                self.fail('tampered source must not load')
        (self.f.root / 'layer-0.png').write_bytes(b'changed')
        with self.assertRaises(inputs.AnimatedSourceError):
            inspect_registration(self.store, 'new-project')


if __name__ == '__main__':
    unittest.main()
