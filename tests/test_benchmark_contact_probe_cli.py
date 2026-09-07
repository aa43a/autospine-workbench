"""Contact inspection with real synthetic PNG bytes and exact source replay."""
from copy import deepcopy
from io import BytesIO
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from tests import test_benchmark_semantic_cli as fixtures
from autospine_workbench.benchmark.artifacts import publish_report
from autospine_workbench.benchmark.contact_probe_cli import read_contact_probe
from autospine_workbench.resolved_project import canonical_sha256


class ContactProbeCliTests(unittest.TestCase):
    def setUp(self):
        from PIL import Image

        self.fixture = fixtures.SemanticCliTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root, self.manifest = self.fixture.root, self.fixture.manifest
        self.state = self.fixture.fixture.fixture.state
        output = self.fixture.evidence['characters'][0]['outputs']
        for index, name in enumerate(('topwear', 'handwear', 'footwear')):
            raw = BytesIO()
            Image.new('RGBA', (8, 8), (50, 80, 90, 255 if index != 2 else 0)).save(raw, format='PNG')
            output['layers'][index].update(name=name, image=self.fixture.write_asset(f'layer-{index}.png', raw.getvalue()))
            self.fixture.audit['layers'][index].update(name=name, alpha_nonzero=64 if index != 2 else 0)
        output['audit'] = self.fixture.write_asset('audit.json', json.dumps(self.fixture.audit).encode())
        raw = BytesIO()
        Image.new('RGBA', self.fixture.audit['canvas'], (50, 80, 90, 255)).save(raw, format='PNG')
        output['composite'] = self.fixture.write_asset('composite.png', raw.getvalue())
        self.candidate = self.fixture.load()[0]
        for name, doc in (('manifest', self.manifest), ('evidence', self.fixture.evidence)):
            (self.root / (name + '.json')).write_text(json.dumps(doc), encoding='utf-8')

    def invoke(self, character=None):
        return self.fixture.fixture.fixture.invoke('probe-contacts',
            '--manifest', self.root / 'manifest.json', '--evidence', self.root / 'evidence.json',
            '--workspace', self.root, '--character', character or self.candidate['character_id'],
            '--html', self.root / 'contacts.html')

    def test_exact_contact_replay_never_assigns_a_joint(self):
        code, doc = self.invoke()
        self.assertEqual(code, 0, doc)
        pair = doc['relations'][0]['pairs'][0]
        self.assertEqual(pair['contacts'][0]['area'], 64)
        self.assertIsNone(pair['contacts'][0]['joint_id'])
        self.assertIn('joint_assignment_blocked', doc['relations'][0]['reason_codes'])
        self.assertEqual(read_contact_probe(self.state, self.manifest, canonical_sha256(doc), workspace=self.root), doc)
        self.assertEqual(self.invoke(), (0, doc))

    def test_rehashed_contact_tamper_and_changed_png_are_rejected(self):
        _, doc = self.invoke()
        forged = deepcopy(doc)
        forged['relations'][0]['pairs'][0]['contacts'][0]['area'] = 1
        digest = publish_report(self.state, self.manifest['dataset_id'], 'contact-probes', forged)
        with self.assertRaises(ValueError):
            read_contact_probe(self.state, self.manifest, digest, workspace=self.root)
        (self.root / 'layer-0.png').write_bytes(b'changed')
        with self.assertRaises(ValueError):
            read_contact_probe(self.state, self.manifest, canonical_sha256(doc), workspace=self.root)

    def test_holdout_fails_before_opening_assets(self):
        held = next(row['id'] for row in self.manifest['characters'] if row['dataset_split'] == 'holdout')
        with patch('autospine_workbench.benchmark.mapping_cli.read_real_file') as reader:
            code, _ = self.invoke(held)
            self.assertEqual(code, 1)
            reader.assert_not_called()
        self.assertFalse(self.state.exists())
        self.assertFalse((self.root / 'contacts.html').exists())

    def test_layer_budget_is_checked_before_layer_reads_for_build_and_replay(self):
        from autospine_workbench.benchmark.semantic_cli import _read_asset

        with patch('autospine_workbench.benchmark.contact_probe.MAX_BYTES', 1), \
                patch('autospine_workbench.benchmark.semantic_cli._read_asset', wraps=_read_asset) as reader:
            code, result = self.invoke()
            self.assertEqual(code, 1)
            self.assertEqual(result['reason_code'], 'benchmark_semantic_layer_budget_exceeded')
            self.assertEqual([c.args[1]['path'] for c in reader.call_args_list], ['audit.json'])
        self.assertFalse(self.state.exists())
        _, doc = self.invoke()
        with patch('autospine_workbench.benchmark.contact_probe.MAX_BYTES', 1), \
                patch('autospine_workbench.benchmark.semantic_cli._read_asset', wraps=_read_asset) as reader:
            with self.assertRaisesRegex(ValueError, 'benchmark_semantic_layer_budget_exceeded'):
                read_contact_probe(self.state, self.manifest, canonical_sha256(doc), workspace=self.root)
            self.assertEqual([c.args[1]['path'] for c in reader.call_args_list], ['audit.json'])


if __name__ == '__main__':
    unittest.main()
