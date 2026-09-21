from copy import deepcopy
import unittest
from autospine_workbench.targets.character43.depth_order_subset import build


class Probe:
    def pair(self,a,b,time):
        visible={frozenset(p) for p in [('a','x'),('x','body'),('a','body'),('c','body')]}
        return dict(overlap_pixels=int(frozenset((a,b)) in visible))


class OrderSubsetTests(unittest.TestCase):
    def test_conflicted_region_preserved_and_independent_region_can_move(self):
        doc=dict(slots=[dict(name=n) for n in ['a','c','x','body']],animations={'move':{}})
        depth=dict(pairs=[dict(arm_slot=n,torso_slot='body',evidence_source='uniform_sampled_local_depth',
            samples=[dict(tick=0,ambiguous=False,current_front_slot=n)]) for n in ['a','c']])
        original=deepcopy(doc)
        candidate,report=build(doc,'move',depth,Probe())
        self.assertEqual(doc,original)
        self.assertEqual(report['status'],'partial_candidate')
        self.assertEqual(report['excluded'],[dict(pair=['a','body'],reason_code='visible_order_cycle_preserve_setup')])
        self.assertEqual(report['retained_pairs'],[['c','body']])
        self.assertEqual(report['attempts'][-1]['frames'][0]['order'],['a','x','body','c'])
        self.assertIn('drawOrder',candidate['animations']['move'])
        self.assertFalse(report['selected'])

    def test_budget_error_is_not_resolved_by_dropping_regions(self):
        class NoBudget:
            def pair(self,*args):raise ValueError('depth_overlap_pixel_budget')
        doc=dict(slots=[dict(name=n) for n in ['a','body']],animations={'move':{}})
        depth=dict(pairs=[dict(arm_slot='a',torso_slot='body',samples=[dict(tick=0,ambiguous=False,current_front_slot='a')])])
        candidate,report=build(doc,'move',depth,NoBudget())
        self.assertIsNone(candidate);self.assertEqual(report['excluded'],[])
        self.assertEqual(len(report['attempts']),1)


if __name__=='__main__':unittest.main()
