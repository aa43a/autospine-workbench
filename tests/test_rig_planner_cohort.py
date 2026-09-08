"""Cohort statistics must preserve decisions and reject incomparable scopes."""
from copy import deepcopy
import unittest
from tests.test_rig_planner import fixture
from autospine_workbench.asset.planning.rig_planner import build
from autospine_workbench.benchmark.rig_planner_cohort import summarize, render


class CohortTests(unittest.TestCase):
    def test_full_source_counts_and_non_authority(self):
        first = build(*fixture()); second = deepcopy(first)
        second['character_id'] = 'second'
        second['layers'][0]['existing_action'] = 'bind'
        entries = [('one', first, first['scope']), ('two', second, second['scope'])]
        before = deepcopy(entries); doc = summarize(entries)
        self.assertEqual(entries, before)
        self.assertEqual(doc['total_layers'], 2)
        self.assertEqual(doc['characters'][0]['pending_strategies'], {'facial':1})
        self.assertEqual(doc['characters'][1]['pending_strategies'], {})
        self.assertEqual(doc['characters'][1]['existing_actions'], {'bind':1})
        self.assertIsNone(doc['accuracy']); self.assertFalse(doc['production_authorized'])
        self.assertIn('1 / 0', render(doc))

    def test_refuse_partial_mixed_and_duplicate_plans(self):
        plan = build(*fixture())
        with self.assertRaises(ValueError): summarize([])
        with self.assertRaises(ValueError): summarize([('one',plan,plan['scope']+['missing'])])
        entry = ('one',plan,plan['scope'])
        with self.assertRaises(ValueError): summarize([entry,entry])
        for key,value in [('profile','other'), ('authority','approved'), ('production_authorized',True)]:
            bad = deepcopy(plan); bad[key] = value
            with self.assertRaises(ValueError): summarize([('one',bad,bad['scope'])])
