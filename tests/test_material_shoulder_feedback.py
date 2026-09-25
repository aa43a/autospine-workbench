import unittest
import json
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from m4_material_shoulder_feedback import select,load


class ShoulderFeedbackTests(unittest.TestCase):
    def report(self):
        rows=[dict(slot='a',time=t,geometry=dict(min_area_ratio=area,max_area_ratio=1,max_edge_stretch=1))
              for t,area in ((.2,.49),(.3,.47),(.8,.48))]
        return dict(source_candidate='source',motion_source_candidate='motion',material_owners={'a':'b'},
                    source_times=[0,.5,1],solver_failures=[],
                    validation=dict(max_region_ratio=1.005,failures=rows,
                                    contact_frame='verified_material_affine',material_owners={'a':'b'}))

    def test_worst_geometry_per_interval_and_stricter_contact_only(self):
        extra,margin=select(self.report(),'source','motion',{'a':'b'},[0,.5,1])
        self.assertEqual(extra,[.3,.8]);self.assertAlmostEqual(margin,.01001)

    def test_wrong_identity_and_excessive_margin_rejected(self):
        with self.assertRaises(ValueError):select(self.report(),'other','motion',{'a':'b'},[0,.5,1])
        report=self.report();report['validation']['max_region_ratio']=1.1
        with self.assertRaises(ValueError):select(report,'source','motion',{'a':'b'},[0,.5,1])

    def test_old_bone_frame_is_not_reused_as_material_feedback(self):
        report=self.report();report['validation']['contact_frame']='chest_bone'
        with self.assertRaises(ValueError):select(report,'source','motion',{'a':'b'},[0,.5,1])

    def test_full_previous_grid_preserved_and_skeleton_verified(self):
        report=self.report();report['skeleton_sha256']=sha256(b'{}').hexdigest();report['validation']['frames']=9
        with TemporaryDirectory() as root:
            path=Path(root);(path/'skeleton.json').write_bytes(b'{}')
            (path/'report.json').write_text(json.dumps(report),encoding='utf-8')
            result=load(path,'source','motion',{'a':'b'},[0,.5,1],[0,.25,.5,.75,1])
            self.assertEqual(result['previous_validation_times'],[i/8 for i in range(9)])
            (path/'skeleton.json').write_bytes(b'{"changed":true}')
            with self.assertRaises(ValueError):load(path,'source','motion',{'a':'b'},[0,.5,1],[0,.25,.5,.75,1])


if __name__=='__main__':unittest.main()
