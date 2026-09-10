"""New lifecycle contracts validate actual service-produced metadata."""
from contextlib import contextmanager
from copy import deepcopy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from jsonschema import Draft202012Validator, ValidationError

from test_sleeve_onboarding_source import inputs as fixture
from autospine_workbench.automation.asset_library import AssetLibrary
from autospine_workbench.automation.project_route import ProjectRoute
from autospine_workbench.automation.sleeve_onboarding import SleeveOnboarding
from autospine_workbench.automation.storage_io import read_document


def validator(name):
    schema = json.loads((Path(__file__).resolve().parents[1] / 'schemas' / (name+'.schema.json')).read_text())
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


class AssetOnboardingSchemaTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.project = {'id': 'sample', 'name': 'Name', 'revision': 0,
                        'resolved': {'sha256': 'a'*64, 'layers': []}}
        self.store = SimpleNamespace(state_root=self.root, get_project=lambda _: self.project)

    def test_asset_lifecycle_service_documents_and_unknown_field_rejection(self):
        service = AssetLibrary(self.store); check = validator('asset-library-entry-v1')
        cases = [('rename', {'name': '角色'}), ('archive', {}), ('trash', {}), ('restore', {}), ('restore', {})]
        for revision, (action, extra) in enumerate(cases):
            value = service.change('sample', dict(action=action, expected_revision=revision, **extra))
            check.validate(value)
        for mutation in [lambda d: d.update(name='\0'), lambda d: d.update(name='   '),
                         lambda d: d.update(revision=True), lambda d: d.update(production_authorized=True)]:
            bad = deepcopy(value); mutation(bad)
            with self.assertRaises(ValidationError): check.validate(bad)

    def test_actual_route_choices_and_source_address_shape(self):
        service = ProjectRoute(self.store); check = validator('project-route-choice-v1')
        for revision, choice in enumerate(('ordinary', 'sleeves', 'undecided')):
            service.save('sample', dict(choice=choice, expected_revision=revision, expected_resolved_sha256='a'*64))
            path = service.root / 'sample' / f'revision-{revision+1:012d}.json'
            value = read_document(path); check.validate(value)
        for key, changed in [('choice', 'approved'), ('source_sha256', '../source'), ('authority', 'approved')]:
            bad = dict(value, **{key: changed})
            with self.assertRaises(ValidationError): check.validate(bad)

    def test_onboarding_prepare_save_documents_require_complete_address_inventory(self):
        data = fixture(); data.assert_current = lambda: None
        check = validator('sleeve-onboarding-v1')
        address_names = check.schema['properties']['input_addresses']['required']
        data.source_addresses = {key: 'a'*64 for key in address_names}

        @contextmanager
        def current(*args): yield data

        service = SleeveOnboarding(self.store)
        with patch('autospine_workbench.automation.sleeve_onboarding.load_inputs', current):
            service.prepare('sample', 'a'*64)
            value, _, _, draft = service.read_current('sample')
            check.validate(value)
            service.save('sample', dict(expected_revision=1, expected_resolved_sha256='a'*64, draft=draft))
            value = service.read_current('sample')[0]; check.validate(value)
        for mutation in [lambda d: d['input_addresses'].pop('animated_registration_sha256'),
                         lambda d: d.update(saved=1), lambda d: d.update(closure_sha256='invalid'),
                         lambda d: d.update(extra=True)]:
            bad = deepcopy(value); mutation(bad)
            with self.assertRaises(ValidationError): check.validate(bad)


if __name__ == '__main__': unittest.main()
