import unittest
from m4_local_depth_capture import framebuffer_rect,selected


class LocalCaptureTests(unittest.TestCase):
    def test_world_y_down_roi_maps_to_top_left_image_without_vertical_flip(self):
        info=dict(left=-20,bottom=-80,width=100,height=120)
        self.assertEqual(framebuffer_rect([-10,-30,5,6],info),(10,10,5,6))
        self.assertEqual(framebuffer_rect([-20,-40,100,120],info),(0,0,100,120))
        with self.assertRaisesRegex(ValueError,'outside_framebuffer'):
            framebuffer_rect([-21,-40,5,6],info)

    def test_representative_selection_keeps_first_peak_last_per_pair(self):
        def row(t,n,pair):return dict(pair=pair,check=dict(time=t,counts=dict(ambiguous=n),
                                                        status='requires_partition_or_more_depth'))
        result=selected(dict(records=[row(3,1,['a','b']),row(0,2,['a','b']),
                                      row(1,9,['a','b']),row(2,4,['a','b'])]))
        self.assertEqual([r['check']['time'] for r in result],[0,1,3])


if __name__=='__main__':unittest.main()
