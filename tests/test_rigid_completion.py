"""Shoe candidates preserve historical identities and explicit review decisions."""
from copy import deepcopy
import json
from pathlib import Path
import unittest

from tests.test_layer_binding import fixture
from autospine_workbench.asset.joints.binding_completion import build_completion as v3
from autospine_workbench.asset.joints.rigid_completion import build_completion, inherit_unchanged
from autospine_workbench.asset.joints.layer_binding import build_layer_bindings, validate_layer_bindings
from autospine_workbench.asset.joints.reviewed_skeleton import build_reviewed_skeleton
from autospine_workbench.benchmark.layer_binding_draft import build_layer_binding_draft
from autospine_workbench.resolved_project import canonical_sha256


class RigidCompletionTests(unittest.TestCase):
    def test_shoes_are_candidates_and_legacy_unchanged(self):
        for name, side in [('footwear-l', 'l'), (' ＳＨＯＥＳ－Ｒ ', 'r'), ('shoe', None)]:
            args = fixture(name)
            legacy = canonical_sha256(v3(*args))
            before = deepcopy(args)
            doc = build_completion(*args)
            self.assertEqual(args, before)
            self.assertEqual(canonical_sha256(v3(*args)), legacy)
            self.assertEqual(v3(*args)['bindings'][1]['options'], [])
            self.assertEqual(validate_layer_bindings(*args, doc), doc)
            row = doc['bindings'][1]
            self.assertEqual([o['bone_ids'] for o in row['options']], [['foot_l'], ['foot_r']])
            self.assertEqual(row['suggested_option_id'], 'rigid:foot_'+side if side else None)
            self.assertEqual(row['status'], 'needs_review')
            self.assertEqual(build_layer_binding_draft(doc)['records'][1]['action'], 'pending')

    def test_unsupported_and_conflicting_semantics(self):
        for name in ('boots', 'objects', 'shoe-decoration'):
            self.assertEqual(build_completion(*fixture(name))['bindings'][1]['options'], [])
        candidate, assisted, _ = fixture('footwear-l')
        candidate['layers'][1]['semantic'] = 'accessory.object'
        assisted['candidate_sha256'] = assisted['draft']['candidate_sha256'] = canonical_sha256(candidate)
        skeleton = build_reviewed_skeleton(candidate, assisted)
        self.assertEqual(build_completion(candidate, assisted, skeleton)['bindings'][1]['options'], [])

    def test_empty_layer_not_completed(self):
        candidate, assisted, _ = fixture('shoe')
        candidate['layers'][1]['observed']['empty'] = True
        assisted['candidate_sha256'] = assisted['draft']['candidate_sha256'] = canonical_sha256(candidate)
        doc = build_completion(candidate, assisted, build_reviewed_skeleton(candidate, assisted))
        self.assertEqual(doc['bindings'][1]['options'], [])

    def test_all_review_decisions_survive_upgrade(self):
        args = fixture('footwear-l')
        for builder in (build_layer_bindings, v3):
            base, completed = builder(*args), build_completion(*args)
            for action in ('pending', 'exclude', 'requires_split', 'semantic_review'):
                old = build_layer_binding_draft(base)
                old['records'][0].update(action='bind', option_id='rigid:head', notes='confirmed head')
                old['records'][1].update(action=action, notes='keep this decision')
                new = inherit_unchanged(base, old, completed)
                self.assertEqual(new['records'], old['records'])
                self.assertNotEqual(new['source_bindings_sha256'], old['source_bindings_sha256'])

    def test_stale_and_tampered_data_rejected(self):
        args = fixture('shoe')
        base, doc = v3(*args), build_completion(*args)
        old = build_layer_binding_draft(base)
        old['records'][0].update(action='bind', option_id='rigid:head')
        changed = deepcopy(doc)
        changed['bindings'][0]['options'][0]['setup_local']['x'] += 1
        with self.assertRaisesRegex(ValueError, 'changed_reviewed_layer'):
            inherit_unchanged(base, old, changed)
        with self.assertRaisesRegex(ValueError, 'completion_mismatch'):
            validate_layer_bindings(*args, changed)
        changed = deepcopy(doc)
        changed['source_skeleton_sha256'] = '0'*64
        with self.assertRaisesRegex(ValueError, 'source_mismatch'):
            inherit_unchanged(base, old, changed)

    def test_schema(self):
        from jsonschema import Draft202012Validator
        path = Path(__file__).resolve().parents[1]/'schemas/layer-binding-completion-v4.schema.json'
        Draft202012Validator(json.loads(path.read_text('utf-8'))).validate(build_completion(*fixture('shoe')))
