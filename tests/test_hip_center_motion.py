from copy import deepcopy
import unittest
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
from autospine_workbench.targets.character43.hip_center_motion import apply
from autospine_workbench.targets.character43.affine_pose import matrices


class HipCenterTests(unittest.TestCase):
    def test_source_hip_origin_uses_declared_camera_basis(self):
        from test_mixamo_map import source,mapped
        from autospine_workbench.targets.character43.source_hip_centers import extract
        raw=source()
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder);(path/'map.json').write_text(json.dumps(mapped(raw)))
            centers,reference=extract(SimpleNamespace(path=path,source_kind='bvh',raw_bvh=raw))
        # Root and upper-leg offsets are both (1,2,3), basis is Z,Y,X.
        self.assertEqual(centers,[(6.,4.,2.)]*2)
        self.assertEqual(reference,10)

    def test_floor_root_rotation_does_not_move_stationary_source_hips(self):
        doc=dict(bones=[dict(name='root',x=0,y=0,rotation=0),
            dict(name='thigh_l',parent='root',x=-2,y=10,rotation=0),dict(name='thigh_r',parent='root',x=2,y=10,rotation=0)],
            animations={'a':{'bones':{'root':{'rotate':[dict(time=0,value=0),dict(time=1,value=90)],
                                            'translate':[dict(time=0,x=0,y=0),dict(time=1,x=2,y=3)]}}}})
        before=deepcopy(doc)
        result,report=apply(doc,'a',[(0,0,0),(0,0,0)],[0,1],10,20)
        self.assertEqual(doc,before)
        self.assertEqual(result['bones'],doc['bones'])
        self.assertEqual(result['animations']['a']['bones']['root']['rotate'],doc['animations']['a']['bones']['root']['rotate'])
        pose=matrices(result,'a',1)
        self.assertAlmostEqual((pose['thigh_l'][4]+pose['thigh_r'][4])/2,0)
        self.assertAlmostEqual((pose['thigh_l'][5]+pose['thigh_r'][5])/2,10)
        self.assertLess(report['maximum_after_error_px'],1e-10)
        moving,_=apply(doc,'a',[(0,0,0),(2,3,0)],[0,1],10,20)
        pose=matrices(moving,'a',1)
        self.assertAlmostEqual((pose['thigh_l'][4]+pose['thigh_r'][4])/2,4)
        self.assertAlmostEqual((pose['thigh_l'][5]+pose['thigh_r'][5])/2,4)

    def test_bad_samples_are_rejected(self):
        with self.assertRaisesRegex(ValueError,'samples_invalid'):
            apply({},'a',[(0,0,0)]*2,[1,0],10,20)
