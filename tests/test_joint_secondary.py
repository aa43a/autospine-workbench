"""Secondary layers preserve body/deform authority and pinned material roots."""
from copy import deepcopy
from io import BytesIO
import json
import math
import unittest

from autospine_workbench.targets.character43.affine_pose import sample
from autospine_workbench.targets.character43.joint_secondary import apply, defaults, inventory, normalize
from autospine_workbench.targets.character43.joint_secondary_mesh import cloth, hair
from autospine_workbench.targets.character43.joint_secondary_guard import protect
from autospine_workbench.targets.character43.joint_secondary_clearance import capsules, penetration, compare as clearance
from autospine_workbench.targets.character43.joint_secondary import _points
from autospine_workbench.targets.character43.affine_pose import matrices
from autospine_workbench.targets.character43.joint_spring import bake, grid, solve
from test_character_skirt_candidate import fixture
from autospine_workbench.targets.character43.skirt_candidate import generate


def scene():
    from PIL import Image
    files, _ = generate(fixture(), 'a'*64, ['skirt'], step=20)
    document = json.loads(files['skeleton.json']); bone_index = len(document['bones'])
    document['bones'].append(dict(name='head', parent='root', x=0., y=90., rotation=0.))
    document['slots'].append(dict(name='hair', bone='head', attachment='hair'))
    flat = []
    for x, y in [(-40, 0), (40, 0), (40, -100), (-40, -100)]: flat.extend([1, bone_index, x, y, 1.])
    document['skins'][0]['attachments']['hair'] = {'hair': dict(type='mesh', path='hair', width=80, height=100,
        vertices=flat, uvs=[0, 0, 1, 0, 1, 1, 0, 1], triangles=[0, 1, 2, 0, 2, 3])}
    stream = BytesIO(); Image.new('RGBA', (80, 100), (120, 70, 10, 255)).save(stream, format='PNG')
    files['images/hair.png'] = stream.getvalue()
    manifest = json.loads(files['character-manifest.json'])
    manifest['layers'].append(dict(layer_id='hair', name='back hair', state='rigid_reviewed', regions=[dict(region_id='hair')]))
    files['character-manifest.json'] = json.dumps(manifest).encode()
    document['animations']['idle']['bones']['head'] = {'rotate': [
        dict(time=i/30, value=5*math.sin(math.pi*i/30)) for i in range(61)]}
    return files, document


