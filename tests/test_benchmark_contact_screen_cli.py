"""Source-bound contact screening never promotes geometry to joint authority."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from tests import test_benchmark_contact_probe_cli as fixtures
from autospine_workbench.benchmark.artifacts import publish_report
from autospine_workbench.benchmark.contact_screen_cli import read_contact_screen
from autospine_workbench.resolved_project import canonical_sha256


class ContactScreenCliTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.ContactProbeCliTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root, self.manifest, self.state = self.fixture.root, self.fixture.manifest, self.fixture.state

    def invoke(self, character=None):
        return self.fixture.fixture.fixture.fixture.invoke('screen-contacts',
            '--manifest', self.root / 'manifest.json', '--evidence', self.root / 'evidence.json',
            '--workspace', self.root, '--character', character or self.fixture.candidate['character_id'],
            '--html', self.root / 'screen.html')

    def test_replay_and_idempotence_preserve_unassigned_evidence(self):
        code, doc = self.invoke()
        self.assertEqual(code, 0, doc)
        self.assertEqual(read_contact_screen(self.state, self.manifest, canonical_sha256(doc), workspace=self.root), doc)
        self.assertEqual(self.invoke(), (0, doc))
        self.assertEqual(doc['authority'], 'none')
        self.assertTrue(doc['diagnostic_only'])
        self.assertTrue(all(c['joint_id'] is None for r in doc['relations'] for p in r['pairs'] for c in p['contacts']))
        self.assertTrue((self.root / 'screen.html').exists())

    def test_forged_status_or_missing_source_cannot_replay(self):
        _, doc = self.invoke()
        forged = deepcopy(doc)
        forged['relations'][0]['pairs'][0]['contacts'][0]['geometry_status'] = 'rejected_deep_overlap'
        digest = publish_report(self.state, self.manifest['dataset_id'], 'contact-screens', forged)
        with self.assertRaises(ValueError):
            read_contact_screen(self.state, self.manifest, digest, workspace=self.root)
        (self.root / 'layer-0.png').write_bytes(b'changed')
        with self.assertRaises(ValueError):
            read_contact_screen(self.state, self.manifest, canonical_sha256(doc), workspace=self.root)

    def test_holdout_and_oversized_layers_fail_before_layer_reads(self):
        held = next(row['id'] for row in self.manifest['characters'] if row['dataset_split'] == 'holdout')
        with patch('autospine_workbench.benchmark.mapping_cli.read_real_file') as reader:
            self.assertEqual(self.invoke(held)[0], 1)
            reader.assert_not_called()
        from autospine_workbench.benchmark.semantic_cli import _read_asset
        with patch('autospine_workbench.benchmark.contact_probe.MAX_BYTES', 1), \
                patch('autospine_workbench.benchmark.semantic_cli._read_asset', wraps=_read_asset) as reader:
            self.assertEqual(self.invoke()[0], 1)
            self.assertEqual([c.args[1]['path'] for c in reader.call_args_list], ['audit.json'])
        self.assertFalse(self.state.exists())


if __name__ == '__main__':
    unittest.main()
