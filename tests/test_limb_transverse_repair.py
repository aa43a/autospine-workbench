from copy import deepcopy
import math
import unittest

from autospine_workbench.targets.character43.affine_pose import matrices, sample
from autospine_workbench.targets.character43.limb_transverse_repair import build
from autospine_workbench.targets.spine43.continuous_pose import area


def fixture():
    bones = [dict(name='root', x=0, y=0, rotation=15),
             dict(name='thigh_l', parent='root', x=2, y=3, rotation=0),
             dict(name='calf_l', parent='thigh_l', x=20, y=0, rotation=45),
             dict(name='foot_l', parent='calf_l', x=15, y=0, rotation=0)]
    mesh = dict(type='mesh', uvs=[0, 0, 0, 1, 1, 0], triangles=[0, 1, 2],
                vertices=[1, 2, 0, 0, 1., 1, 2, 0, 10, 1., 1, 2, 10, 0, 1.])
    return dict(bones=bones, slots=[dict(name='leg'), dict(name='other')],
        skins=[dict(name='default', attachments={'leg': {'leg': mesh}, 'other': {'other': deepcopy(mesh)}})],
        animations={'motion': {'bones': {'thigh_l': {'scale': [dict(time=0, x=1., y=1.),
                                                               dict(time=1, x=.3, y=1.)]}}}})


