import unittest
from autospine_workbench.targets.spine43.seam_roi_context import analyze


class RoiContextTests(unittest.TestCase):
    def test_alpha_loss_alone_is_not_a_hole(self):
        result=analyze([[211]*3 for _ in range(3)],[[116]*3 for _ in range(3)],[1,1])
        self.assertFalse(result['center_after_below8'])
        self.assertEqual(result['new_low_alpha_pixels'],0)
        self.assertIsNone(result['center_distance_to_low_alpha_px'])

    def test_enclosed_hole_and_crop_connected_distinguished(self):
        before=[[255]*5 for _ in range(5)]
        after=[r[:] for r in before];after[2][2]=0
        self.assertEqual(analyze(before,after,[2,2])['components'][0]['context'],'enclosed_in_roi')
        after[1][2]=after[0][2]=0
        self.assertEqual(analyze(before,after,[2,2])['components'][0]['context'],'reaches_roi_edge')

    def test_diagonal_sensitivity_and_existing_transparency(self):
        before=[[255]*3 for _ in range(3)];before[0][0]=0
        after=[r[:] for r in before];after[1][1]=0
        self.assertEqual(analyze(before,after,[1,1],4)['components'][0]['context'],'enclosed_in_roi')
        result=analyze(before,after,[1,1],8)
        self.assertEqual(result['components'][0]['context'],'reaches_roi_edge')
        self.assertEqual(result['new_low_alpha_pixels'],1)

    def test_invalid_input_rejected(self):
        for before,after,point in (([[256]],[[0]],[0,0]),([[1]],[[1,2]],[0,0]),([[1]],[[1]],[2,2])):
            with self.assertRaises(ValueError):analyze(before,after,point)
