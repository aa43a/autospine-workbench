"""Common-lattice symmetry and conservative contour-chain readiness."""
from copy import deepcopy
import unittest
import numpy as np
from tests.test_seam_translation import fixture
from autospine_workbench.targets.spine43.same_frame_seam import compare_frame
from autospine_workbench.targets.spine43.seam_segments import chains


class SameFrameTests(unittest.TestCase):
    def test_identity_has_no_added_or_fixed_pixels(self):
        source,_=fixture();s={'triangle':[0,1,2],'barycentric':[.4,.3,.3]}
        boundaries={'leg':{'samples':[s]},'shoe':{'samples':[s]}}
        relation={'driver':'leg','follower':'shoe','pairs':[{'driver_sample':0,'follower_sample':0}]}
        textures={n:np.ones((8,8))*255 for n in boundaries}
        result,images=compare_frame(source,source,relation,boundaries,textures,1)
        self.assertEqual(result['gap_pixels'][0],result['gap_pixels'][1])
        self.assertEqual(result['new_gap_pixels'],0);self.assertEqual(result['fixed_gap_pixels'],0)
        self.assertEqual(result['mean_union_alpha_change'],0)
        np.testing.assert_array_equal(images[0],images[1])

    def test_swapping_versions_keeps_rect_and_reverses_pixel_changes(self):
        before,_=fixture();after=deepcopy(before)
        after['animations']['continuous-corrective-inspection']['attachments']['default']['leg']['leg']['deform'][1]['vertices']=[0]*12
        s={'triangle':[0,1,2],'barycentric':[.4,.3,.3]};bounds={'leg':{'samples':[s]},'shoe':{'samples':[s]}}
        relation={'driver':'leg','follower':'shoe','pairs':[{'driver_sample':0,'follower_sample':0}]};textures={n:np.ones((8,8))*255 for n in bounds}
        a,_=compare_frame(before,after,relation,bounds,textures,1);b,_=compare_frame(after,before,relation,bounds,textures,1)
        self.assertEqual(a['rect'],b['rect']);self.assertEqual(a['corridor_pixels'],b['corridor_pixels'])
        self.assertEqual(a['gap_pixels'],list(reversed(b['gap_pixels'])))
        self.assertEqual(a['new_gap_pixels'],b['fixed_gap_pixels'])

    def test_ordered_chain_uses_normalized_arc_length(self):
        samples=[{'pixel_xy':[i,0],'triangle':[0,1,2],'barycentric':[1-i/2,i/2,0]} for i in range(3)]
        result=chains(samples,[2,0,1],[[0,0],[2,0],[0,1]])
        self.assertEqual(result[0]['status'],'open_chain_candidate')
        self.assertEqual(result[0]['ordered_samples'],[0,1,2]);self.assertEqual(result[0]['u'],[0,.5,1])

    def test_branch_is_not_silently_parameterized(self):
        samples=[{'pixel_xy':p,'triangle':[0,1,2],'barycentric':[1,0,0]} for p in ([0,0],[1,0],[2,0],[1,1])]
        result=chains(samples,range(4),[[0,0],[1,0],[0,1]])
        self.assertEqual(result[0]['status'],'branched_pixel_neighborhood')
        self.assertNotIn('u',result[0])

    def test_isolated_samples_remain_fragments(self):
        samples=[{'pixel_xy':[i*10,0]} for i in range(2)]
        self.assertEqual([r['status'] for r in chains(samples,[0,1],[])],['fragment','fragment'])

    def test_zero_length_chain_is_rejected(self):
        samples=[{'pixel_xy':[i,0],'triangle':[0,1,2],'barycentric':[1,0,0]} for i in range(3)]
        with self.assertRaisesRegex(ValueError,'zero_length'):chains(samples,[0,1,2],[[0,0],[1,0],[0,1]])