class LimbTransverseRepairTests(unittest.TestCase):
    def test_constant_distal_gain_preserves_single_bone_corrected_area(self):
        doc=fixture()
        doc['animations']['motion']['attachments']={'default':{'leg':{'leg':{'deform':[
            dict(time=0,vertices=[0.]*6),dict(time=1,vertices=[1.,2.,-2.,4.,3.,-1.])]}}}}
        for gain in (0.,.25,.5,.75,1.):
            result,_=build(doc,'motion',['leg'],correction_frame='transverse',distal_gain=gain,required_times=[.371])
            for t in (0,.371,1):
                old=sample(doc,'motion',t)[0]['leg'];new=sample(result,'motion',t)[0]['leg']
                self.assertAlmostEqual(area(old,[0,1,2]),area(new,[0,1,2]),places=8)
        with self.assertRaisesRegex(ValueError,'distal_gain_invalid'):
            build(doc,'motion',['leg'],distal_gain=1.1)
        _,report=build(doc,'motion',['leg'],correction_frame='transverse',
                       anchor_terminal=True,distal_gain=.25)
        self.assertEqual(report['profile'],'limb-transverse-anchored-distal-gain-v1-experiment')
        self.assertEqual(report['distal_gain'],.25)
        self.assertFalse(report['production_authorized'])

    def test_terminal_anchor_preserves_existing_deformed_foot_world_shape(self):
        doc=fixture();mesh=doc['skins'][0]['attachments']['leg']['leg']
        for offset in (1,6,11):mesh['vertices'][offset]=3
        doc['animations']['motion']['attachments']={'default':{'leg':{'leg':{'deform':[
            dict(time=0,vertices=[0.]*6),dict(time=1,vertices=[1.,2.,-2.,4.,3.,-1.])]}}}}
        candidate,report=build(doc,'motion',['leg'],correction_frame='transverse',anchor_terminal=True)
        for time in (0,.371,.8,1):
            self.assertEqual(sample(candidate,'motion',time)[0],sample(doc,'motion',time)[0])
        self.assertEqual(report['terminal_anchors'],['foot_l'])
        self.assertEqual(candidate['bones'],doc['bones']);self.assertEqual(candidate['skins'],doc['skins'])

    def test_transports_nonuniform_prior_correction_with_same_bone_area(self):
        doc=fixture()
        doc['animations']['motion']['attachments']={'default':{'leg':{'leg':{'deform':[
            dict(time=0,vertices=[0.,0.,0.,0.,0.,0.]),
            dict(time=1,vertices=[1.,2.,-2.,4.,3.,-1.])]}}}}
        original=deepcopy(doc)
        result,report=build(doc,'motion',['leg'],correction_frame='transverse',tolerance_px=.001,required_times=[.371,.5])
        self.assertEqual(doc,original)
        self.assertEqual(result['bones'],doc['bones']);self.assertEqual(result['skins'],doc['skins'])
        for time in (0,.371,.5,1):
            before=sample(doc,'motion',time)[0];after=sample(result,'motion',time)[0]
            self.assertAlmostEqual(area(before['leg'],[0,1,2]),area(after['leg'],[0,1,2]),places=8)
            self.assertEqual(before['other'],after['other'])
        self.assertEqual(report['correction_frame'],'transverse')
        self.assertNotIn('existing_corrective_offsets_retained',report['invariants'])
        self.assertFalse(report['selected'])
        self.assertIn(.371,[k['time'] for k in result['animations']['motion']['attachments']['default']['leg']['leg']['deform']])
        for times in ([-1],[2],[float('nan')]):
            with self.assertRaisesRegex(ValueError,'required_times_invalid'):
                build(doc,'motion',['leg'],required_times=times)
        with self.assertRaisesRegex(ValueError,'correction_frame_invalid'):
            build(doc,'motion',['leg'],correction_frame='unknown')

    def test_removes_shear_without_changing_axes_area_width_or_other_slots(self):
        doc = fixture(); source = deepcopy(doc)
        result, report = build(doc, 'motion', ['leg'], tolerance_px=.001)
        self.assertEqual(doc, source)
        self.assertEqual(result['bones'], doc['bones'])
        self.assertEqual(result['skins'], doc['skins'])
        self.assertEqual(result['animations']['motion']['bones'], doc['animations']['motion']['bones'])
        for time in [0, .125, .371, .75, 1]:
            before = sample(doc, 'motion', time)[0]
            after = sample(result, 'motion', time)[0]
            self.assertEqual(before['other'], after['other'])
            # Points on the bone axis, including its attachment to the knee, stay fixed.
            self.assertEqual(before['leg'][0], after['leg'][0])
            self.assertEqual(before['leg'][2], after['leg'][2])
            ax = [after['leg'][2][i]-after['leg'][0][i] for i in (0, 1)]
            cross = [after['leg'][1][i]-after['leg'][0][i] for i in (0, 1)]
            self.assertLess(abs(sum(x*y for x, y in zip(ax, cross)))/math.hypot(*ax), .001)
            self.assertAlmostEqual(area(before['leg'], [0, 1, 2]), area(after['leg'], [0, 1, 2]), places=9)
        self.assertFalse(report['selected'])
        self.assertGreater(report['maximum_displacement_px']['leg'], 5)
        self.assertLessEqual(report['maximum_interpolation_error_px'], .001)

    def test_keeps_prior_correction_as_world_displacement(self):
        doc = fixture()
        doc['animations']['motion']['attachments'] = {'default': {'leg': {'leg': {'deform': [
            dict(time=0, vertices=[2., 3.]*3), dict(time=1, vertices=[-1., 4.]*3)]}}}}
        plain = fixture()
        corrected, _ = build(doc, 'motion', ['leg'])
        reference, _ = build(plain, 'motion', ['leg'])
        for time in (0, .5, 1):
            a = sample(corrected, 'motion', time)[0]['leg']; b = sample(reference, 'motion', time)[0]['leg']
            old = sample(doc, 'motion', time)[0]['leg']; base = sample(plain, 'motion', time)[0]['leg']
            for pa, pb, po, pp in zip(a, b, old, base):
                for i in (0, 1):
                    self.assertAlmostEqual(pa[i]-pb[i], po[i]-pp[i], places=9)

    def test_preserves_setup_shear_and_real_projection_compression(self):
        doc = fixture(); doc['bones'][1]['scaleX'] = .5
        result, _ = build(doc, 'motion', ['leg'])
        self.assertEqual(sample(doc, 'motion', 0)[0]['leg'], sample(result, 'motion', 0)[0]['leg'])
        before = sample(doc, 'motion', 1)[0]['leg']; after = sample(result, 'motion', 1)[0]['leg']
        setup = deepcopy(doc); setup['animations']['motion'] = {'bones': {}}
        setup_area = area(sample(setup, 'motion', 0)[0]['leg'], [0, 1, 2])
        self.assertAlmostEqual(area(after, [0, 1, 2])/setup_area, .3)
        self.assertAlmostEqual(area(before, [0, 1, 2]), area(after, [0, 1, 2]))

    def test_mixed_weights_and_zero_weight_entries_keep_ownership(self):
        doc = fixture(); mesh = doc['skins'][0]['attachments']['leg']['leg']
        mesh['vertices'] = [v for x, y in [(0, 0), (0, 10), (10, 0)]
                            for v in [3, 1, x, y, .25, 2, x, y, .75, 0, x, y, 0.]]
        result, _ = build(doc, 'motion', ['leg'])
        self.assertEqual(result['skins'], doc['skins'])
        self.assertTrue(all(math.isfinite(v) for p in sample(result, 'motion', .5)[0]['leg'] for v in p))

    def test_rejects_unsupported_inputs_and_unresolved_key_budget(self):
        for mutate, error in [
            (lambda d: d['skins'][0]['attachments']['leg']['leg']['vertices'].__setitem__(1, 0), 'single_limb'),
            (lambda d: d['skins'][0]['attachments']['leg']['leg']['vertices'].__setitem__(4, .5), 'weights_invalid'),
            (lambda d: d['animations']['motion']['bones']['thigh_l']['scale'][0].update(curve='stepped'), 'linear_required'),
            (lambda d: d['animations']['motion'].update(slots={'leg': {'attachment': []}}), 'timeline_unsupported'),
        ]:
            doc = fixture(); mutate(doc)
            with self.assertRaisesRegex(ValueError, error):
                build(doc, 'motion', ['leg'])
        with self.assertRaisesRegex(ValueError, 'interpolation_unresolved'):
            build(fixture(), 'motion', ['leg'], tolerance_px=1e-9, maximum_keys=3)


if __name__ == '__main__':
    unittest.main()
