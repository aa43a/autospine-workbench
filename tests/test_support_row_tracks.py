from copy import deepcopy
import unittest
from test_support_timeline import fixture
from autospine_workbench.targets.character43.support_row_tracks import apply
from autospine_workbench.targets.character43.affine_pose import matrices


class RowTracksTests(unittest.TestCase):
    def test_zero_correction_preserves_full_fk_and_source(self):
        doc,_=fixture(); names=('thigh_l','calf_l','thigh_r','calf_r')
        for n in names:doc['animations']['walk']['bones'][n]={'rotate':[dict(time=0,value=0)]}
        original=deepcopy(doc)
        rows=[dict(time=t,root_shift=[0,0],angles={n:0 for n in names}) for t in (0,.4,.8,1.2)]
        result=apply(doc,'walk',rows)
        self.assertEqual(doc,original)
        self.assertEqual(result['bones'],doc['bones'])
        for t in (0,.2,.7,1.2):
            for n in names:
                for a,b in zip(matrices(result,'walk',t)[n],matrices(doc,'walk',t)[n]):
                    self.assertAlmostEqual(a,b)

    def test_duplicate_time_rejected(self):
        with self.assertRaisesRegex(ValueError,'times_invalid'):
            apply({},'walk',[dict(time=0),dict(time=0)])
