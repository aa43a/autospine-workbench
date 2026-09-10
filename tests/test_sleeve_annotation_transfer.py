"""Labels survive exact source geometry only; motion approval never transfers."""
from copy import deepcopy
import unittest
from tests.test_sleeve_regions import SleeveRegionTests
from autospine_workbench.asset.planning.sleeve_regions import build, template
from autospine_workbench.automation.sleeve_annotation_transfer import transfer, check


class AnnotationTransferTests(unittest.TestCase):
    def setUp(self):
        self.candidate = build(*SleeveRegionTests().fixture())
        self.draft = template(self.candidate)
        assignments = self.draft['records'][0]['assignments']
        assignments[0].update(role='sleeve', origin='geometry_prefill')
        assignments[4].update(role='hanging_cloth', origin='manual_edit')

    def test_exact_labels_remain_without_mutation_and_receipt_replays(self):
        original = deepcopy((self.candidate, self.draft))
        new = deepcopy(self.candidate); new['skeleton_sha256'] = 'b'*64
        draft, receipt = transfer(self.candidate, self.draft, new)
        self.assertEqual(receipt['manual_count'], 1)
        self.assertEqual(receipt['geometry_count'], 1)
        self.assertEqual(receipt['pending_count'], 3)
        self.assertEqual(draft, check(receipt, self.candidate, self.draft, new))
        self.assertTrue(receipt['requires_save'])
        self.assertEqual(original, (self.candidate, self.draft))
        bad = dict(receipt, manual_count=5)
        with self.assertRaises(ValueError): check(bad, self.candidate, self.draft, new)

    def test_changed_pixels_geometry_winding_or_side_never_reuse(self):
        changes = [lambda r: r.update(source_image_sha256='b'*64),
                   lambda r: r['vertices_xy'][12].__setitem__(0, 23.001),
                   lambda r: r['triangles'][4].reverse(),
                   lambda r: r.update(bone_ids=['upperarm_r','forearm_r','hand_r'])]
        for change in changes:
            new = deepcopy(self.candidate); change(new['records'][0])
            draft, receipt = transfer(self.candidate, self.draft, new)
            self.assertEqual(receipt['manual_count'], 0)
            self.assertEqual(draft['records'][0]['assignments'][4]['origin'], 'pending')

    def test_geometry_prefill_does_not_become_manual_when_suggestion_changes(self):
        new = deepcopy(self.candidate)
        new['records'][0]['suggestions'][0]['suggested_role'] = 'cuff'
        draft, receipt = transfer(self.candidate, self.draft, new)
        self.assertEqual(receipt['geometry_count'], 0)
        self.assertEqual(draft['records'][0]['assignments'][0]['origin'], 'pending')

    def test_index_reordering_uses_triangle_geometry_and_ambiguous_matches_fail_closed(self):
        new = deepcopy(self.candidate)
        row = new['records'][0]
        row['triangles'].reverse()
        for i, suggestion in enumerate(reversed(self.candidate['records'][0]['suggestions'])):
            row['suggestions'][i] = dict(suggestion, triangle_id=i)
        draft, receipt = transfer(self.candidate, self.draft, new)
        self.assertEqual(draft['records'][0]['assignments'][0]['role'], 'hanging_cloth')
        row['triangles'][1] = row['triangles'][0][:]
        draft, receipt = transfer(self.candidate, self.draft, new)
        self.assertEqual(receipt['manual_count'], 0)
