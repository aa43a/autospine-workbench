from copy import deepcopy
import unittest
from unittest.mock import patch
from types import SimpleNamespace

from autospine_workbench.targets.character43.motion_depth import build
from autospine_workbench.targets.character43.motion_depth import _source
from autospine_workbench.targets.character43.oblique_motion import project


def fixture():
    bones = [dict(name=n, **({'parent': p} if p else {})) for n, p in
             [('root', None), ('chest', 'root'), ('upperarm_l', 'chest'), ('skirt', 'chest')]]
    slots = [dict(name=n, bone=b, attachment=n) for n, b in [('arm', 'upperarm_l'), ('body', 'chest'), ('skirt', 'skirt')]]
    document = dict(bones=bones, slots=slots, skins=[dict(attachments={s['name']: {s['name']: {'type': 'region'}} for s in slots})])
    mapping = dict(basis=dict(depth='+Z'), bones=[
        dict(role='humanoid.spine.upper', joint_name='torso'),
        dict(role='humanoid.arm.upper.left', joint_name='shoulder'),
        dict(role='humanoid.arm.lower.left', joint_name='elbow', aim=dict(joint_name='wrist'))])
    return document, mapping


class MotionDepthTests(unittest.TestCase):
    def test_depth_uses_same_yaw_basis_as_limb_projection(self):
        points=[(3.,2.,-1.),(-2.,4.,5.)]
        projected=SimpleNamespace(frames=[SimpleNamespace(tick=i*10000,
            joints=[('wrist',SimpleNamespace(screen_xy=p[:2],depth=p[2]))]) for i,p in enumerate(points)])
        mapping={'root':{'reference_length_source_units':2}}
        with patch('autospine_workbench.targets.character43.motion_depth.project_bvh_frames',return_value=projected):
            for yaw in (-45,0,45,90):
                frames,length,digest=_source(SimpleNamespace(source_sha256='a'*64),mapping,None,yaw)
                self.assertEqual(length,2)
                self.assertEqual(digest,'a'*64)
                for i,((tick,joints),point) in enumerate(zip(frames,points)):
                    self.assertEqual(tick,i*10000)
                    self.assertAlmostEqual(joints['wrist'],project(point,yaw)[2])

    def test_build_preserves_explicit_view_in_evidence(self):
        doc,mapping=fixture()
        frames=[(0,dict(torso=0,shoulder=1,elbow=1,wrist=1))]
        with patch('autospine_workbench.targets.character43.motion_depth._source',return_value=(frames,1,'a'*64)) as source:
            report=build(doc,None,mapping,yaw_degrees=45)
        source.assert_called_once_with(None,mapping,None,45)
        self.assertEqual(report['yaw_degrees'],45)
        self.assertEqual(report['depth_axis'],'yaw_rotated_declared_basis')
        self.assertFalse(report['selected'])

    def run_depth(self, values, bounds=None):
        doc, mapping = fixture(); original = deepcopy(doc)
        frames = [(i*10000, dict(torso=0, shoulder=v[0], elbow=v[1], wrist=v[2])) for i, v in enumerate(values)]
        with patch('autospine_workbench.targets.character43.motion_depth._source', return_value=(frames, 1, 'a'*64)):
            report = build(doc, None, mapping, clip_bounds=bounds)
        self.assertEqual(doc, original)
        return report

    def test_hysteresis_and_source_clip_identity(self):
        report = self.run_depth([(0.1, .1, .1)]*5, (10000, 40000))
        self.assertEqual(report['switch_candidates'], 1)
        event = report['pairs'][0]['events'][0]
        self.assertEqual(event['tick'], 20000)
        self.assertEqual(event['source_frame_index'], 3)
        self.assertFalse(report['selected'])
        self.assertEqual(report['groups']['other'], ['skirt'])

    def test_cross_plane_ambiguity_does_not_trigger_reordering(self):
        report = self.run_depth([(-.1, .1, .2)]*5)
        self.assertEqual(report['switch_candidates'], 0)
        self.assertEqual(report['ambiguous_pair_samples'], 5)
        self.assertEqual(report['status'], 'depth_candidates_need_review')

    def test_one_frame_depth_noise_is_ignored(self):
        report = self.run_depth([(.1, .1, .1), (-.1, -.1, -.1)]*4)
        self.assertEqual(report['switch_candidates'], 0)


if __name__ == '__main__':
    unittest.main()
