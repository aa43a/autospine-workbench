from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from jsonschema import Draft202012Validator
from referencing import Registry,Resource
from test_ordinary_sleeve_deform import sources
from autospine_workbench.asset.planning.ordinary_sleeve_deform import build as deform_build
from autospine_workbench.asset.planning.ordinary_deform_interpolation import build,validate
from autospine_workbench.benchmark.mesh_storage import publish_mesh_report,read_mesh_report


class InterpolationContractTests(unittest.TestCase):
    def test_schema_replay_storage_and_no_runtime_claim(self):
        repair,source,draft,skeleton=sources()
        deform=deform_build(repair,source,draft,skeleton)
        inputs=dict(deform=deform,repair=repair,source=source,draft=draft,skeleton=skeleton)
        report=build(**inputs)
        schema=json.loads(Path('schemas/ordinary-deform-interpolation-v1.schema.json').read_text())
        motion=json.loads(Path('schemas/ordinary-sleeve-motion-v1.schema.json').read_text())
        registry=Registry().with_resource('ordinary-sleeve-motion-v1.schema.json',Resource.from_contents(motion))
        checker=Draft202012Validator(schema,registry=registry);checker.check_schema(schema);checker.validate(report)
        self.assertIs(validate(report,**inputs),report)
        self.assertEqual(report['records'][0]['status'],'sampled_interpolation_passed')
        self.assertEqual(report['temporal_quality_status'],'needs_review')
        self.assertEqual(report['target_interpolation_status'],'not_evaluated')
        self.assertFalse(report['continuous_time_proven']);self.assertFalse(report['production_authorized'])
        with tempfile.TemporaryDirectory() as root:
            sha=publish_mesh_report(root,'project-component-partitions',report)
            self.assertEqual(read_mesh_report(root,'project-component-partitions',sha),report)
            self.assertEqual(publish_mesh_report(root,'project-component-partitions',report),sha)
        for change in [lambda d:d.update(runtime_status='passed'),
                       lambda d:d['records'][0]['tracks'][0]['qa'].pop(),
                       lambda d:d['records'][0]['tracks'][0].update(new_failed_between_keys=[1])]:
            bad=deepcopy(report);change(bad)
            with self.assertRaises(ValueError):validate(bad,**inputs)

    def test_blocked_source_and_missing_region_cannot_disappear(self):
        from test_ordinary_sleeve import fixture
        from autospine_workbench.asset.planning.ordinary_sleeve_repair import build as repair_build
        from autospine_workbench.resolved_project import canonical_sha256
        source,draft,skeleton=fixture()
        draft['records'][0]['assignments'][2]['role']='unknown'
        source['draft_sha256']=canonical_sha256(draft)
        source['records'].append(dict(layer_id='residual',component_id='none',mesh=None))
        repair=repair_build(source,draft,skeleton);deform=deform_build(repair,source,draft,skeleton)
        report=build(deform,repair=repair,source=source,draft=draft,skeleton=skeleton)
        self.assertEqual(len(report['records']),2)
        self.assertIn('source_region_blocked',report['records'][0]['reason_codes'])
        self.assertEqual(report['records'][1]['tracks'],[])
        self.assertTrue(all(r['status']=='blocked' for r in report['records']))


if __name__=='__main__': unittest.main()
