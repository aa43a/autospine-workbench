import unittest
from autospine_workbench.targets.character43.depth_sample_times import select, repair_times


class SampleTimesTests(unittest.TestCase):
    def test_preserves_clipped_source_offset_and_orders_distinct_samples(self):
        samples=[dict(tick=t,source_tick=t+5000000) for t in (0,1000000,2000000)]
        result=select(samples,[1.0001,.9999,1,1.5,1])
        self.assertEqual([r['tick'] for r in result],[999900,1000000,1000100,1500000])
        self.assertTrue(all(r['source_tick']-r['tick']==5000000 for r in result))

    def test_schedule_keeps_keys_midpoints_and_both_sides_of_switch(self):
        doc=dict(animations={'test':dict(slots={'a':dict(alpha=[dict(time=.75,value=0)])})})
        depth=dict(pairs=[dict(samples=[dict(tick=t) for t in (0,1000000,2000000)])])
        self.assertEqual(repair_times(doc,'test',depth),[0,.5,.7499,.75,.7501,1,1.5,2])
        self.assertIsNone(repair_times(doc,'test',dict(pairs=[])))

    def test_rejects_outside_times_and_changed_mapping(self):
        samples=[dict(tick=0,source_tick=1),dict(tick=1000000,source_tick=1000001)]
        for times in ([],[-.001],[1.1],[float('nan')],[True],[0]*2050):
            with self.assertRaises(ValueError):select(samples,times)
        samples[1]['source_tick']+=1
        with self.assertRaisesRegex(ValueError,'mapping_changed'):select(samples,[.5])

    def test_integer_tick_roundtrip_does_not_drop_last_source_sample(self):
        for tick in (1000001,1933333,3966667):
            rows=[dict(tick=0,source_tick=0),dict(tick=tick,source_tick=tick)]
            self.assertEqual(select(rows,[tick/1e6])[-1]['source_tick'],tick)