class JointSecondaryTests(unittest.TestCase):
    def test_disabled_exact_and_camera_does_not_invent_inertia(self):
        files, document = scene(); before = deepcopy(document)
        out, report = apply(files, document, 'idle', {}, [0., 1., 2.])
        self.assertEqual(out, before); self.assertEqual(report['status'], 'disabled')
        out, report = apply(files, document, 'idle', {'hair': {'enabled': True}}, [0., 1., 2.],
                            camera_keys=[dict(time=0., yaw=0), dict(time=2., yaw=360)])
        self.assertEqual(out, before); self.assertEqual(report['status'], 'blocked')
        self.assertIn('unprojected', report['skipped'][0]['reason']); self.assertEqual(document, before)

    def test_hair_mesh_pins_roots_and_preserves_uv_world_setup(self):
        files, document = scene(); before = deepcopy(document)
        record = hair(files, document, 'hair', .35)
        actual = sample(dict(document, animations={'setup': {}}), 'setup', 0)[0]['hair']
        self.assertLess(max(math.dist(p, q) for p, q in zip(actual, record['expected_setup'])), 1e-8)
        self.assertGreater(len(actual), 4); self.assertGreater(len(record['pinned_vertices']), 0)
        self.assertEqual(document['slots'], before['slots'])
        self.assertEqual(document['animations'], before['animations'])

    def test_cloth_cloned_deform_retains_every_old_pose_at_zero_response(self):
        _, document = scene(); helper_names = [b['name'] for b in document['bones'] if '-skirt_' in b['name']]
        mesh = document['skins'][0]['attachments']['skirt']['skirt']; data = mesh['vertices']; i = count = 0
        while i < len(data): n = data[i]; count += n; i += 1+4*n
        keys = [dict(time=0, vertices=[0.]*(count*2)), dict(time=1, vertices=[.2*math.sin(i) for i in range(count*2)]),
                dict(time=2, vertices=[0.]*(count*2))]
        document['animations']['idle']['attachments'] = {'default': {'skirt': {'skirt': {'deform': keys}}}}
        before = deepcopy(document); report = cloth(document, 'skirt', helper_names)
        self.assertGreater(report['movable_vertices'], 0); self.assertGreater(len(report['pinned_vertices']), 0)
        for time in (0, .37, .79, 1.61, 2):
            a = sample(before, 'idle', time)[0]['skirt']; b = sample(document, 'idle', time)[0]['skirt']
            self.assertLess(max(math.dist(p, q) for p, q in zip(a, b)), 1e-8)

    def test_combination_is_deterministic_and_keeps_body_and_unrelated_tracks(self):
        files, document = scene(); original = deepcopy(document)
        config = {'hair': {'enabled': True}, 'cloth': {'enabled': True}, 'loop': True}
        result, report = apply(files, document, 'idle', config, [i/30 for i in range(61)])
        again, evidence = apply(files, document, 'idle', config, [i/30 for i in range(61)])
        self.assertEqual(result, again); self.assertEqual(report, evidence); self.assertEqual(document, original)
        self.assertEqual(report['status'], 'applied'); self.assertEqual(report['root_error_px'], 0.)
        self.assertEqual(result['animations']['idle']['bones']['head'], document['animations']['idle']['bones']['head'])
        self.assertEqual(result['animations']['idle']['bones']['root'], document['animations']['idle']['bones']['root'])
        self.assertEqual(len(report['probe_tracks_replaced']), 6)
        self.assertGreater(max(r['peak_response_deg'] for r in report['regions']), .1)
        self.assertEqual(report['solver_sample_count'], 241)
        self.assertEqual(report['key_sample_count'], 121)
        self.assertLessEqual(max(s['key_approximation_error_deg'] for r in report['regions'] for s in r['springs']), .05)
        self.assertLessEqual(max(s['key_peak_loss_deg'] for r in report['regions'] for s in r['springs']), .05)
        forward = {t: sample(result, 'idle', t)[0] for t in (.12, .56, 1.73)}
        reverse = {t: sample(result, 'idle', t)[0] for t in (1.73, .56, .12)}
        self.assertEqual(forward, reverse)

    def test_invalid_and_unknown_config_fails_without_mutation(self):
        files, document = scene()
        for config in ({'hair': {'damping': 0}}, {'cloth': {'max_angle': float('nan')}}, {'hair': {'enabled': 1}}, {'wind': 2}):
            with self.assertRaises(ValueError): normalize(config, 2.)
        with self.assertRaisesRegex(ValueError, 'unknown_slot'):
            apply(files, document, 'idle', {'hair': {'enabled': True, 'slots': ['not-hair']}}, [0., 2.])
        catalog = inventory(files, document)
        self.assertEqual([r['slot'] for r in catalog['hair']], ['hair'])
        self.assertEqual([r['slot'] for r in catalog['cloth']], ['skirt'])

    def test_slot_override_inherits_group_and_can_be_removed(self):
        files, document = scene()
        config = {'hair': {'enabled': True, 'strength': 1.5,
            'overrides': {'hair': {'strength': .5, 'stiffness': 16., 'root_fraction': .55}}}}
        normalized = normalize(config, 2.)
        self.assertEqual(normalized['hair']['strength'], 1.5)
        self.assertEqual(normalized['hair']['overrides']['hair'], {'strength': .5, 'stiffness': 16., 'root_fraction': .55})
        _, report = apply(files, document, 'idle', config, [0., 1., 2.])
        region = report['regions'][0]
        self.assertEqual(region['root_fraction'], .55)
        self.assertEqual(region['requested_config']['strength'], .5)
        self.assertEqual(region['requested_config']['damping'], .85)
        self.assertEqual(region['effective_config']['strength'], .5*region['effective_gain'])
        self.assertEqual(normalize({'hair': {'overrides': {}}}, 2.), normalize({}, 2.))
        for bad in ({'cloth': {'overrides': {'skirt': {'root_fraction': .5}}}},
                    {'hair': {'overrides': {'hair': {'enabled': False}}}},
                    {'hair': {'overrides': {'hair': {'strength': float('inf')}}}}):
            with self.assertRaises(ValueError): normalize(bad, 2.)
        with self.assertRaisesRegex(ValueError, 'unknown_override_slot'):
            apply(files, document, 'idle', {'hair': {'enabled': True, 'overrides': {'missing': {'strength': .5}}}}, [0., 2.])


