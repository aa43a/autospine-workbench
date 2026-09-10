"""Ownership, not project names, selects the versioned target branch."""
from copy import deepcopy
import tempfile
import unittest
from pathlib import Path
from test_ordinary_sleeve import fixture
from autospine_workbench.automation.sleeve_export_dispatch import prepare
from autospine_workbench.automation.sleeve_workflow import summarize
from autospine_workbench.benchmark.mesh_storage import read_mesh_report
from autospine_workbench.resolved_project import canonical_sha256
import json


class SleeveExportDispatchTests(unittest.TestCase):
    def test_ordinary_rows_have_exact_stored_motion_and_preserve_residual(self):
        garment,draft,skeleton=fixture()
        garment['records'].append(dict(layer_id='arm',component_id='residual',mesh=None))
        garment['draft_sha256']=canonical_sha256(draft)
        old=dict(records=[],project_id='fresh')
        original=deepcopy((old,garment,draft,skeleton))
        with tempfile.TemporaryDirectory() as folder:
            rows,schema,selected,meta=prepare(old,garment,draft,skeleton,Path(folder))
            self.assertEqual(schema,'autospine.sleeve-export-report/v2')
            self.assertEqual(len(rows),2)
            self.assertEqual(rows[0]['status'],'candidate_requires_review')
            self.assertEqual(rows[1]['status'],'blocked')
            self.assertEqual(rows[1]['reason_codes'],['ordinary_sleeve_region_unavailable'])
            for key,value in meta.items():
                stored=read_mesh_report(Path(folder),'project-component-partitions',value['motion_source_sha256'])
                self.assertEqual(stored,selected[key])
        self.assertEqual((old,garment,draft,skeleton),original)

    def test_pure_wide_keeps_legacy_records_and_schema(self):
        garment,draft,skeleton=fixture()
        draft['records'][0]['assignments'][0]['role']='hanging_cloth'
        garment['draft_sha256']=canonical_sha256(draft)
        old=dict(records=[dict(layer_id='arm',component_id='c1',reason_codes=['preserved'])])
        with tempfile.TemporaryDirectory() as folder:
            self.assertEqual(prepare(old,garment,draft,skeleton,Path(folder)),(old['records'],None,{},{}))
        garment['draft_sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'draft_mismatch'):
            prepare(old,garment,draft,skeleton,Path('unused'))

    def test_workflow_preserves_explicit_motion_provenance(self):
        row=dict(layer_id='arm',component_id='c1',status='blocked',reason_code='motion_envelope_geometry_failure',
                 motion_profile='ordinary-forearm30-hand30-sine129-v1',motion_source_sha256='a'*64)
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);out=root/'spine/fresh';out.mkdir(parents=True)
            (out/'report.json').write_text(json.dumps(dict(schema='autospine.sleeve-export-report/v2',records=[row])))
            result=summarize(root,'fresh','run-fixture',[])
            self.assertEqual(result['records'][0]['motion_profile'],row['motion_profile'])
            self.assertEqual(result['records'][0]['motion_source_sha256'],row['motion_source_sha256'])
            self.assertIsNone(result['records'][0]['download'])


if __name__=='__main__':unittest.main()
