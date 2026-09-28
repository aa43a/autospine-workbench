import copy
import unittest
from m4_order_window_delivery import verify_capture


class WindowDeliveryTests(unittest.TestCase):
    def test_incomplete_or_regressed_capture_cannot_be_packaged(self):
        fixture=dict(rows=[dict(time=0),dict(time=1)])
        capture=dict(rows=[dict(time=t,vertex_delta=0,newly_below_alpha_eight=0,maximum_alpha_delta=0,
                               inside=False,maximum_channel_delta=0) for t in (0,1)],
                     switches=[dict(changed_pixels=0),dict(changed_pixels=0)],
                     switch_sample_status='no_change_over_one_channel_unit')
        verify_capture(capture,fixture)
        for kind in ('missing','outside','geometry','gap','switch'):
            with self.subTest(kind=kind):
                value=copy.deepcopy(capture)
                if kind=='missing':value['rows'].pop()
                if kind=='outside':value['rows'][0]['maximum_channel_delta']=1
                if kind=='geometry':value['rows'][0]['vertex_delta']=.01
                if kind=='gap':value['rows'][0]['newly_below_alpha_eight']=1
                if kind=='switch':value['switches'][0]['changed_pixels']=1
                with self.assertRaises(ValueError):verify_capture(value,fixture)
