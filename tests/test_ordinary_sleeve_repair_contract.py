"""Repair selection must retain full provenance, rejected trials and blocked rows."""
from copy import deepcopy
from contextlib import redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch, MagicMock
from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from test_ordinary_sleeve import fixture
from autospine_workbench.asset.planning.ordinary_sleeve_repair import build
from autospine_workbench.asset.planning.ordinary_sleeve_repair_validation import validate
from autospine_workbench.asset.planning.ordinary_sleeve_repair_review import render
from autospine_workbench.benchmark.mesh_storage import publish_mesh_report, read_mesh_report
from autospine_workbench.resolved_project import canonical_sha256


def failing_fixture():
    source, draft, skeleton = fixture()
    weights = source['records'][0]['mesh']['weights'][0]
    weights[1]['weight'] = 0.; weights[2]['weight'] = 1.
    return source, draft, skeleton


class OrdinaryRepairContractTests(unittest.TestCase):
    def test_schema_replay_and_immutable_storage(self):
        args = failing_fixture(); doc = build(*args)
        schema = json.loads(Path('schemas/ordinary-sleeve-repair-v1.schema.json').read_text())
        motion = json.loads(Path('schemas/ordinary-sleeve-motion-v1.schema.json').read_text())
        registry = Registry().with_resource('ordinary-sleeve-motion-v1.schema.json', Resource.from_contents(motion))
        validator = Draft202012Validator(schema, registry=registry)
        validator.check_schema(schema); validator.validate(doc)
        self.assertIs(validate(doc, args[2], source=args[0], draft=args[1]), doc)
        self.assertTrue(doc['records'][0]['selected'])
        self.assertEqual(len(doc['records'][0]['trials']), 3)
        with tempfile.TemporaryDirectory() as folder:
            sha = publish_mesh_report(folder, 'project-component-partitions', doc)
            self.assertEqual(read_mesh_report(folder, 'project-component-partitions', sha), doc)
            self.assertEqual(publish_mesh_report(folder, 'project-component-partitions', doc), sha)
        source, draft, skeleton = fixture()
        source['records'][0]['mesh'] = None
        unavailable = build(source, draft, skeleton)
        validator.validate(unavailable)
        self.assertEqual(unavailable['records'][0]['selected_row']['status'], 'blocked')

    def test_replay_rejects_forged_selection_metrics_and_sources(self):
        source, draft, skeleton = failing_fixture(); doc = build(source, draft, skeleton)
        changes = [lambda d: d.update(global_replacement_authorized=True),
                   lambda d: d['records'][0].update(selected_trial='hand_shared_boundary'),
                   lambda d: d['records'][0]['trials'].pop(),
                   lambda d: d['records'][0]['selected_row']['tracks'][0]['qa'].pop(),
                   lambda d: d['records'][0]['before'].update(status='candidate_requires_review')]
        for change in changes:
            bad = deepcopy(doc); change(bad)
            with self.assertRaises(ValueError): validate(bad, skeleton, source=source, draft=draft)
        altered = deepcopy(draft); altered['records'][0]['assignments'][0]['role'] = 'unknown'
        with self.assertRaisesRegex(ValueError, 'source_mismatch'):
            validate(doc, skeleton, source=source, draft=altered)
        with self.assertRaises(TypeError): validate(doc, skeleton)

    def test_paired_timeline_and_cli_real_store(self):
        source, draft, skeleton = failing_fixture()
        spec = importlib.util.spec_from_file_location('repair_cli', 'tools/build-ordinary-sleeve-repair.py')
        cli = importlib.util.module_from_spec(spec); spec.loader.exec_module(cli)
        with tempfile.TemporaryDirectory() as folder:
            state = Path(folder)/'state'; output = Path(folder)/'output'
            kind = 'project-component-partitions'
            publish_mesh_report(state, kind, draft)
            sha = publish_mesh_report(state, kind, source)
            inputs = SimpleNamespace(skeleton=skeleton, assert_current=MagicMock())
            context = MagicMock(); context.__enter__.return_value = inputs
            argv = ['repair', 'fresh', '--source', sha, '--output', str(output), '--state-root', str(state)]
            with patch('sys.argv', argv), patch.object(cli, 'load_inputs', return_value=context), redirect_stdout(io.StringIO()) as stream:
                cli.main()
            result_sha = stream.getvalue().strip()
            result = read_mesh_report(state, kind, result_sha)
            self.assertEqual(canonical_sha256(result), result_sha)
            self.assertEqual(json.loads((output/(result_sha+'.json')).read_text()), result)
            html = (output/'index.html').read_text(encoding='utf-8')
            self.assertIn('修正前', html); self.assertIn('当前候选选择', html)
            self.assertIn('仍阻塞', html); self.assertIn('type="range"', html)
            self.assertIn(result['schema'], html); self.assertIn(result['source_sha256'], html)
            self.assertIn('other.value=select.value', html)
            inputs.assert_current.assert_called_once()
        with self.assertRaises(ValueError): render(dict(schema='autospine.ordinary-sleeve-motion/v1'))


if __name__ == '__main__': unittest.main()
