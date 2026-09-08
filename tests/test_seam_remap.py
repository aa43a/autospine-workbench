"""Complete local assignment, bounded search and no loss of hard pairs."""
from copy import deepcopy
import unittest
from autospine_workbench.targets.spine43.seam_remap import assignment,remap,bake
from tests.test_seam_translation import fixture


class SeamRemapTests(unittest.TestCase):
    def test_minimum_cost_requires_reassigning_greedy_choice(self):
        options={0:[(1,1.),(2,2.)],1:[(1,1.5),(2,100.)]}
        self.assertEqual(assignment(options),{0:2,1:1})
        self.assertEqual(assignment(dict(reversed(list(options.items())))),{0:2,1:1})

    def test_incomplete_and_oversized_assignment_is_blocked(self):
        self.assertIsNone(assignment({0:[(1,1)],1:[(1,1)]}))
        self.assertIsNone(assignment({i:[(i,1)] for i in range(9)}))
        self.assertIsNone(assignment({0:[(i,1) for i in range(17)]}))

    def test_tie_is_stable(self):
        self.assertEqual(assignment({1:[(2,1),(1,1)],0:[(2,1),(1,1)]}),{0:1,1:2})

    def test_failed_remap_keeps_every_pair_and_source(self):
        source,_=fixture();keys=source['animations']['continuous-corrective-inspection']['attachments']['default']['leg']['leg']['deform']
        keys[1]['vertices'][4]=8;keys[1]['vertices'][6]=8
        s0={'triangle':[0,1,2],'barycentric':[1,0,0],'pixel_xy':[0,0]};s1={'triangle':[0,1,2],'barycentric':[0,1,0],'pixel_xy':[1,0]}
        report={'boundaries':{'leg':{'samples':[s0,s1]},'shoe':{'samples':[s0]}},'relations':[{'driver':'leg','follower':'shoe','pairs':[
            {'driver_sample':0,'follower_sample':0,'setup_distance_px':0},{'driver_sample':1,'follower_sample':0,'setup_distance_px':2}]}]}
        before=deepcopy(report);result,changes=remap(source,report)
        self.assertEqual(result,before);self.assertEqual(report,before)
        self.assertEqual(changes[0]['status'],'blocked_no_complete_assignment')
        self.assertEqual(changes[0]['replacements'],[])
        report['boundaries']['shoe']['samples'].append(deepcopy(s1))
        successful,changes=remap(source,report)
        self.assertEqual(changes[0]['status'],'candidate_requires_review')
        self.assertEqual([p['driver_sample'] for p in successful['relations'][0]['pairs']],[0,1])
        self.assertEqual(len({p['follower_sample'] for p in successful['relations'][0]['pairs']}),2)
        self.assertEqual([p['follower_sample'] for p in report['relations'][0]['pairs']],[0,0])

    def test_invalid_source(self):
        with self.assertRaisesRegex(ValueError,'animation_invalid'):bake({'animations':{}},{})
