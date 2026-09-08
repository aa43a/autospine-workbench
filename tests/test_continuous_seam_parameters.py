import unittest
from autospine_workbench.targets.spine43.continuous_seam_parameters import fit
from autospine_workbench.targets.spine43.continuous_parameter_validation import validate


class ContinuousParametersTests(unittest.TestCase):
    def test_plateau_spreads_symmetrically(self):
        values=fit([2,2,2],5,1)
        for a,b in zip(values,[1.9,2,2.1]):self.assertAlmostEqual(a,b)

    def test_reversal_corrected_within_budget(self):
        values=fit([1,3,2],5,1)
        for a,b in zip(values,[1,2.45,2.55]):self.assertAlmostEqual(a,b)

    def test_reverse_orientation(self):
        self.assertEqual(fit([3,2,1],5,-1),[3,2,1])

    def test_insufficient_length_and_budget_fail(self):
        with self.assertRaises(ValueError):fit([0,0,0],.1,1)
        with self.assertRaises(ValueError):fit([4,0],5,1,budget=.1)

    def test_endpoint_and_finite_validation(self):
        result=fit([0,0,0],5,1)
        for a,b in zip(result,[0,.1,.2]):self.assertAlmostEqual(a,b)
        with self.assertRaises(ValueError):fit([float('nan')],5,1)

    def test_validator_rejects_plateau_and_lost_source(self):
        sample=lambda t:{'parameter':t,'embedding':{'barycentric':[1.,0.,0.]}}
        group={'pairs':[0,1],'status':'candidate_requires_review','reference_parameters':[1.,1.],
               'samples':[sample(.95),sample(1.05)],'direction':1,'cost':.005,'max_world_shift_px':.5}
        relation={'source_pair_count':2,'blocked_pairs':[],'groups':[group]}
        report={'schema':'autospine.continuous-seam-parameters/v1','authority':'none','production_authorized':False,
                'status':'needs_review','analysis':{'relations':[relation]}}
        self.assertIs(validate(report),report)
        group['samples'][1]['parameter']=.95
        with self.assertRaisesRegex(ValueError,'parameter_order'):validate(report)
        relation['groups']=[]
        with self.assertRaisesRegex(ValueError,'parameter_source_coverage'):validate(report)