class JointSpringTests(unittest.TestCase):
    def test_face_keys_and_fixed_solver_share_exact_midpoints_at_exported_durations(self):
        for duration in (2., 3.966667, 4.033333, 9.933333, 19.966667, 1.012345):
            ticks = grid(duration)
            self.assertEqual(ticks[::2], grid(duration, 60))
            self.assertEqual(ticks[-1], duration)
            dt = ticks[1]-ticks[0]
            self.assertLessEqual(dt, 1/120+1e-8)
            self.assertLess(max(abs((b-a)-dt) for a,b in zip(ticks, ticks[1:])), 1e-8)
        self.assertEqual(len(grid(19.966667)), 2397)

    def test_key_bake_keeps_sharp_response_corner_and_deterministic_error_bound(self):
        ticks = [i/120 for i in range(7)]
        values = [0., 1., 0., .02, 0., -.5, 0.]
        times, samples, report = bake(ticks, values)
        self.assertEqual(times, [ticks[i] for i in (0,1,2,4,5,6)])
        self.assertEqual(samples, [values[i] for i in (0,1,2,4,5,6)])
        self.assertEqual(report['adaptive_key_count'], 2)
        self.assertEqual(report['key_peak_loss_deg'], 0.)
        self.assertLessEqual(report['key_approximation_error_deg'], .05)
        self.assertEqual(bake(ticks, values), (times, samples, report))

    def test_stationary_has_no_fake_sway_and_loop_is_explicit(self):
        ticks = grid(2.); poses = [(3., 7., -90.) for _ in ticks]
        values, report = solve(ticks, poses, loop=True)
        self.assertEqual(max(map(abs, values)), 0.); self.assertEqual(report['loop_status'], 'converged')

    def test_root_motion_response_is_bounded_repeatable_and_loop_converges(self):
        ticks = grid(2.); poses = [(8*math.sin(math.pi*t), 0., 5*math.sin(math.pi*t)) for t in ticks]
        values, report = solve(ticks, poses, max_angle=1., loop=True)
        self.assertEqual((values, report), solve(ticks, poses, max_angle=1., loop=True))
        self.assertGreater(max(map(abs, values)), .05); self.assertLessEqual(max(map(abs, values)), 1.)
        self.assertEqual(report['loop_status'], 'converged')
        self.assertLess(report['endpoint_velocity_error_deg_s'], .1)

    def test_nonloop_is_not_forced_back_to_first_pose(self):
        ticks = grid(1.); poses = [(10*t, 0., 10*t) for t in ticks]
        values, report = solve(ticks, poses, loop=True)
        self.assertEqual(report['loop_status'], 'source_not_loopable')
        self.assertNotEqual(values[0], values[-1])


class JointGuardTests(unittest.TestCase):
    def test_collision_checks_added_penetration_without_erasing_existing_coverage(self):
        pose = {name: (1.,0.,0.,1.,x,y) for name,x,y in [
            ('head',0,0), ('neck',0,-20), ('chest',0,-30), ('pelvis',0,-100),
            ('upperarm_l',-20,-25), ('upperarm_r',20,-25)]}
        proxies = capsules(pose)
        self.assertEqual([p['kind'] for p in proxies], ['head', 'torso'])
        before = penetration([[-10.,-10.]], proxies)
        self.assertFalse(clearance([[-5.,-10.]], before, proxies)['passed'])
        existing = penetration([[-5.,-10.]], proxies)
        self.assertTrue(clearance([[-4.8,-10.]], existing, proxies)['passed'])
        self.assertGreater(existing[0], 0.)

    def test_thin_triangle_reduces_only_new_response_instead_of_hiding_failure(self):
        document = dict(bones=[dict(name='root', x=0., y=0., rotation=0.),
            dict(name='helper', parent='root', x=0., y=0., rotation=0.),
            dict(name='m5-response-helper', parent='helper', x=0., y=0., rotation=0.)],
            slots=[dict(name='cloth', bone='root', attachment='cloth')],
            skins=[dict(attachments={'cloth': {'cloth': dict(type='mesh', uvs=[0,0,1,0,1,1],
                triangles=[0,1,2], vertices=[1,0,0.,0.,1., 1,2,10.,0.,1., 1,0,10.,.1,1.])}})],
            animations={'move': {'bones': {'m5-response-helper': {'rotate': [
                dict(time=0., value=0.), dict(time=1/120, value=1.), dict(time=2/120, value=0.)]}}}})
        baseline = deepcopy(document); baseline['animations']['move']['bones'] = {}
        times = [0., 1/120, 2/120]; poses = [matrices(baseline, 'move', t) for t in times]
        records = [dict(slot='cloth', helpers=['m5-response-helper'], peak_response_deg=1., springs=[dict(peak_angle_deg=1.)])]
        result = protect(document, baseline, 'move', records, times, poses, _points)
        self.assertLess(result[0]['effective_gain'], 1.)
        self.assertGreater(result[0]['effective_gain'], 0.)
        self.assertGreaterEqual(result[0]['history'][-1]['min_area_ratio'], .55)
        self.assertGreater(result[0]['history'][0]['failed_samples'], 0)
        self.assertEqual(document['bones'], baseline['bones'])


if __name__ == '__main__': unittest.main()
