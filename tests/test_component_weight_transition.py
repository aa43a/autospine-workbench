from copy import deepcopy
import unittest
from tests.test_component_mesh import fixture
from autospine_workbench.asset.planning.component_mesh import build as build_mesh
from autospine_workbench.asset.planning.component_ownership import template
from autospine_workbench.asset.planning.component_weight_transition import build, measure, reweight, _score, _passes


def limb_fixture():
    entries, skeleton, _, addresses, plan = fixture()
    entries[0][0]['name'] = 'handwear-l'
    names = ['upperarm_l', 'forearm_l', 'hand_l']
    skeleton['bones'] = [dict(id=name, parent_id=names[i-1] if i else 'chest',
                              head_xy=[106,202+6*i], tail_xy=[106,208+6*i], world_rotation_degrees=90.)
                         for i,name in enumerate(names)]
    draft = template('fixture',entries,addresses,plan,names)
    draft['records'][0].update(status='assigned',semantic='body.arm',side='left',bone_ids=names)
    return entries,skeleton,draft,addresses,plan


class ComponentWeightTransitionTests(unittest.TestCase):
    def test_replay_sources_and_no_metric_regression(self):
        args = limb_fixture(); baseline = build_mesh(*args); before = deepcopy(baseline)
        experiment = build(baseline,args[1],args[0])
        self.assertEqual(baseline,before)
        self.assertEqual(experiment,build(baseline,args[1],args[0]))
        c = experiment['comparisons'][0]
        self.assertTrue(all(a<=b for a,b in zip(_score(c['selected_qa']),_score(c['baseline_qa']))))
        for original, selected in zip(c['baseline_qa']['probes'],c['selected_qa']['probes']):
            if _passes(original): self.assertTrue(_passes(selected))
        self.assertIsNone(experiment['records'][1]['mesh'])
        self.assertFalse(experiment['production_authorized'])
        broken=deepcopy(baseline); broken['records'][0]['isolated_image_sha256']='f'*64
        with self.assertRaises(ValueError): build(broken,args[1],args[0])
        args[1]['bones'][0]['head_xy'][0]+=1
        with self.assertRaises(ValueError): build(baseline,args[1],args[0])

    def test_only_weights_change_and_widths_bounded(self):
        args=limb_fixture(); mesh=build_mesh(*args)['records'][0]['mesh']
        layer,_,candidate,_=args[0][0]; bones=args[1]['bones']
        evidence=measure(candidate['components'][0],layer['bbox'],bones)
        revised,widths=reweight(mesh,bones,evidence,4)
        for key in ('vertices_xy','uvs','triangles','raster_qa'):
            self.assertEqual(revised[key],mesh[key])
        for row, original in zip(revised['weights'],mesh['weights']):
            self.assertAlmostEqual(sum(w['weight'] for w in row),1)
            self.assertEqual([w['local_xy'] for w in row],[w['local_xy'] for w in original])
        for width,e in zip(widths,evidence):
            self.assertGreaterEqual(width,e['original_halfwidth'])
            self.assertLessEqual(width,e['cap'])
        with self.assertRaises(ValueError): reweight(mesh,bones,evidence,99)

    def test_rigid_feet_remain_exact(self):
        args=fixture(); baseline=build_mesh(*args)
        result=build(baseline,args[1],args[0])
        self.assertEqual(result['records'],baseline['records'])
        self.assertEqual(result['comparisons'],[])
