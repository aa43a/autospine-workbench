"""Passing integer keys can still collapse under world-delta interpolation."""
from copy import deepcopy
import unittest
from test_ordinary_sleeve import fixture
from autospine_workbench.asset.planning.ordinary_deform_sampling import dense_offsets,sample
from autospine_workbench.asset.planning.component_temporal_qa import passed


def inputs():
    source,_,skeleton=fixture();mesh=source['records'][0]['mesh']
    for row in mesh['weights']:
        for i,w in enumerate(row):w['weight']=1. if i==0 else 0.
    track=dict(bone_id='forearm',drivers=['forearm_l','hand_l'],amplitudes=[30,0],
        keys=[dict(tick=t,time=t/64,offsets=[]) for t in range(129)])
    return mesh,skeleton['bones'],track


class OrdinaryDeformSamplingTests(unittest.TestCase):
    def test_passing_keys_but_collapsed_midframes_are_detected(self):
        mesh,chain,track=inputs()
        for key in track['keys']:
            if key['tick']%2:
                key['offsets']=[dict(vertex_id=i,delta_xy=[-2*x,-2*y]) for i,(x,y) in enumerate(mesh['vertices_xy'])]
        original=deepcopy((mesh,chain,track));report=sample(mesh,chain,track)
        self.assertEqual((mesh,chain,track),original)
        self.assertTrue(all(passed(q) for q in report['qa'][::4]))
        self.assertIn(2,report['failed_between_keys']);self.assertIn(2,report['new_failed_between_keys'])
        self.assertEqual(len(report['qa']),513);self.assertFalse(report['continuous_time_proven'])
        self.assertTrue(report['setup_exact']);self.assertTrue(report['loop_exact'])

    def test_exact_zero_deltas_and_periodic_boundary_diagnostic(self):
        mesh,chain,track=inputs();report=sample(mesh,chain,track)
        self.assertEqual(report['failed_samples'],[]);self.assertEqual(report['max_offset_px'],0.)
        # Ramp across the final key span produces a cyclic velocity corner at 0.
        track['keys'][127]['offsets']=[dict(vertex_id=0,delta_xy=[1.,0.])]
        report=sample(mesh,chain,track)
        self.assertGreater(report['max_cyclic_delta_second_difference_normalized'],0.)
        self.assertEqual(report,sample(mesh,chain,track))
        with self.assertRaises(ValueError):sample(mesh,chain,track,substeps=2)

    def test_rejects_bad_order_duplicate_out_of_range_and_nonfinite(self):
        _,_,track=inputs();keys=track['keys']
        changes=[lambda k:k.pop(),lambda k:k[1].update(tick=2),lambda k:k[1].update(time=1.),
                 lambda k:k[1].update(offsets=[dict(vertex_id=9,delta_xy=[0.,0.])]),
                 lambda k:k[1].update(offsets=[dict(vertex_id=0,delta_xy=[float('nan'),0.])]),
                 lambda k:k[1].update(offsets=[dict(vertex_id=0,delta_xy=[1.,0.])]*2)]
        for change in changes:
            bad=deepcopy(keys);change(bad)
            with self.assertRaises(ValueError):dense_offsets(bad,9)
        self.assertEqual(len(dense_offsets(keys,9)),129)


if __name__=='__main__':unittest.main()
