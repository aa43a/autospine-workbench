import unittest
from autospine_workbench.targets.character43.motion_hand_status import summarize,render


class HandStatusTests(unittest.TestCase):
    def test_intervals_split_and_clip_time_rebased(self):
        rows=[dict(time=t,hands={s:dict(projected_area_fraction=v) for s in ('left','right')})
              for t,v in [(0,.1),(1,.1),(2,.3),(3,.15),(4,.1)]]
        records=summarize(rows,(1000000,4000000));r=records[0]
        self.assertEqual(r['sampled_count'],4)
        self.assertEqual([(x['start'],x['end'],x['samples']) for x in r['intervals']],[(0,0,1),(2,3,2)])
        self.assertEqual(records[1]['intervals'],r['intervals'])

    def test_unavailable_is_not_presented_as_pass_and_reason_escaped(self):
        html=render(dict(records=[],reason='<script>')).decode()
        self.assertIn('&lt;script&gt;',html)
        self.assertIn('不代表目标贴图正确',html)
