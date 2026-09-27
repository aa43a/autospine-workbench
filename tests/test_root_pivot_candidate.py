from copy import deepcopy
import unittest
from autospine_workbench.targets.character43.root_pivot_candidate import build
from autospine_workbench.targets.character43.affine_pose import matrices


class RootPivotTests(unittest.TestCase):
    def test_rotation_preserved_with_pelvis_center_and_translation(self):
        doc = dict(bones=[dict(name='root', x=0,y=0,rotation=0),
                          dict(name='pelvis',parent='root',x=0,y=10,rotation=0)],
                   animations={'move':dict(bones={'root':dict(
                       rotate=[dict(time=0,value=0),dict(time=1,value=90)],
                       translate=[dict(time=0,x=0,y=0),dict(time=1,x=3,y=4)])})})
        original = deepcopy(doc)
        changed, report = build(doc, 'move', [i/100 for i in range(101)])
        self.assertEqual(doc, original)
        self.assertEqual(changed['animations']['move']['bones']['root']['rotate'], doc['animations']['move']['bones']['root']['rotate'])
        pose = matrices(changed,'move',1)['pelvis']
        self.assertAlmostEqual(pose[4],3)
        self.assertAlmostEqual(pose[5],14)
        self.assertAlmostEqual(pose[2],1)
        self.assertLess(report['worst']['error_px'], .001)
        self.assertFalse(report['selected'])
