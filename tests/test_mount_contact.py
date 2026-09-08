"""Distinguish projected interiors from true alpha boundaries before clipping."""
import unittest
from autospine_workbench.asset.planning.mount_contact import local_pair, boundary, mask
from tests.test_rig_planner import fixture


def rect(x,y,w,h):return {(a,b) for a in range(x,x+w) for b in range(y,y+h)}


class ContactTests(unittest.TestCase):
    def test_close_boundaries_and_separation(self):
        source=rect(0,0,10,10)
        result=local_pair(source,rect(12,0,10,10),[9.5,4.5],5)
        self.assertEqual(result['status'],'boundary_pair_support')
        self.assertGreater(result['boundary_pair_pixels'],0)
        self.assertEqual(result['overlap_pixels'],0)
        self.assertEqual(local_pair(source,rect(20,0,10,10),[9.5,4.5],5)['status'],'no_local_support')

    def test_roi_border_is_not_target_boundary(self):
        result=local_pair(rect(0,0,10,10),rect(-100,-100,210,210),[9.5,4.5],3)
        self.assertEqual(result['status'],'boundary_over_target_interior')
        self.assertEqual(result['boundary_pair_pixels'],0)
        self.assertGreater(result['overlap_pixels'],0)

    def test_interior_overlap_is_not_boundary_contact(self):
        result=local_pair(rect(0,0,12,12),rect(5,5,2,2),[11.5,5.5],12)
        self.assertEqual(result['status'],'overlap_only')
        self.assertEqual(result['overlap_pixels'],4)
        self.assertEqual(result['boundary_near_target_pixels'],0)

    def test_empty_translation_and_determinism(self):
        self.assertEqual(local_pair(set(),set(),[0,0],3)['status'],'no_source_boundary')
        source=rect(0,0,10,10);target=rect(12,0,10,10)
        a=local_pair(source,target,[9.5,4.5],5)
        b=local_pair({(x+100,y-20) for x,y in source},{(x+100,y-20) for x,y in target},[109.5,-15.5],5)
        for key in ('status','overlap_pixels','boundary_pair_pixels','boundary_near_target_pixels'):
            self.assertEqual(a[key],b[key])
        self.assertEqual(a,local_pair(source,target,[9.5,4.5],5))
        self.assertEqual(len(boundary(rect(0,0,3,3))),8)

    def test_invalid_geometry_and_image_fail_closed(self):
        with self.assertRaises(ValueError):local_pair({(0,0)},set(),[float('nan'),0],3)
        candidate,_,_,_,_=fixture()
        with self.assertRaises(ValueError):mask(candidate['layers'][0],b'changed')
