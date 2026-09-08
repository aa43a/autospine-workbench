"""Head completion retains reviewed choices without adopting new guesses."""
from copy import deepcopy
import json
from pathlib import Path
import unittest

from tests.test_layer_binding import fixture
from autospine_workbench.asset.joints.binding_completion import build_completion, inherit_unchanged
from autospine_workbench.asset.joints.layer_binding import build_layer_bindings, validate_layer_bindings
from autospine_workbench.asset.joints.reviewed_skeleton import build_reviewed_skeleton
from autospine_workbench.benchmark.layer_binding_draft import build_layer_binding_draft
from autospine_workbench.resolved_project import canonical_sha256


class BindingCompletionTests(unittest.TestCase):
    def test_names_local_transform_and_legacy_preserved(self):
        for name in ('eyewhite-l', 'irides-r', 'mouth', ' ＥＹＥＢＲＯＷ－Ｌ ', 'headwear'):
            args = fixture(name)
            before = deepcopy(args)
            legacy = build_layer_bindings(*args)
            doc = build_completion(*args)
            self.assertEqual(args, before)
            self.assertEqual(build_layer_bindings(*args), legacy)
            self.assertEqual(legacy['bindings'][1]['options'], [])
            self.assertEqual(doc, validate_layer_bindings(*args, doc))
            option = doc['bindings'][1]['options'][0]
            self.assertEqual(option['bone_ids'], ['head'])
            self.assertIsInstance(option['setup_local']['x'], float)
            self.assertEqual(doc['bindings'][0], legacy['bindings'][0])

    def test_unknown_and_empty_stay_blocked(self):
        for name in ('objects', 'footwear', 'bottomwear', 'wings'):
            self.assertEqual(build_completion(*fixture(name))['bindings'][1]['options'], [])
        candidate, assisted, _ = fixture('headwear')
        candidate['layers'][1]['observed']['empty'] = True
        assisted['candidate_sha256'] = assisted['draft']['candidate_sha256'] = canonical_sha256(candidate)
        doc = build_completion(candidate, assisted, build_reviewed_skeleton(candidate, assisted))
        self.assertEqual(doc['bindings'][1]['options'], [])
        self.assertIn('empty_layer', doc['bindings'][1]['reason_codes'])

    def test_only_unchanged_choices_inherited(self):
        args = fixture('mouth')
        base, completed = build_layer_bindings(*args), build_completion(*args)
        old = build_layer_binding_draft(base)
        old['records'][0].update(action='bind', option_id='rigid:head', notes='reviewed')
        draft = inherit_unchanged(base, old, completed)
        self.assertEqual(draft['records'][0], old['records'][0])
        self.assertEqual(draft['records'][1]['action'], 'pending')
        self.assertNotEqual(draft['source_bindings_sha256'], old['source_bindings_sha256'])
        old['records'][1].update(action='exclude', notes='reviewed exclusion')
        with self.assertRaisesRegex(ValueError, 'changed_reviewed_layer'):
            inherit_unchanged(base, old, completed)

    def test_stale_source_and_tamper_rejected(self):
        args = fixture('mouth')
        base, doc = build_layer_bindings(*args), build_completion(*args)
        draft = build_layer_binding_draft(base)
        changed = deepcopy(doc)
        changed['source_skeleton_sha256'] = '0'*64
        with self.assertRaisesRegex(ValueError, 'source_mismatch'):
            inherit_unchanged(base, draft, changed)
        changed = deepcopy(doc)
        changed['bindings'][1]['options'][0]['setup_local']['x'] += 1
        with self.assertRaisesRegex(ValueError, 'completion_mismatch'):
            validate_layer_bindings(*args, changed)
        changed = deepcopy(doc)
        changed['bindings'].pop()
        with self.assertRaisesRegex(ValueError, 'source_mismatch'):
            inherit_unchanged(base, draft, changed)

    def test_schema(self):
        try:
            from jsonschema import Draft202012Validator
        except ImportError:
            self.skipTest('jsonschema unavailable')
        path = Path(__file__).resolve().parents[1]/'schemas/layer-binding-completion-v3.schema.json'
        Draft202012Validator(json.loads(path.read_text('utf-8'))).validate(build_completion(*fixture('mouth')))
