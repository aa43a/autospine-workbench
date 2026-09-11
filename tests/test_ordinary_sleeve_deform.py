"""Sparse world deltas preserve source identities and never imply continuous admission."""
from copy import deepcopy
import math
import unittest
from test_ordinary_sleeve import fixture
from autospine_workbench.asset.planning.ordinary_sleeve_repair import build as repair_build
from autospine_workbench.asset.planning.ordinary_sleeve_deform import build
from autospine_workbench.asset.planning.component_temporal_qa import passed
from autospine_workbench.resolved_project import canonical_sha256


def sources(failing=False):
    source,draft,skeleton=fixture()
    if failing:
        row=source['records'][0]['mesh']['weights'][3]
        row[1]['weight']=0.;row[2]['weight']=1.
    return repair_build(source,draft,skeleton),source,draft,skeleton


class OrdinarySleeveDeformTests(unittest.TestCase):
    def test_passing_frames_unchanged_and_no_admission(self):
        args=sources();before=deepcopy(args);doc=build(*args)
        self.assertEqual(args,before);self.assertEqual(doc,build(*args))
        self.assertEqual(doc['repair_sha256'],canonical_sha256(args[0]))
        row=doc['records'][0]
        self.assertEqual(row['status'],'candidate_requires_review')
        self.assertIn('continuous_interpolation_required',row['reason_codes'])
        self.assertEqual(doc['continuous_interpolation_status'],'not_evaluated')
        self.assertFalse(doc['production_authorized'])
        self.assertEqual(row['weights'],args[0]['records'][0]['selected_row']['weights'])
        for track in row['tracks']:
            self.assertEqual(len(track['keys']),129);self.assertEqual(track['corrected_ticks'],0)
            self.assertTrue(all(not key['offsets'] for key in track['keys']))
            self.assertTrue(track['setup_exact']);self.assertTrue(track['loop_exact'])

    def test_failing_cuff_pose_has_bounded_sparse_correction_and_temporal_diagnostics(self):
        args=sources(True);doc=build(*args);row=doc['records'][0]
        self.assertTrue(any(t['corrected_ticks'] for t in row['tracks']))
        for track in row['tracks']:
            self.assertTrue(track['protected_vertices_preserved'])
            self.assertTrue(track['previously_passed_preserved'])
            self.assertLessEqual(track['max_offset_px'],row['budget_px']+1e-9)
            self.assertTrue(math.isfinite(track['max_adjacent_delta_px']))
            self.assertTrue(math.isfinite(track['max_second_difference_px']))
            for key,old in zip(track['keys'],track['before_qa']):
                if passed(old) or key['tick'] in (0,64,128):self.assertEqual(key['offsets'],[])
                for entry in key['offsets']:self.assertLess(entry['vertex_id'],6)
            self.assertEqual(track['failed_ticks'],sum(not passed(q) for q in track['qa']))

    def test_unknown_and_unavailable_rows_not_dropped_and_tampered_repair_rejected(self):
        source,draft,skeleton=fixture()
        draft['records'][0]['assignments'][2]['role']='unknown'
        source['draft_sha256']=canonical_sha256(draft)
        source['records'].append(dict(layer_id='residual',component_id='c2',mesh=None))
        repair=repair_build(source,draft,skeleton);doc=build(repair,source,draft,skeleton)
        self.assertEqual(len(doc['records']),2)
        self.assertIn('ownership_review_required',doc['records'][0]['reason_codes'])
        self.assertEqual(doc['records'][1]['tracks'],[])
        self.assertEqual(doc['records'][1]['status'],'blocked')
        repair['records'][0]['selected_row']['weights'][0][0]['weight']=.2
        with self.assertRaises(ValueError):build(repair,source,draft,skeleton)


if __name__=='__main__':unittest.main()
