"""Explicit harmonic profile cannot change old repair identities or evade gates."""
from copy import deepcopy
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from jsonschema import Draft202012Validator, ValidationError
from referencing import Registry, Resource
from test_ordinary_sleeve_repair_contract import failing_fixture
from autospine_workbench.asset.planning.ordinary_sleeve_repair import build, PROFILE, HARMONIC_PROFILE
from autospine_workbench.asset.planning.ordinary_sleeve_repair_validation import validate
from autospine_workbench.asset.planning.ordinary_sleeve_repair_review import render
from autospine_workbench.resolved_project import canonical_sha256


class HarmonicRepairTests(unittest.TestCase):
    def test_old_default_identity_is_exact_and_new_profile_is_explicit(self):
        args=failing_fixture()
        legacy=build(*args)
        # Independently obtained from git HEAD's original unmodified v1 builder.
        self.assertEqual(canonical_sha256(legacy),'03408b91defc0bff68555962d9e68e9669ffb73b70a52d85544d27a4a16746ed')
        self.assertEqual(legacy,build(*args,profile=PROFILE))
        current=build(*args,profile=HARMONIC_PROFILE)
        self.assertNotEqual(canonical_sha256(current),canonical_sha256(legacy))
        self.assertEqual(current['records'][0]['before'],legacy['records'][0]['before'])
        self.assertEqual([t['id'] for t in current['records'][0]['trials']],['cuff_absolute_harmonic'])
        self.assertEqual(current,validate(current,args[2],source=args[0],draft=args[1]))
        self.assertIn(HARMONIC_PROFILE,render(current))
        self.assertFalse(current['global_replacement_authorized'])

    def test_schema_and_replay_reject_profile_mixing_and_tampering(self):
        args=failing_fixture(); doc=build(*args,profile=HARMONIC_PROFILE)
        schema=json.loads(Path('schemas/ordinary-sleeve-repair-v1.schema.json').read_text())
        motion=json.loads(Path('schemas/ordinary-sleeve-motion-v1.schema.json').read_text())
        registry=Registry().with_resource('ordinary-sleeve-motion-v1.schema.json',Resource.from_contents(motion))
        checker=Draft202012Validator(schema,registry=registry);checker.check_schema(schema);checker.validate(doc)
        mixed=deepcopy(doc);mixed['profile']=PROFILE
        with self.assertRaises(ValidationError):checker.validate(mixed)
        for bad in (mixed,deepcopy(doc)):
            if bad is not mixed:bad['records'][0]['trials'][0]['tracks'][0]['qa'][1]['inversions']+=1
            with self.assertRaises(ValueError):validate(bad,args[2],source=args[0],draft=args[1])

    def test_rejected_trial_keeps_original_row(self):
        args=failing_fixture()
        with patch('autospine_workbench.asset.planning.ordinary_sleeve_repair.gate',return_value=(['new_inversion'],True)):
            doc=build(*args,profile=HARMONIC_PROFILE)
        row=doc['records'][0]
        self.assertFalse(row['selected']);self.assertEqual(row['selected_row'],row['before'])
        self.assertIn('new_inversion',row['trials'][0]['reason_codes'])
        self.assertEqual(row['selected_row']['status'],'blocked')


if __name__=='__main__':unittest.main()
