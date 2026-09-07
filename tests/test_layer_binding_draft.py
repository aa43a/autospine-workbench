"""Option-based drafts preserve complete layers and never carry mesh weights."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from autospine_workbench.benchmark.layer_binding_draft import (
    build_layer_binding_draft, validate_layer_binding_draft,
)


def fixture():
    return {'schema': 'autospine.layer-binding-candidates/v2', 'authority': 'none',
            'production_authorized': False, 'status': 'needs_review', 'bindings': [
                {'layer_id': 'layer-000', 'status': 'needs_review', 'options': [
                    {'id': 'arm-rigid', 'mode': 'rigid', 'bone_ids': ['upperarm_l']},
                    {'id': 'arm-chain', 'mode': 'mesh_chain', 'bone_ids': ['upperarm_l', 'forearm_l']}]},
                {'layer_id': 'layer-001', 'status': 'blocked', 'options': []}]}


class LayerBindingDraftTests(unittest.TestCase):
    def setUp(self):
        self.bindings = fixture()
        self.draft = build_layer_binding_draft(self.bindings)

    def test_initial_pending_exact_pure_and_independent_from_legacy(self):
        before = deepcopy((self.bindings, self.draft))
        self.assertEqual(validate_layer_binding_draft(self.bindings, self.draft), self.draft)
        self.assertEqual((self.bindings, self.draft), before)
        self.assertTrue(all(r['action'] == 'pending' and r['option_id'] is None for r in self.draft['records']))
        self.assertNotIn('bone_id', self.draft['records'][0])
        legacy = deepcopy(self.bindings)
        legacy['schema'] = 'autospine.region-binding-candidates/v1'
        with self.assertRaises(ValueError):
            build_layer_binding_draft(legacy)

    def test_explicit_chain_choice_preserved_without_weights_or_authority(self):
        self.draft['records'][0].update(action='bind', option_id='arm-chain', notes='Two bones\nReview\tseam')
        result = validate_layer_binding_draft(self.bindings, self.draft)
        self.assertEqual(result, self.draft)
        self.assertEqual(result['authority'], 'none')
        self.assertIs(result['production_authorized'], False)
        self.assertEqual(result['records'][0]['option_id'], 'arm-chain')
        result['records'][0]['weights'] = [0.5, 0.5]
        with self.assertRaises(ValueError):
            validate_layer_binding_draft(self.bindings, result)

    def test_changed_source_and_unknown_or_blocked_option_fail(self):
        self.draft['records'][0].update(action='bind', option_id='missing')
        with self.assertRaises(ValueError):
            validate_layer_binding_draft(self.bindings, self.draft)
        self.draft = build_layer_binding_draft(self.bindings)
        self.draft['records'][1].update(action='bind', option_id='arm-chain')
        with self.assertRaises(ValueError):
            validate_layer_binding_draft(self.bindings, self.draft)
        self.draft = build_layer_binding_draft(self.bindings)
        self.bindings['bindings'][0]['options'][1]['bone_ids'].append('hand_l')
        with self.assertRaises(ValueError):
            validate_layer_binding_draft(self.bindings, self.draft)

    def test_all_records_in_source_order_required(self):
        for change in (lambda d: d['records'].pop(), lambda d: d['records'].reverse(),
                       lambda d: d['records'].__setitem__(1, deepcopy(d['records'][0]))):
            doc = deepcopy(self.draft)
            change(doc)
            with self.assertRaises(ValueError):
                validate_layer_binding_draft(self.bindings, doc)

    def test_nonbind_cannot_select_and_exceptions_require_notes(self):
        for action in ('pending', 'requires_split', 'exclude', 'semantic_review'):
            doc = deepcopy(self.draft)
            doc['records'][0].update(action=action, option_id='arm-chain', notes='reason')
            with self.assertRaises(ValueError):
                validate_layer_binding_draft(self.bindings, doc)
        for action in ('requires_split', 'exclude', 'semantic_review'):
            doc = deepcopy(self.draft)
            doc['records'][0].update(action=action, notes=' \n\t')
            with self.assertRaises(ValueError):
                validate_layer_binding_draft(self.bindings, doc)
            doc['records'][0]['notes'] = 'Independent review\r\nrequired'
            validate_layer_binding_draft(self.bindings, doc)

    def test_unknown_types_notes_and_authority_rejected(self):
        for change in (lambda d: d.update(production_authorized=0), lambda d: d.update(authority='human'),
                       lambda d: d['records'][0].update(action=['bind']),
                       lambda d: d['records'][0].update(notes='bad\x00'),
                       lambda d: d['records'][0].update(notes='x' * 2001)):
            doc = deepcopy(self.draft)
            change(doc)
            with self.assertRaises(ValueError):
                validate_layer_binding_draft(self.bindings, doc)

    def test_invalid_option_source_rejected(self):
        for change in (lambda s: s['bindings'][0]['options'].append(deepcopy(s['bindings'][0]['options'][0])),
                       lambda s: s['bindings'][0]['options'][0].update(bone_ids=['a', 'b']),
                       lambda s: s['bindings'][0]['options'][1].update(bone_ids=['a']),
                       lambda s: s['bindings'][0]['options'][1].update(bone_ids=['a', 'a']),
                       lambda s: s['bindings'][0]['options'][1].update(mode='weights'),
                       lambda s: s.update(status='blocked')):
            source = deepcopy(self.bindings)
            change(source)
            with self.assertRaises(ValueError):
                build_layer_binding_draft(source)

    def test_schema(self):
        try:
            from jsonschema import Draft202012Validator
        except ImportError:
            self.skipTest('jsonschema unavailable')
        schema = json.loads((ROOT / 'schemas/layer-binding-draft-v2.schema.json').read_text('utf-8'))
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema)
        validator.validate(self.draft)
        self.draft['records'][0].update(action='bind', option_id='arm-chain')
        validator.validate(self.draft)
        self.draft['records'][0]['option_id'] = None
        self.assertTrue(list(validator.iter_errors(self.draft)))


if __name__ == '__main__':
    unittest.main()
