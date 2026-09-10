import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch
from autospine_workbench.asset.planning.sleeve_regions import template
from autospine_workbench.resolved_project import canonical_sha256

spec=importlib.util.spec_from_file_location('retained_sleeve',
    Path(__file__).resolve().parents[1]/'tools/solve-retained-sleeve.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


class RetainedDomainTests(unittest.TestCase):
    def fixture(self,role):
        mesh=dict(layer_id='layer',component_id='component',vertices_xy=[[0,0],[2,0],[0,2]],
                  triangles=[[0,1,2]],suggestions=[dict(triangle_id=0,suggested_role='unknown')])
        candidate=dict(project_id='fixture',skeleton_sha256='skeleton',records=[mesh])
        draft=template(candidate);draft['records'][0]['assignments'][0].update(role=role,origin='manual_edit')
        storage={canonical_sha256(candidate):candidate,'draft':draft,'weights':dict(draft_sha256='draft')}
        source=dict(project_id='fixture',skeleton_sha256='skeleton',source_sha256='weights',records=[
            dict(layer_id='layer',component_id='component',helper={},setup_vertices=mesh['vertices_xy'],triangles=mesh['triangles'])])
        return source,storage

    def test_exact_draft_preserves_unknown_protection(self):
        for role,free in [('unknown',[]),('hand',[]),('hanging_cloth',[0,1,2])]:
            source,storage=self.fixture(role)
            with patch.object(module,'read_mesh_report',side_effect=lambda state,bucket,sha:storage[sha]):
                domains=module.reviewed_domains(None,source)
            self.assertEqual(domains['layer','component']['free_vertices'],free)

    def test_wrong_geometry_and_skeleton_fail_closed(self):
        for field,value,reason in [('setup_vertices',[[0,0],[3,0],[0,2]],'geometry'),('skeleton_sha256','other','identity')]:
            source,storage=self.fixture('hanging_cloth')
            if field=='setup_vertices':source['records'][0][field]=value
            else:source[field]=value
            with patch.object(module,'read_mesh_report',side_effect=lambda state,bucket,sha:storage[sha]):
                with self.assertRaisesRegex(ValueError,reason):module.reviewed_domains(None,source)
