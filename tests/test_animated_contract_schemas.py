"""Published animation contracts reject invented authority and malformed payloads."""
from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

try:
    from jsonschema import Draft202012Validator
    from referencing import Registry, Resource
except ImportError:
    Draft202012Validator = None

from autospine_workbench.automation.animated_compile import prepare_mesh, compile_preview
from autospine_workbench.automation.animated_motion import build_motion
from autospine_workbench.automation.animated_package import package_preview
from autospine_workbench.automation.animated_run import create_run
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.animated_registration import validate_entry
from autospine_workbench.automation.animated_inputs import AnimatedSourceError
from autospine_workbench.automation.storage_io import canonical_bytes
from tests.test_animated_application import source_fixture

ROOT = Path(__file__).resolve().parents[1]
NAMES = ('workbench-animated-definitions-v1', 'animated-pipeline-run-v1',
         'workbench-preview-motion-v1', 'workbench-animated-preview-v1', 'workbench-sampled-playback-v1',
         'animated-input-registration-v1', 'animated-joint-review-request-v1',
         'benchmark-manifest-v1', 'benchmark-joint-draft-v1', 'animated-source-rebase-request-v1',
         'animated-input-registration-v2', 'animated-authoring-rebase-v1')


@unittest.skipIf(Draft202012Validator is None, 'jsonschema is optional')
class AnimatedContractSchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schemas = {}
        resources = []
        for name in NAMES:
            schema = json.loads((ROOT / 'schemas' / (name + '.schema.json')).read_bytes())
            Draft202012Validator.check_schema(schema)
            cls.schemas[name] = schema
            resource = Resource.from_contents(schema)
            resources.extend([(name + '.schema.json', resource), (schema.get('$id', name), resource),
                              ('https://autospine-workbench.local/schemas/' + name + '.schema.json', resource)])
        cls.registry = Registry().with_resources(resources)
        source = source_fixture()
        cls.assisted = source.assisted
        stage = prepare_mesh(source)
        compiled = compile_preview(source, stage, 'limb-flex-15')
        cls.files = package_preview(source, compiled)
        cls.scope = json.loads(cls.files['preview-manifest.json'])
        cls.run_document = create_run('fixture', source.source_addresses, 'limb-flex-15')

    def validator(self, name):
        return Draft202012Validator(self.schemas[name], registry=self.registry)

    def rejects(self, name, value, mutate):
        bad = deepcopy(value)
        mutate(bad)
        self.assertTrue(list(self.validator(name).iter_errors(bad)), bad)

    def test_actual_compilation_outputs_match_all_contracts(self):
        self.validator('animated-pipeline-run-v1').validate(self.run_document)
        self.validator('workbench-preview-motion-v1').validate(json.loads(self.files['motion.json']))
        self.validator('workbench-animated-preview-v1').validate(self.scope)
        self.validator('workbench-sampled-playback-v1').validate(json.loads(self.files['playback.json']))
        completed = deepcopy(self.run_document)
        completed.update(status='needs_review', preview_available=True,
                         summary=self.scope['summary'], review_items=self.scope['review_items'])
        for step in completed['steps'][:3]:
            step['status'] = 'succeeded'
        completed['steps'][3]['status'] = 'needs_review'
        self.validator('animated-pipeline-run-v1').validate(completed)
        scope = dict(self.scope, stage_identity={key: self.run_document[key] for key in
            ('run_id', 'source_addresses', 'clip', 'engine_sha256', 'target_version')})
        self.validator('workbench-animated-preview-v1').validate(scope)

    def test_run_cannot_claim_preview_before_compilation_or_change_stage_order(self):
        for mutate in (lambda r: r.update(preview_available=True),
                       lambda r: r.update(authority='production'),
                       lambda r: r.update(status='complete'),
                       lambda r: r['steps'][0].update(id='compile-animated-preview'),
                       lambda r: r['steps'][0]['outputs'].update(bundle_sha256='not-a-digest')):
            self.rejects('animated-pipeline-run-v1', self.run_document, mutate)

    def test_motion_rejects_unbounded_motion_and_unsupported_joints(self):
        motion = build_motion('limb-flex-15', ['forearm_l'])
        self.validator('workbench-preview-motion-v1').validate(build_motion('limb-flex-30', ['calf_r']))
        for mutate in (lambda m: m.update(production_authorized=True),
                       lambda m: m.update(clip='walk'),
                       lambda m: m['bones'].update(head=m['bones']['forearm_l']),
                       lambda m: m['bones']['forearm_l']['rotation'][15].update(degrees=16),
                       lambda m: m['bones']['forearm_l']['rotation'].pop()):
            self.rejects('workbench-preview-motion-v1', motion, mutate)

    def test_preview_cannot_forge_release_or_visual_quality(self):
        for mutate in (lambda p: p.update(production_authorized=True),
                       lambda p: p.update(full_character_animation=True),
                       lambda p: p.update(target='4.2'),
                       lambda p: p['bake_qa'].update(seam_coverage='passed'),
                       lambda p: p['regions'][0].update(review_status='approved'),
                       lambda p: p['regions'][0]['expected_page_uvs'][0].__setitem__(0, 2)):
            self.rejects('workbench-animated-preview-v1', self.scope, mutate)

    def test_large_playback_is_not_subject_to_small_run_journal_limit(self):
        playback = json.loads(self.files['playback.json'])
        layer = playback['layers'][0]
        layer['uvs'] = [[0.25, 0.75]] * 220
        for frame in playback['frames']:
            frame['vertices'][layer['id']] = [[123.1234567, 321.7654321]] * 220
        raw = canonical_bytes(playback)
        self.assertGreater(len(raw), 128 << 10)
        self.validator('workbench-sampled-playback-v1').validate(playback)
        with TemporaryDirectory() as temporary:
            store = AnimatedStore(Path(temporary))
            digest = store.publish({'playback.json': raw})
            self.assertEqual(store.read(digest)['playback.json'], raw)
        self.rejects('workbench-sampled-playback-v1', playback,
                     lambda p: p.update(renderer='official_spine_runtime'))

    def test_registered_source_and_explicit_joint_submission_contracts(self):
        registration = dict(schema='autospine.animated-input-registration/v1', authority='none',
                            production_authorized=False, project_id='fixture',
                            manifest=json.loads((ROOT / 'docs/benchmark/manifest-frozen-v1.json').read_bytes()),
                            source_draft_sha256='a' * 64, checkpoint=self.run_document['source_addresses'],
                            revision=0, previous_sha256=None)
        self.validator('animated-input-registration-v1').validate(registration)
        proof = dict(schema='autospine.animated-authoring-rebase/v1', authority='none',
                     annotation_mode='model_assisted', independent_annotation=False,
                     previous_registration_sha256='b' * 64, source_checkpoint=registration['checkpoint'],
                     target_checkpoint=registration['checkpoint'], authoring_revision=2,
                     authoring_overrides_sha256='c' * 64,
                     joint_overrides={'elbow.left': {'x': 10, 'y': 20}, 'eye.left': {'x': 30, 'y': 40}},
                     imported_joint_ids=['elbow.left'], ignored_joint_ids=['eye.left'])
        rebased = dict(registration, schema='autospine.animated-input-registration/v2',
                       revision=1, previous_sha256='b' * 64, authoring_rebase=proof)
        self.validator('animated-input-registration-v2').validate(rebased)
        validate_entry(rebased, 'fixture', 1, ('b' * 64, registration))
        for mutate in (lambda r: r.update(schema='autospine.animated-input-registration/v1'),
                       lambda r: r['authoring_rebase'].update(previous_registration_sha256='d' * 64),
                       lambda r: r['authoring_rebase']['joint_overrides']['elbow.left'].update(x=float('nan')),
                       lambda r: r['authoring_rebase']['ignored_joint_ids'].append('elbow.left')):
            bad = deepcopy(rebased)
            mutate(bad)
            with self.assertRaises(AnimatedSourceError):
                validate_entry(bad, 'fixture', 1, ('b' * 64, registration))
        for mutate in (lambda r: r.pop('authoring_rebase'),
                       lambda r: r['authoring_rebase'].update(independent_annotation=True),
                       lambda r: r['authoring_rebase']['imported_joint_ids'].append('eye.left')):
            self.rejects('animated-input-registration-v2', rebased, mutate)
        request = dict(expected_resolved_sha256='a' * 64, expected_input_sha256='b' * 64,
                       records=self.assisted['draft']['records'],
                       reviewed_joint_ids=self.assisted['reviewed_joint_ids'])
        self.validator('animated-joint-review-request-v1').validate(request)
        self.rejects('animated-joint-review-request-v1', request,
                     lambda r: r.update(independent_annotation=True))
        self.rejects('animated-joint-review-request-v1', request,
                     lambda r: r['reviewed_joint_ids'].append('invented'))

    def test_source_rebase_requires_two_exact_inputs_without_approval(self):
        request = dict(expected_resolved_sha256='a' * 64, expected_registration_sha256='b' * 64)
        self.validator('animated-source-rebase-request-v1').validate(request)
        for mutate in (lambda r: r.pop('expected_registration_sha256'),
                       lambda r: r.update(expected_resolved_sha256='current'),
                       lambda r: r.update(approved=True)):
            self.rejects('animated-source-rebase-request-v1', request, mutate)


if __name__ == '__main__':
    unittest.main()
