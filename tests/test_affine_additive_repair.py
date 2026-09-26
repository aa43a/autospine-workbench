from copy import deepcopy
import unittest
from unittest.mock import patch

from autospine_workbench.targets.character43.affine_area_repair import repair
from autospine_workbench.targets.character43.affine_pose import sample
from test_character_affine_repair import fixture


def corrected_fixture():
    doc = fixture()
    # Weighted mesh has five influences. Existing deformation also moves the
    # fixed single-bone vertex; an additive joint solve must preserve that move.
    doc['animations']['walk']['attachments'] = {'default': {'mesh': {'mesh': {'deform': [
        dict(time=0, vertices=[.02, .03]*5), dict(time=.37, vertices=[.04, .06]*5),
        dict(time=1, vertices=[.02, .03]*5)]}}}}
    return doc


class AdditiveRepairTests(unittest.TestCase):
    def test_healthy_single_bone_skin_requires_no_mixed_chain_solve(self):
        from test_limb_transverse_repair import fixture as single_bone_fixture
        from autospine_workbench.targets.character43.limb_transverse_repair import build
        doc = single_bone_fixture()
        doc['animations']['motion']['bones']['thigh_l']['scale'][-1]['x'] = .8
        rest = deepcopy(doc); rest['animations']['motion'] = {'bones': {}}
        deformed, _ = build(doc, 'motion', ['leg'])
        result, report = repair(deformed, 'motion', samples=3, additive=True,
            convergent=True, projected_reference=True, dual_floor=True,
            setup_vertices=sample(rest, 'motion', 0)[0])
        self.assertEqual(result, deformed)
        self.assertEqual(report['records'], [])

    def test_composes_displacement_and_preserves_fixed_vertex_and_prior_knots(self):
        doc = corrected_fixture(); before = deepcopy(doc)
        def translate(context, points):
            return [[p[0]+(.01 if free else 0), p[1]+(.02 if free else 0)]
                    for p, free in zip(points, context['free'])]
        with patch('autospine_workbench.targets.character43.affine_area_repair.project', translate):
            result, evidence = repair(doc, 'walk', samples=3, additive=True)
        self.assertEqual(doc, before)
        self.assertEqual(result['bones'], doc['bones'])
        self.assertEqual(result['skins'], doc['skins'])
        keys = result['animations']['walk']['attachments']['default']['mesh']['mesh']['deform']
        self.assertIn(.37, [k['time'] for k in keys])
        for t in [k['time'] for k in keys]:
            old = sample(doc, 'walk', t)[0]['mesh']; new = sample(result, 'walk', t)[0]['mesh']
            self.assertEqual(old[0], new[0])
            for i in (1, 2):
                self.assertAlmostEqual(new[i][0]-old[i][0], .01)
                self.assertAlmostEqual(new[i][1]-old[i][1], .02)
        self.assertEqual(evidence['composition'], 'additive_to_existing_local_deform')

    def test_temporal_seed_transports_only_new_delta(self):
        doc = corrected_fixture(); seeds = []
        def solve(context, points, initial=None):
            seeds.append((deepcopy(points), deepcopy(initial)))
            return deepcopy(points), dict(converged=False)
        rest = deepcopy(doc); rest['animations']['walk'] = {'bones': {}}
        # Force the existing deformed triangle to require a solve, without
        # borrowing a changed setup reference or discarding the existing offset.
        offsets = doc['animations']['walk']['attachments']['default']['mesh']['mesh']['deform'][1]['vertices']
        offsets[7] = offsets[9] = -.95
        with patch('autospine_workbench.targets.character43.area_projection.project', solve):
            result, _ = repair(doc, 'walk', samples=3, additive=True,
                convergent=True, projected_reference=True, temporal=True,
                setup_vertices=sample(rest, 'walk', 0)[0])
        self.assertTrue(seeds)
        for original, seed in seeds[1:]:
            self.assertEqual(original, seed)
        for t in (0, .37, .5, 1):
            self.assertEqual(sample(result, 'walk', t)[0], sample(doc, 'walk', t)[0])

    def test_rejects_implicit_overwrite_and_unsupported_sparse_or_curved_keys(self):
        with self.assertRaisesRegex(ValueError, 'existing_deform'):
            repair(corrected_fixture(), 'walk', samples=3)
        for field in ('offset', 'curve'):
            doc = corrected_fixture()
            doc['animations']['walk']['attachments']['default']['mesh']['mesh']['deform'][0][field] = 1
            with self.assertRaisesRegex(ValueError, 'dense_linear'):
                repair(doc, 'walk', samples=3, additive=True)


if __name__ == '__main__':
    unittest.main()
