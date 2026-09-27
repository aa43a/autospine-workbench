from copy import deepcopy
import unittest
from unittest.mock import patch
from test_limb_transverse_repair import fixture
from autospine_workbench.targets.character43.fixed_surface_sampling import build


class FixedSurfaceSamplingTests(unittest.TestCase):
    def test_retains_source_unselected_content_and_every_requested_time(self):
        parent=fixture()
        parent['animations']['motion']['attachments']={'default':{'leg':{'leg':{'deform':[
            dict(time=0,vertices=[0.]*6),dict(time=1,vertices=[1.,2.,-2.,4.,3.,-1.])]}}}}
        before=deepcopy(parent)
        result,report=build(parent,'motion','leg',[0,.371,1],rounds=2)
        self.assertEqual(parent,before)
        for key in ('bones','skins','slots'):self.assertEqual(result[key],parent[key])
        self.assertEqual(result['animations']['motion']['bones'],parent['animations']['motion']['bones'])
        self.assertTrue({0,.371,1}<=set(report['times']))
        self.assertLessEqual(len(report['history']),2)
        self.assertTrue(all(r['keys']<=2049 for r in report['history']))
        self.assertFalse(report['selected'])

    def test_exact_key_failure_is_not_hidden_by_more_samples(self):
        parent=fixture();candidate=deepcopy(parent)
        candidate['animations']['motion']['attachments']={'default':{'leg':{'leg':{'deform':[
            dict(time=t,vertices=[0.,0.,0.,-10.,-10.,0.]) for t in (0.,1.)]}}}}
        with patch('autospine_workbench.targets.character43.fixed_surface_sampling.compensate',return_value=(candidate,{})):
            _,report=build(parent,'motion','leg',[0,.5,1])
        self.assertEqual(report['status'],'exact_key_failure')
        self.assertEqual(len(report['history']),1)

    def test_rejects_invalid_rounds_and_times(self):
        for rounds in (0,9,True):
            with self.assertRaises(ValueError):build(fixture(),'motion','leg',[0,1],rounds=rounds)
        with self.assertRaises(ValueError):build(fixture(),'motion','leg',[-1])
