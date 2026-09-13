from copy import deepcopy
from hashlib import sha256
import json
import unittest
from autospine_workbench.automation.cohort_versions import select


class VersionTests(unittest.TestCase):
    def setUp(self):
        candidate = dict(source=dict(path='a.psd', sha256='a'*64), mapping=dict(status='accepted'))
        self.manifest = dict(characters=[dict(id='a', dataset_split='holdout', psd_candidates=[candidate],
            reviewed_joints={'neck': [1, 2]}, annotation_status='reviewed', supported_motion_set=['idle'])])
        self.raw = json.dumps(self.manifest).encode()
        self.versions = dict(schema='autospine.cohort-source-versions/v1',
            baseline_manifest_sha256=sha256(self.raw).hexdigest(), authority='human_source_selection',
            production_authorized=False, entries=[dict(character_id='a', dataset_split='holdout',
                previous_psd_candidates=[candidate], source=dict(path='a.psd', sha256='b'*64,
                    byte_size=100, canvas=[100, 200]))])

    def test_new_version_never_mutates_or_inherits_review(self):
        before = deepcopy(self.manifest)
        result = select(self.manifest, self.raw, self.versions)
        self.assertEqual(self.manifest, before)
        character = result['characters'][0]
        self.assertEqual(character['reviewed_joints'], {})
        self.assertEqual(character['annotation_status'], 'pending')
        self.assertEqual(character['supported_motion_set'], [])
        self.assertEqual(character['dataset_split'], 'holdout')
        self.assertEqual(character['psd_candidates'][0]['mapping']['status'], 'candidate')

    def test_stale_scope_duplicate_or_new_path_rejected(self):
        cases = []
        bad = deepcopy(self.versions); bad['baseline_manifest_sha256'] = '0'*64; cases.append(bad)
        bad = deepcopy(self.versions); bad['entries'] *= 2; cases.append(bad)
        bad = deepcopy(self.versions); bad['entries'][0]['dataset_split'] = 'development'; cases.append(bad)
        bad = deepcopy(self.versions); bad['entries'][0]['source']['path'] = '../other.psd'; cases.append(bad)
        for bad in cases:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                select(self.manifest, self.raw, bad)
