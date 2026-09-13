"""Intake must not equate names, lifecycle, or variant matches with completion."""
from copy import deepcopy
import unittest
from autospine_workbench.automation.cohort_intake import assess


class IntakeTests(unittest.TestCase):
    def setUp(self):
        self.manifest = dict(schema='autospine.benchmark-manifest/v1', split_status='frozen', characters=[
            dict(id=str(i), dataset_split='holdout' if i > 6 else 'visible',
                 source=dict(path=f'png/{i}.png'),
                 psd_candidates=[dict(source=dict(path=f'{i}.psd', sha256=f'{i:064x}'))]) for i in range(10)])
        self.catalog = dict(schema='autospine.asset-library/v1', projects=[])

    def project(self, name, source, lifecycle='active'):
        return dict(id=name, name=name, source=source, lifecycle=lifecycle, project_revision=1)

    def test_identity_lifecycle_and_name_are_separate(self):
        self.catalog['projects'] = [self.project('0', dict(kind='audit')),
            self.project('upload1', dict(source_sha256=f'{1:064x}')),
            self.project('upload2', dict(source_sha256=f'{2:064x}'), 'trashed')]
        result = assess(self.manifest, self.catalog)
        self.assertEqual([r['reason_code'] for r in result['characters'][:4]], [
            'audit_source_verification_required', 'source_matched_workflow_not_assessed',
            'asset_restore_required', 'psd_import_required'])
        self.assertEqual(result['exact_active_single_source'], 1)
        self.assertTrue(all(r['whole_character_complete'] is None for r in result['characters']))
        self.assertEqual(result['independent_holdout_status'], 'requires_exposure_audit')

    def test_variants_and_duplicate_matches_require_selection(self):
        self.manifest['characters'][0]['psd_candidates'].append(dict(source=dict(path='other.psd', sha256='f'*64)))
        self.catalog['projects'] = [self.project('a', dict(source_sha256=f'{0:064x}')),
            self.project('b', dict(source_sha256=f'{1:064x}')), self.project('c', dict(source_sha256=f'{1:064x}'))]
        before = deepcopy(self.manifest)
        result = assess(self.manifest, self.catalog)
        self.assertEqual(result['characters'][0]['reason_code'], 'psd_variant_review_required')
        self.assertEqual(result['characters'][1]['reason_code'], 'project_selection_required')
        self.assertEqual(before, self.manifest)

    def test_rejects_unfrozen_or_incomplete_denominator(self):
        self.manifest['characters'].pop()
        with self.assertRaisesRegex(ValueError, 'frozen_ten'):
            assess(self.manifest, self.catalog)
