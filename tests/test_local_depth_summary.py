import unittest
from autospine_workbench.targets.character43.local_depth_summary import summarize


class SummaryTests(unittest.TestCase):
    def row(self,time,counts):
        return dict(pair=['arm','body'],check=dict(time=time,status='requires_partition_or_more_depth',
            counts=dict(zip(('front','back','ambiguous','unknown'),counts)),overlap_pixels=sum(counts)))

    def test_distinguishes_near_plane_mixed_depth_missing_and_unmeasured(self):
        rows=[self.row(0,[0,5,2,0]),self.row(1,[2,5,0,0]),self.row(2,[2,5,0,1]),
              dict(pair=['arm','body'],check=dict(time=3,status='unmeasured',reason_code='budget'))]
        group=summarize(rows)['pairs'][0]
        self.assertEqual(group['reasons'],dict(depth_margin_ambiguity=1,mixed_front_back_support=1,
                                             missing_depth_support=1,**{'unmeasured:budget':1}))
        self.assertEqual(sum(group['pixel_observations'].values()),22)

    def test_duplicate_or_nonconserving_counts_fail(self):
        row=self.row(0,[0,5,2,0])
        with self.assertRaisesRegex(ValueError,'duplicate'):summarize([row,row])
        row['check']['overlap_pixels']=8
        with self.assertRaisesRegex(ValueError,'inventory'):summarize([row])


if __name__=='__main__':unittest.main()
