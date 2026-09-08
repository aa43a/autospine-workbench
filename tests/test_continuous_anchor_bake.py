from copy import deepcopy
import unittest
from unittest.mock import patch
from autospine_workbench.targets.spine43.continuous_anchor_bake import bake


class AnchorBakeTests(unittest.TestCase):
    def fixture(self):
        anchor={'triangle':[0,1,2],'barycentric':[1.,0.,0.],'pixel_xy':[0,0]}
        baseline={'boundaries':{'d':{'samples':[deepcopy(anchor)]},'f':{'samples':[deepcopy(anchor)]}},
                  'relations':[{'driver':'d','follower':'f','pairs':[{'driver_sample':0,'follower_sample':0,'setup_distance_px':0.} for _ in range(2)]}]}
        params={'analysis':{'relations':[{'driver':'d','follower':'f','groups':[{'status':'candidate_requires_review','pairs':[0],
                'samples':[{'embedding':{'triangle':[0,1,2],'barycentric':[.5,.5,0.]},'pixel_xy':[.5,0.]}]}]}]}}
        return baseline,params

    def test_replacement_is_pure_and_keeps_unhandled_pairs(self):
        baseline,params=self.fixture();original=deepcopy(baseline)
        def solver(source,files,mapped):
            self.assertEqual(len(mapped['relations'][0]['pairs']),2)
            self.assertEqual(mapped['relations'][0]['pairs'][0]['follower_sample'],1)
            self.assertEqual(mapped['relations'][0]['pairs'][1],baseline['relations'][0]['pairs'][1])
            return {'animations':{'alpha-seam-inspection':{}}},{}
        with patch('autospine_workbench.targets.spine43.continuous_anchor_bake.world',return_value={n:[[0,0],[1,0],[0,1]] for n in ('d','f')}),patch('autospine_workbench.targets.spine43.continuous_anchor_bake.bake_from_report',side_effect=solver):
            doc,qa=bake({}, {},baseline,params)
        self.assertEqual(baseline,original);self.assertEqual(qa['replacement_count'],1)
        self.assertEqual(set(doc['animations']),{'continuous-anchor-inspection'})

    def test_mismatched_relation_count_rejected(self):
        baseline,params=self.fixture();params['analysis']['relations']=[]
        with self.assertRaisesRegex(ValueError,'anchor_bake_relation_count'):bake({}, {},baseline,params)

    def test_missing_sample_does_not_silently_truncate(self):
        baseline,params=self.fixture();params['analysis']['relations'][0]['groups'][0]['samples']=[]
        with patch('autospine_workbench.targets.spine43.continuous_anchor_bake.world',return_value={}):
            with self.assertRaisesRegex(ValueError,'anchor_bake_sample_count'):bake({}, {},baseline,params)
