from copy import deepcopy
import math
import unittest

from test_joint_face import fixture
from autospine_workbench.targets.character43.joint_loop_qa import inspect, neutral_document
from autospine_workbench.targets.character43.joint_face import apply, defaults
from autospine_workbench.targets.character43.affine_pose import sample


def documents():
    _, source = fixture()
    source['animations']['body']['bones'] = {}
    result = deepcopy(source)
    result['bones'].append(dict(name='m5-hair-test', parent='head', x=0., y=0., rotation=0., length=10.))
    for slot in result['slots']:
        slot['bone'] = 'm5-hair-test'
        vertices = result['skins'][0]['attachments'][slot['name']][slot['name']]['vertices']
        for i in range(1, len(vertices), 5):
            vertices[i] = 2
    return source, result


class JointLoopQATests(unittest.TestCase):
    def test_noncyclic_wind_is_not_approved_when_geometry_is_static(self):
        source, result = documents()
        field = dict(enabled=True, loop_compatible=False)
        report = inspect(source, result, 'body', 1., True, secondary_report={'wind': field})
        self.assertTrue(report['overall']['passed'])
        self.assertFalse(report['added_effects']['wind']['passed'])
        self.assertEqual(report['status'], 'needs_changes')
        field['loop_compatible'] = True
        self.assertEqual(inspect(source, result, 'body', 1., True,
            secondary_report={'wind': field})['status'], 'passed')

    def test_looping_helpers_pass_position_velocity_and_counterfactual(self):
        source, result = documents()
        result['animations']['body']['bones']['m5-hair-test'] = {'translate': [
            dict(time=i/120, x=2*math.sin(2*math.pi*i/120), y=0) for i in range(121)]}
        before = deepcopy(result)
        report = inspect(source, result, 'body', 1., True)
        self.assertEqual(report['status'], 'passed')
        self.assertTrue(report['added_effects']['local_helpers']['passed'])
        self.assertLess(report['added_effects']['world_increment']['max_endpoint_error_px'], 1e-10)
        self.assertEqual(result, before)

    def test_smaller_total_error_never_approves_new_effect_seam(self):
        source, result = documents()
        move = {'translate': [dict(time=0, x=0, y=0), dict(time=1, x=10, y=0)]}
        source['animations']['body']['bones']['root'] = deepcopy(move)
        result['animations']['body']['bones']['root'] = deepcopy(move)
        result['animations']['body']['bones']['m5-hair-test'] = {'translate': [
            dict(time=0, x=0, y=0), dict(time=1, x=-1, y=0)]}
        report = inspect(source, result, 'body', 1., True)
        self.assertLess(report['overall']['max_endpoint_error_px'], report['source_body']['max_endpoint_error_px'])
        self.assertFalse(report['added_effects']['passed'])
        self.assertFalse(report['added_effects']['local_helpers']['passed'])
        self.assertEqual(report['status'], 'needs_changes')
        self.assertIn('original_body_is_not_loop_ready_joint_effects_do_not_remove_this_limit', report['limitations'])

    def test_matching_pose_but_discontinuous_velocity_is_rejected(self):
        source, result = documents()
        result['animations']['body']['bones']['m5-hair-test'] = {'translate': [
            dict(time=0, x=0, y=0), dict(time=.5, x=20, y=0), dict(time=1, x=0, y=0)]}
        report = inspect(source, result, 'body', 1., True)
        row = report['added_effects']['local_helpers']['records'][0]
        self.assertEqual(row['endpoint_error'], 0)
        self.assertAlmostEqual(row['velocity_error'], 80.)
        self.assertEqual(report['status'], 'needs_changes')

    def test_invisible_alpha_seam_cannot_hide_behind_unchanged_geometry(self):
        source, result = documents()
        result['animations']['body']['slots'] = {'layer-000': {'alpha': [
            dict(time=0, value=1), dict(time=1, value=0)]}}
        report = inspect(source, result, 'body', 1., True)
        self.assertTrue(report['overall']['passed'])
        self.assertFalse(report['added_effects']['face_alpha']['passed'])
        self.assertEqual(report['status'], 'needs_changes')

    def test_original_body_nonloop_remains_limit_even_when_new_channels_are_neutral(self):
        source, result = documents()
        track = {'translate': [dict(time=0, x=0, y=0), dict(time=1, x=3, y=0)]}
        source['animations']['body']['bones']['root'] = deepcopy(track)
        result['animations']['body']['bones']['root'] = deepcopy(track)
        report = inspect(source, result, 'body', 1., True)
        self.assertTrue(report['added_effects']['passed'])
        self.assertFalse(report['source_body']['loop_ready'])
        self.assertEqual(report['status'], 'needs_changes')
        self.assertEqual(inspect(source, result, 'body', 1., False)['status'], 'not_requested')

    def test_face_neutralization_keeps_bind_and_old_deform_basis(self):
        files, source = fixture()
        config = defaults(); config['enabled'] = True; config['gaze']['x'] = .7
        result, _, face = apply(files, source, 'body', config, [0, 1, 2])
        neutral, added, alpha, _ = neutral_document(source, result, 'body')
        self.assertEqual(neutral['bones'], result['bones']); self.assertEqual(neutral['skins'], result['skins'])
        self.assertGreater(len(added), 0); self.assertGreater(len(alpha), 0)
        for time in [0, .37, 1, 2]:
            before = sample(source, 'body', time)[0]; after = sample(neutral, 'body', time)[0]
            self.assertLess(max(math.dist(p, q) for s in before for p, q in zip(before[s], after[s])), 1e-10)

    def test_removed_aux_probe_is_explicit_and_not_restored(self):
        source, result = documents()
        bone = dict(name='layer-skirt_1_upper', parent='head', x=0., y=0., rotation=0., length=10.)
        source['bones'].append(deepcopy(bone)); result['bones'].append(deepcopy(bone))
        source['animations']['body']['bones'][bone['name']] = {'rotate': [
            dict(time=i/16, value=2*math.sin(2*math.pi*i/16)) for i in range(17)]}
        report = inspect(source, result, 'body', 1., True, secondary_report={'probe_tracks_replaced': [bone['name']]})
        self.assertEqual(report['probe_tracks_replaced'], [bone['name']])
        self.assertIn(bone['name'], report['changed_existing_aux_tracks'])
        neutral, _, _, _ = neutral_document(source, result, 'body')
        self.assertNotIn(bone['name'], neutral['animations']['body']['bones'])

    def test_draw_order_seam_is_not_lost_in_static_vertex_check(self):
        source, result = documents()
        result['animations']['body']['drawOrder'] = [dict(time=.5, offsets=[dict(slot='layer-000', offset=1)])]
        report = inspect(source, result, 'body', 1., True)
        self.assertTrue(report['overall']['passed'])
        self.assertFalse(report['overall']['visibility']['draw_order_equal'])
        self.assertEqual(report['status'], 'needs_changes')


if __name__ == '__main__':
    unittest.main()
