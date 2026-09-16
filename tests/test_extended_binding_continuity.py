import json
import unittest
import test_rebuilt_binding_replay as fixtures
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.targets.character43.rebuilt_binding_continuity import unchanged_layers,predecessor


class ExtendedContinuityTests(unittest.TestCase):
    def setUp(self):
        case=fixtures.RebuiltBindingTests();case.setUp();self.addCleanup(case.doCleanups)
        self.old=dict(case.b.source);self.new=dict(case.b.target)
        for files in (self.old,self.new):
            receipt=json.loads(files['final-region-exclusion.json'])
            receipt['schema']='autospine.final-region-exclusion/v2'
            files['final-region-exclusion.json']=canonical_bytes(receipt)

    def test_explicit_stage_scope_and_unchanged_bindings(self):
        self.assertEqual(unchanged_layers(self.old,self.new),[])
        self.assertEqual(unchanged_layers(self.old,self.new,extended=True),['shirt'])
        changed={**self.new,'images/shirt.png':b'changed'}
        self.assertEqual(unchanged_layers(self.old,changed,extended=True),[])

    def test_predecessor_must_be_nonempty_preserved_subset(self):
        first={'region_id':'a','image_sha256':'1'};second={'region_id':'b','image_sha256':'2'}
        self.assertTrue(predecessor([first],[first,second],extended=True))
        self.assertFalse(predecessor([first],[first,second]))
        self.assertFalse(predecessor([],[first],extended=True))
        self.assertFalse(predecessor([first],[second],extended=True))
        self.assertFalse(predecessor([first],[{**first,'image_sha256':'changed'}],extended=True))
