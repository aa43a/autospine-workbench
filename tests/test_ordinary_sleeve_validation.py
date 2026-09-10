"""Exact ordinary-sleeve motion inventories and status cannot be forged."""
from copy import deepcopy
import json
from pathlib import Path
import unittest
from jsonschema import Draft202012Validator
from test_ordinary_sleeve import fixture
from autospine_workbench.asset.planning.ordinary_sleeve import build
from autospine_workbench.asset.planning.ordinary_sleeve_validation import validate
from autospine_workbench.resolved_project import canonical_sha256


class OrdinarySleeveValidationTests(unittest.TestCase):
    def test_real_output_schema_and_exact_replay(self):
        source, draft, skeleton = fixture(); doc = build(source, draft, skeleton)
        schema = json.loads(Path('schemas/ordinary-sleeve-motion-v1.schema.json').read_text())
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(doc)
        self.assertEqual(validate(doc, skeleton, source=source, draft=draft), doc)
        draft['records'][0]['assignments'][2]['role'] = 'hanging_cloth'
        source['draft_sha256'] = canonical_sha256(draft)
        unavailable = build(source, draft, skeleton)
        Draft202012Validator(schema).validate(unavailable)
        self.assertEqual(validate(unavailable, skeleton), unavailable)

    def test_empty_duplicate_tracks_wrong_drivers_and_false_status_rejected(self):
        source, draft, skeleton = fixture(); doc = build(source, draft, skeleton)
        mutations = [lambda r: r.update(tracks=[]),
                     lambda r: r['tracks'].__setitem__(1, deepcopy(r['tracks'][0])),
                     lambda r: r['tracks'][0]['drivers'].__setitem__(0, 'hand_l'),
                     lambda r: r['tracks'][0]['qa'].pop(),
                     lambda r: r['tracks'][0]['samples'].pop(),
                     lambda r: r['tracks'][0].update(failed_ticks=3),
                     lambda r: r.update(status='blocked'),
                     lambda r: r['tracks'][0]['samples'][2]['points'][0].__setitem__(0, 99.)]
        for mutation in mutations:
            bad = deepcopy(doc); mutation(bad['records'][0])
            with self.assertRaises(ValueError): validate(bad, skeleton)

    def test_numeric_failure_and_unknown_cannot_be_removed_with_full_closure(self):
        source, draft, skeleton = fixture()
        draft['records'][0]['assignments'][2]['role'] = 'unknown'
        source['draft_sha256'] = canonical_sha256(draft)
        doc = build(source, draft, skeleton)
        self.assertEqual(validate(doc, skeleton, source=source, draft=draft), doc)
        bad = deepcopy(doc)
        bad['records'][0].update(status='candidate_requires_review', reason_codes=['runtime_and_alpha_contact_required'])
        with self.assertRaises(ValueError): validate(bad, skeleton, source=source, draft=draft)
        source, draft, skeleton = fixture()
        entries = source['records'][0]['mesh']['weights'][0]
        entries[1]['weight'] = 0.; entries[2]['weight'] = 1.
        doc = build(source, draft, skeleton)
        self.assertEqual(validate(doc, skeleton), doc)
        doc['records'][0].update(status='candidate_requires_review', reason_codes=['runtime_and_alpha_contact_required'])
        with self.assertRaises(ValueError): validate(doc, skeleton)


if __name__ == '__main__': unittest.main()
