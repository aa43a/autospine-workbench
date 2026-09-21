import unittest
from tests.fixtures.kimodo_npz_archive import build_npz,motion_member_bytes
from tests.kimodo_npz_helpers import source_document,map_document
from autospine_workbench.targets.character43.kimodo_depth_sampler import KimodoDepthSampler
from autospine_workbench.targets.character43.hand_depth_observation import observe
from autospine_workbench.kimodo_soma77 import SOMA77_INDEX_BY_NAME
from autospine_workbench.kimodo_npz_reader import decode_kimodo_npz
from autospine_workbench.kimodo_npz_consistency import validate_kimodo_consistency


class KimodoDepthTests(unittest.TestCase):
    def setUp(self):
        self.raw=build_npz(motion_member_bytes())
        self.source=source_document(self.raw);self.mapping=map_document()

    def sampler(self,**kwargs):return KimodoDepthSampler(self.raw,self.source,self.mapping,**kwargs)

    def test_declared_basis_yaw_and_normalization_match_verified_positions(self):
        pose=validate_kimodo_consistency(decode_kimodo_npz(self.raw,self.source),self.source).positions
        for yaw in (0,90):
            s=self.sampler(yaw_degrees=yaw)
            axis=self.mapping['basis']['depth' if yaw==0 else 'screen_x']
            component=lambda p:(1 if axis[0]=='+' else -1)*p['XYZ'.index(axis[1])]
            chest=SOMA77_INDEX_BY_NAME[s.roles['humanoid.spine.upper']['joint_name']]
            length=self.mapping['root']['reference_length_meters']
            for i,tick in enumerate(s.ticks):
                expected=(component(pose[i][SOMA77_INDEX_BY_NAME['LeftHand']])-component(pose[i][chest]))/length
                self.assertAlmostEqual(s.joint_depths(tick)['LeftHand'],expected)
                self.assertEqual(s(tick)['forearm_l'][1],s.joint_depths(tick)['LeftHand'])
                self.assertEqual(set(s.leg_segments(tick)),{'thigh_l','calf_l','thigh_r','calf_r'})

    def test_midpoints_require_explicit_model_and_out_of_range_is_not_clamped(self):
        s=self.sampler();tick=(s.ticks[0]+s.ticks[1])/2
        with self.assertRaisesRegex(ValueError,'unobserved'):s.joint_depths(tick)
        model=self.sampler(interpolation='linear_observed_positions')
        a,b=[model.joint_depths(t) for t in model.ticks[:2]]
        self.assertAlmostEqual(model.joint_depths(tick)['LeftHand'],(a['LeftHand']+b['LeftHand'])/2)
        for t in (-1,s.ticks[-1]+1,float('nan')):
            with self.assertRaisesRegex(ValueError,'time_invalid'):model.joint_depths(t)

    def test_full_hand_uses_actual_declared_end_joint_and_records_model(self):
        s=self.sampler();r=observe(s,s.ticks[0],full_hand=True)
        self.assertEqual(r['joints']['hand_l'][-1],'LeftHandMiddleEnd')
        self.assertEqual(r['segments']['hand_l'][1],s.joint_depths(s.ticks[0])['LeftHandMiddleEnd'])
        self.assertEqual(r['interpolation'],'source_samples_only')
        self.assertFalse(r['selected'])
        self.assertIn('raw_npz_sha256',r['identity'])

    def test_source_bytes_and_invalid_models_fail(self):
        with self.assertRaises(ValueError):KimodoDepthSampler(self.raw+b'x',self.source,self.mapping)
        with self.assertRaisesRegex(ValueError,'interpolation_unsupported'):self.sampler(interpolation='automatic')


if __name__=='__main__':unittest.main()
