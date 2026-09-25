import unittest
from m4_corrective_geometry_check import checked_times


class CorrectiveGridTests(unittest.TestCase):
    def doc(self):
        return {'animations':{'a':{'bones':{'root':{'rotate':[{'time':0},{'time':1}]}}}}}

    def test_declared_failed_sample_is_not_dropped(self):
        report={'validation_times':[0,.123,1],'validation':{'frames':3}}
        self.assertEqual(checked_times(self.doc(),'a',[0,1],report),[0,.123,.5,1])

    def test_dense_evidence_cannot_be_silently_downsampled(self):
        times=[i/5000 for i in range(5001)]
        with self.assertRaisesRegex(ValueError,'required_samples_exceed_capture_budget'):
            checked_times(self.doc(),'a',[0,1],{'validation_times':times,'validation':{'frames':len(times)}})

    def test_invalid_grid_is_rejected(self):
        for times in ([0,1.1],[0,float('nan')],[0,.5,.5]):
            with self.assertRaisesRegex(ValueError,'validation_grid_invalid'):
                checked_times(self.doc(),'a',[0,1],{'validation_times':times,'validation':{'frames':len(times)}})


if __name__=='__main__':unittest.main()
