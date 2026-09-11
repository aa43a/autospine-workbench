"""Discrete deformation has a complete replay contract and a usable CLI artifact."""
from contextlib import redirect_stdout
from copy import deepcopy
import importlib.util
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch
from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from test_ordinary_sleeve_deform import sources
from autospine_workbench.asset.planning.ordinary_sleeve_deform import build
from autospine_workbench.asset.planning.ordinary_sleeve_deform_validation import validate
from autospine_workbench.benchmark.mesh_storage import publish_mesh_report, read_mesh_report


class DeformContractTests(unittest.TestCase):
    def test_schema_full_replay_and_tampering(self):
        repair,source,draft,skeleton = sources(True)
        doc = build(repair,source,draft,skeleton)
        schema = json.loads(Path('schemas/ordinary-sleeve-deform-v1.schema.json').read_text())
        motion = json.loads(Path('schemas/ordinary-sleeve-motion-v1.schema.json').read_text())
        registry = Registry().with_resource('ordinary-sleeve-motion-v1.schema.json', Resource.from_contents(motion))
        check = Draft202012Validator(schema, registry=registry)
        check.check_schema(schema); check.validate(doc)
        closure = dict(repair=repair,source=source,draft=draft,skeleton=skeleton)
        self.assertIs(validate(doc,**closure),doc)
        for mutation in [lambda d:d.update(runtime_status='passed'),
                         lambda d:d['records'][0]['tracks'][0]['keys'].pop(),
                         lambda d:d['records'][0]['tracks'][0].update(max_adjacent_delta_px=999),
                         lambda d:d.update(delta_space='spine-local'),
                         lambda d:d['records'][0]['tracks'][0]['keys'][0].update(time=1)]:
            bad=deepcopy(doc);mutation(bad)
            with self.assertRaises(ValueError): validate(bad,**closure)
        bad=deepcopy(source);bad['project_id']='different'
        with self.assertRaisesRegex(ValueError,'source_mismatch'):
            validate(doc,repair=repair,source=bad,draft=draft,skeleton=skeleton)

    def test_cli_immutable_readback_and_paired_review(self):
        repair,source,draft,skeleton=sources(True)
        spec=importlib.util.spec_from_file_location('deform_cli','tools/build-ordinary-sleeve-deform.py')
        cli=importlib.util.module_from_spec(spec);spec.loader.exec_module(cli)
        with tempfile.TemporaryDirectory() as folder:
            state=Path(folder)/'state';out=Path(folder)/'out';kind='project-component-partitions'
            for item in [source,draft,repair]: sha=publish_mesh_report(state,kind,item)
            inputs=SimpleNamespace(skeleton=skeleton,assert_current=MagicMock())
            context=MagicMock();context.__enter__.return_value=inputs
            argv=['deform','fresh','--repair',sha,'--state-root',str(state),'--output',str(out)]
            with patch('sys.argv',argv),patch.object(cli,'load_inputs',return_value=context),redirect_stdout(io.StringIO()) as output:
                cli.main()
            digest=output.getvalue().strip();doc=read_mesh_report(state,kind,digest)
            self.assertEqual(doc,build(repair,source,draft,skeleton))
            self.assertEqual(doc,json.loads((out/(digest+'.json')).read_text()))
            self.assertEqual(digest,publish_mesh_report(state,kind,doc))
            html=(out/'index.html').read_text(encoding='utf-8')
            for phrase in ['修正前','离散修正候选','二阶差分','type="range"','连续性通过证明']:
                self.assertIn(phrase,html)
            self.assertIn('o.value=s.value',html)
            self.assertIn(doc['repair_sha256'],html)
            inputs.assert_current.assert_called_once()


if __name__ == '__main__': unittest.main()
