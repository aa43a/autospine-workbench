"""Wind must move a static rig, preserve roots, and be portable across solvers."""
from copy import deepcopy
import json
import math
import unittest

from autospine_workbench.targets.character43 import joint_secondary, joint_wind
from autospine_workbench.targets.character43.joint_animation_config import defaults, normalize
from autospine_workbench.targets.character43.joint_spring import grid, solve
from autospine_workbench.targets.character43.affine_pose import sample
from test_joint_secondary import scene
from test_joint_follow import object_scene
from unittest.mock import patch


def preview_fixture():
    files, document = scene()
    config = joint_secondary.defaults(wind=True)
    config['hair'].update(enabled=True, cascade=True)
    config['cloth']['enabled'] = True
    config['wind'].update(enabled=True, strength=33., direction=20., seed=712, gust=.4)
    output, report = joint_secondary.apply(files, document, 'idle', config, [0., 2.])
    return dict(document=output, config=config, report=report, template=report['preview_data'])


class JointWindTests(unittest.TestCase):
    def test_equilibrium_response_keeps_high_strengths_distinct_and_legacy_frozen(self):
        ticks = grid(4.); poses = [(0., 0., -90.) for _ in ticks]
        angles = []
        for strength in (0., 25., 50., 75., 100.):
            cfg = dict(joint_wind.defaults(), enabled=True, strength=strength, gust=0., response_profile=joint_wind.RESPONSE_PROFILE)
            wind, _ = joint_wind.vectors(cfg, ticks)
            force = joint_wind.angular_forces(wind, poses, profile=cfg['response_profile'], stiffness=36., max_angle=6.)
            values, _ = solve(ticks, poses, max_angle=6., external_forces=force)
            angles.append(values[-1])
        self.assertEqual(angles[0], 0.)
        self.assertTrue(all(b > a+.2 for a,b in zip(angles, angles[1:])), angles)
        self.assertLess(angles[-1], 6.)
        old = dict(joint_wind.defaults(), enabled=True)
        self.assertEqual(old, joint_wind.normalize(old, 4.))
        self.assertNotIn('response_profile', normalize({'wind': old}, 4.)['wind'])
        self.assertEqual(defaults()['wind']['response_profile'], joint_wind.RESPONSE_PROFILE)
        with self.assertRaisesRegex(ValueError, 'response_profile'):
            joint_wind.normalize(dict(old, response_profile='unbounded'), 4.)

    def test_projected_overlap_diagnostic_does_not_clamp_rigid_safe_geometry(self):
        from autospine_workbench.targets.character43.affine_pose import matrices
        from autospine_workbench.targets.character43.joint_secondary_guard import protect
        from autospine_workbench.targets.character43.joint_secondary import _points
        doc = dict(bones=[dict(name='root', x=0., y=0., rotation=0.),
            dict(name='head', parent='root', x=0., y=0., rotation=0.),
            dict(name='neck', parent='root', x=0., y=-20., rotation=0.),
            dict(name='m5-object-hair', parent='root', x=0., y=0., rotation=0.)],
            slots=[dict(name='hair', bone='root', attachment='hair')],
            skins=[dict(attachments={'hair': {'hair':dict(type='mesh', uvs=[0,0,1,0,0,1], triangles=[0,1,2],
                vertices=[1,3,-10.,-10.,1., 1,3,-10.,-12.,1., 1,3,-12.,-10.,1.])}})],
            animations={'idle':{'bones':{'m5-object-hair':{'rotate':[
                dict(time=0.,value=0.),dict(time=1/120,value=20.),dict(time=2/120,value=20.)]}}}})
        base = deepcopy(doc); base['animations']['idle']['bones'] = {}
        times = [0.,1/120,2/120]; poses = [matrices(base,'idle',t) for t in times]
        records = [dict(slot='hair',helpers=['m5-object-hair'],peak_response_deg=20.,springs=[dict(peak_angle_deg=20.)])]
        old = protect(deepcopy(doc),base,'idle',deepcopy(records),times,poses,_points)
        new = protect(deepcopy(doc),base,'idle',deepcopy(records),times,poses,_points,projected_overlap='diagnostic')
        self.assertLess(old[0]['effective_gain'], 1.)
        self.assertEqual(new[0]['effective_gain'], 1.)
        self.assertGreater(new[0]['history'][0]['collision_failed_samples'], 0)
        self.assertEqual(new[0]['history'][0]['geometry_failed_samples'], 0)
        self.assertFalse(new[0]['collision']['physical_collision_evaluated'])
    def test_preview_route_reads_only_the_verified_candidate_bundle(self):
        from autospine_workbench.automation.motion_target_jobs import review_file
        from autospine_workbench.automation.pipeline_run import PipelineRunError
        with patch('autospine_workbench.automation.motion_target_jobs.context',
                   return_value=({}, {'wind-preview.json': b'{"verified":"candidate"}'})):
            raw, mime = review_file(None, 'job', ['wind-preview.json'])
            self.assertEqual(json.loads(raw)['verified'], 'candidate')
            self.assertEqual(mime, 'application/json')
        with patch('autospine_workbench.automation.motion_target_jobs.context', return_value=({}, {})):
            with self.assertRaisesRegex(PipelineRunError, 'artifact_not_found'):
                review_file(None, 'job', ['wind-preview.json'])

    def test_stationary_wind_reverses_and_off_recovers_without_playback_state(self):
        ticks = grid(4.); poses = [(0., 0., -90.) for _ in ticks]
        cfg = dict(joint_wind.defaults(), enabled=True, strength=25., gust=0.)
        def trajectory(config):
            wind, _ = joint_wind.vectors(config, ticks)
            return solve(ticks, poses, max_angle=10., external_forces=joint_wind.angular_forces(wind, poses))[0]
        right = trajectory(cfg); left = trajectory(dict(cfg, direction=180.))
        self.assertGreater(right[-1], .5)
        self.assertLess(max(abs(a+b) for a,b in zip(right, left)), 1e-12)
        self.assertEqual(trajectory(dict(cfg, enabled=False)), [0.]*len(ticks))
        stop = trajectory(dict(cfg, keys=[dict(time=0., strength=25., direction=0.),
                                          dict(time=1., strength=25., direction=0.),
                                          dict(time=1.1, strength=0., direction=0.)]))
        self.assertGreater(stop[120], .5)
        self.assertLess(abs(stop[-1]), .001)
        self.assertEqual(right, trajectory(cfg))

    def test_seed_and_shortest_direction_keys_are_deterministic_and_loop_honest(self):
        cfg = dict(joint_wind.defaults(), enabled=True, seed=99,
            keys=[dict(time=0., strength=30., direction=350.), dict(time=2., strength=50., direction=10.)])
        strength, angle = joint_wind.parameters(cfg, 1.)
        self.assertEqual((strength, angle), (40., 360.))
        values, report = joint_wind.vectors(cfg, grid(2.), loop=True)
        self.assertFalse(report['loop_compatible'])
        self.assertEqual(values, joint_wind.vectors(cfg, grid(2.), loop=True)[0])
        other = joint_wind.vectors(dict(cfg, seed=199), grid(2.))[0]
        self.assertNotEqual(values, other)
        cyclic = dict(cfg, keys=[], frequency=.7)
        _, report = joint_wind.vectors(cyclic, grid(2.), loop=True)
        self.assertTrue(report['loop_compatible']); self.assertEqual(report['effective_frequency_hz'], .5)
        poses = [(0., 0., -90.) for _ in values]
        _, evidence = solve(grid(2.), poses, external_forces=joint_wind.angular_forces(values, poses),
                            loop=True, external_loop_compatible=False)
        self.assertNotEqual(evidence['loop_status'], 'converged')

    def test_hair_cloth_and_pendant_share_wind_without_moving_body_or_roots(self):
        for kind, make_scene, slot in [('hair', scene, 'hair'), ('cloth', scene, 'skirt'), ('objects', object_scene, 'hair')]:
            with self.subTest(kind=kind):
                files, doc = make_scene(); doc['animations']['idle']['bones'] = {}
                original = deepcopy(doc); cfg = joint_secondary.defaults(wind=True)
                cfg[kind]['enabled'] = True
                cfg['wind'].update(enabled=True, strength=25., gust=0.)
                output, report = joint_secondary.apply(files, doc, 'idle', cfg, [0., 2.])
                self.assertEqual(doc, original)
                self.assertEqual(report['root_error_px'], 0.)
                self.assertGreater(report['regions'][0]['peak_response_deg'], .01)
                self.assertGreater(report['regions'][0]['peak_sampled_displacement_px'], .01)
                self.assertEqual(output['bones'][:len(doc['bones'])], doc['bones'])
                self.assertTrue(report['wind']['deterministic'])
                self.assertEqual(output['slots'], original['slots'])
                for field in ('uvs', 'triangles'):
                    if kind != 'hair':
                        self.assertEqual(output['skins'][0]['attachments'][slot][slot][field], original['skins'][0]['attachments'][slot][slot][field])
                self.assertEqual({t:sample(output,'idle',t)[0] for t in (.21,1.17,1.93)},
                                 {t:sample(output,'idle',t)[0] for t in (1.93,.21,1.17)})

    def test_wind_disabled_preserves_legacy_solution_and_frozen_config(self):
        files, doc = scene(); old = {'hair':{'enabled':True}, 'cloth':{'enabled':True}}
        before, _ = joint_secondary.apply(files, doc, 'idle', old, [0., 2.])
        modern = dict(old, wind=joint_wind.defaults())
        after, _ = joint_secondary.apply(files, doc, 'idle', modern, [0., 2.])
        self.assertEqual(before, after)
        legacy = normalize(old, 2.)
        self.assertNotIn('wind', legacy); self.assertNotIn('wind_response', legacy['hair'])
        self.assertEqual(legacy, normalize(legacy, 2.))
        new = defaults(); self.assertEqual(new, normalize(new, 2.))

    def test_invalid_wind_is_rejected_and_local_response_zero_is_respected(self):
        for cfg in (dict(enabled=1), dict(seed=.5), dict(direction=float('nan')), dict(strength=101),
                    dict(keys=[dict(time=1., strength=20., direction=0.), dict(time=1., strength=30., direction=0.)])):
            with self.assertRaises(ValueError): joint_wind.normalize(cfg, 2.)
        files, doc = scene(); doc['animations']['idle']['bones'] = {}
        cfg = joint_secondary.defaults(wind=True); cfg['hair'].update(enabled=True, overrides={'hair':{'wind_response':0.}})
        cfg['wind']['enabled'] = True
        _, report = joint_secondary.apply(files, doc, 'idle', cfg, [0., 2.])
        self.assertEqual(report['regions'][0]['peak_response_deg'], 0.)


if __name__ == '__main__':
    unittest.main()
