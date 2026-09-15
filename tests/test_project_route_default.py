from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch
from autospine_workbench.automation.project_route_default import derive
from autospine_workbench.automation.project_route import ProjectRoute


class RouteDefaultTests(TestCase):
    def setUp(self):
        self.project={'resolved':{'sha256':'a'*64,'layers':[
            {'name':'handwear-l','canonical_role':'body.hand'}]}}
        self.geometry=dict(project_id='p',records=[dict(side=side,layer_id=side,
            classification='no_broad_shape_evidence',reason_codes=['narrow_shape_not_sleeveless_proof'])
            for side in ('left','right')])

    def test_default_is_source_bound_and_not_binding_approval(self):
        first=derive(self.project,self.geometry)
        self.assertEqual(first['choice'],'ordinary')
        self.assertFalse(first['binding_approved'])
        self.assertFalse(first['sleeveless_inferred'])
        import json
        from jsonschema import Draft202012Validator
        schema=json.loads((Path(__file__).resolve().parents[1]/'schemas/project-route-default-v1.schema.json').read_bytes())
        Draft202012Validator(schema).validate(first)
        changed=deepcopy(self.geometry);changed['records'][0]['image_sha256']='b'*64
        self.assertNotEqual(first['evidence_sha256'],derive(self.project,changed)['evidence_sha256'])

    def test_broad_missing_unreviewed_and_sleeve_semantics_stay_manual(self):
        for reason in ('arm_joints_unreviewed','alpha_separated_regions_hint','layer_image_missing'):
            changed=deepcopy(self.geometry);changed['records'][0]['reason_codes'].append(reason)
            self.assertIsNone(derive(self.project,changed))
        changed=deepcopy(self.geometry);changed['records'].pop()
        self.assertIsNone(derive(self.project,changed))
        changed=deepcopy(self.geometry);changed['records'][0]['classification']='broad_off_axis_shape'
        self.assertIsNone(derive(self.project,changed))
        self.project['resolved']['layers'][0].update(name='sleeve',bbox={'width':10,'height':10})
        self.assertIsNone(derive(self.project,self.geometry))

    def test_user_override_and_stale_override_never_replaced(self):
        with TemporaryDirectory() as tmp, patch(
                'autospine_workbench.automation.project_route_evidence.collect',return_value=self.geometry):
            service=ProjectRoute(SimpleNamespace(state_root=Path(tmp),get_project=lambda _:self.project))
            value=service.get('p');self.assertEqual(value['choice'],'ordinary')
            self.assertEqual(value['revision'],0)
            value=service.save('p',dict(choice='undecided',expected_resolved_sha256='a'*64,expected_revision=0))
            self.assertEqual(value['choice'],'undecided');self.assertIsNone(value['default_choice'])
            self.project['resolved']['sha256']='b'*64
            self.assertTrue(service.get('p')['stale']);self.assertIsNone(service.get('p')['default_choice'])

    def test_combined_arms_get_preview_route_without_binding_approval(self):
        self.geometry['records']=[dict(side='bilateral',classification='insufficient_evidence',
            reason_codes=['character_side_unknown'])]
        value=derive(self.project,self.geometry)
        self.assertEqual(value['profile'],'combined-arm-preview-first-v1')
        self.assertFalse(value['binding_approved'])
        self.geometry['records'][0]['side']='unknown'
        self.assertIsNone(derive(self.project,self.geometry))
