"""Ordinary sleeves retain real arm FK and strict QA without a fourth bone."""
from copy import deepcopy
import math
import unittest
from autospine_workbench.asset.planning.ordinary_sleeve import build, angles, MOTIONS
from autospine_workbench.resolved_project import canonical_sha256


def fixture():
    ids = ['upperarm_l', 'forearm_l', 'hand_l']
    bones = [dict(id=b, parent_id=ids[i-1] if i else 'chest',
                  head_xy=[i*10., 0.], tail_xy=[i*10.+10., 0.], world_rotation_degrees=0.)
             for i, b in enumerate(ids)]
    skeleton = dict(bones=bones)
    points = [[x, y] for start in (12., 18., 22.) for x, y in ((start, 0.), (start+2, 0.), (start, 2.))]
    weights = [[dict(bone_id=b, weight=1. if j == (1 if i < 6 else 2) else 0.,
                     local_xy=[p[0]-j*10., p[1]]) for j, b in enumerate(ids)] for i, p in enumerate(points)]
    mesh = dict(bone_ids=ids, vertices_xy=points, triangles=[[0, 1, 2], [3, 4, 5], [6, 7, 8]], weights=weights)
    draft = dict(schema='autospine.sleeve-region-draft/v1', project_id='fresh',
                 candidate_sha256='a'*64, authority='none', production_authorized=False,
                 records=[dict(layer_id='arm', component_id='c1', assignments=[
                     dict(triangle_id=i, role=role, origin='manual_edit') for i, role in enumerate(('sleeve', 'cuff', 'hand'))])])
    source = dict(schema='autospine.sleeve-weights/v1', project_id='fresh', authority='none',
                  production_authorized=False, draft_sha256=canonical_sha256(draft), candidate_sha256='a'*64,
                  skeleton_sha256=canonical_sha256(skeleton), records=[dict(layer_id='arm', component_id='c1', mesh=mesh)])
    return source, draft, skeleton


class OrdinarySleeveTests(unittest.TestCase):
    def test_true_fk_four_tracks_no_helper_and_determinism(self):
        args = fixture(); original = deepcopy(args)
        result = build(*args); row = result['records'][0]
        self.assertEqual(args, original)
        self.assertEqual(result, build(*args))
        self.assertEqual(result['schema'], 'autospine.ordinary-sleeve-motion/v1')
        self.assertEqual(row['status'], 'candidate_requires_review')
        self.assertNotIn('helper', row)
        self.assertEqual(row['bone_ids'], ['upperarm_l', 'forearm_l', 'hand_l'])
        self.assertEqual([t['bone_id'] for t in row['tracks']], [name for name, _ in MOTIONS])
        self.assertEqual(row['weights'], args[0]['records'][0]['mesh']['weights'])
        for track in row['tracks']:
            self.assertEqual(len(track['qa']), 129)
            self.assertEqual(len(track['samples']), 33)
            self.assertEqual(len(track['drivers']), 2)
            self.assertFalse(track['correction_selected'])
            self.assertNotIn('trial_keys', track)
            self.assertEqual(track['failed_ticks'], 0)
            self.assertEqual(track['loop_error'], 0.)
            self.assertEqual(track['samples'][0]['points'], track['samples'][-1]['points'])
        forearm = row['tracks'][0]['samples'][8]['points'][0]
        self.assertAlmostEqual(forearm[0], 10+2*math.cos(math.pi/6))
        self.assertAlmostEqual(forearm[1], 2*math.sin(math.pi/6))
        hand = row['tracks'][1]['samples'][8]['points']
        self.assertEqual(hand[:6], row['setup_vertices'][:6])
        self.assertNotEqual(hand[6:], row['setup_vertices'][6:])

    def test_unknown_is_blocked_and_drape_not_disguised_as_ordinary(self):
        for role, reason in [('unknown', 'ownership_review_required'),
                             ('hanging_cloth', 'ordinary_sleeve_drape_branch_required')]:
            source, draft, skeleton = fixture()
            draft['records'][0]['assignments'][2]['role'] = role
            source['draft_sha256'] = canonical_sha256(draft)
            row = build(source, draft, skeleton)['records'][0]
            self.assertEqual(row['status'], 'blocked')
            self.assertIn(reason, row['reason_codes'])
            self.assertNotIn('helper', row)

    def test_geometry_failures_not_silently_admitted(self):
        source, draft, skeleton = fixture()
        entries = source['records'][0]['mesh']['weights'][0]
        entries[1]['weight'] = 0.; entries[2]['weight'] = 1.
        row = build(source, draft, skeleton)['records'][0]
        self.assertEqual(row['status'], 'blocked')
        self.assertIn('motion_envelope_geometry_failure', row['reason_codes'])
        self.assertTrue(any(t['failed_ticks'] for t in row['tracks']))

    def test_source_and_inventory_errors_fail_closed(self):
        mutations = [lambda s, d, k: s.update(draft_sha256='b'*64),
                     lambda s, d, k: s.update(production_authorized=True),
                     lambda s, d, k: k['bones'][0].update(world_rotation_degrees=2),
                     lambda s, d, k: s['records'][0]['mesh']['triangles'][0].__setitem__(0, 1000)]
        for mutate in mutations:
            args = fixture(); mutate(*args)
            with self.assertRaises(ValueError): build(*args)
        self.assertEqual(angles((30, -30), 32), [30., -30.])
        for tick in (float('nan'), -1, 129):
            with self.assertRaises(ValueError): angles((30, 30), tick)


if __name__ == '__main__': unittest.main()
