"""Current images can inform suggestions without overwriting the chosen route."""
from copy import deepcopy
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from tests.test_route_geometry import fixture
from autospine_workbench.automation.project_route import ProjectRoute
from autospine_workbench.automation.project_route_evidence import collect


class ProjectRouteEvidenceTests(unittest.TestCase):
    def test_geometry_suggests_inspection_but_keeps_explicit_ordinary_choice(self):
        project,images=fixture()
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);image=root/'arm.png';image.write_bytes(images['arm'])
            store=SimpleNamespace(state_root=root,get_project=lambda _:project,resolve_asset=lambda *args:image)
            service=ProjectRoute(store)
            value=service.get('fixture')
            self.assertEqual(value['recommendation'],'sleeves')
            self.assertEqual(value['choice'],'undecided')
            self.assertEqual(value['geometry']['project_id'],'fixture')
            service.save('fixture',dict(choice='ordinary',expected_revision=0,expected_resolved_sha256='a'*64))
            value=ProjectRoute(store).get('fixture')
            self.assertEqual(value['choice'],'ordinary')
            self.assertEqual(value['recommendation'],'sleeves')
            self.assertFalse(value['geometry']['production_authorized'])
            project['resolved']['skeleton']['joints'][0]['review_state']='unreviewed'
            self.assertEqual(service.get('fixture')['recommendation'],'undecided')

    def test_failed_image_does_not_infer_sleeve_and_reads_are_bounded(self):
        project,_=fixture();base=project['resolved']['layers'][0]
        project['resolved']['layers']=[dict(deepcopy(base),id=f'arm-{i}') for i in range(20)]
        calls=[]
        def missing(*args):calls.append(args);raise OSError('missing')
        result=collect(SimpleNamespace(resolve_asset=missing),'fixture',project)
        self.assertEqual(len(calls),16)
        self.assertEqual(len(result['records']),20)
        self.assertTrue(all(r['classification']=='insufficient_evidence' for r in result['records']))
        self.assertIn('layer_image_read_failed',result['records'][0]['reason_codes'])
        self.assertIn('route_layer_limit',result['records'][-1]['reason_codes'])


if __name__=='__main__':unittest.main()
