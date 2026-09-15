import json
from hashlib import sha256
from copy import deepcopy
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from tests.test_character_skirt_candidate import fixture
from autospine_workbench.automation.character_skirt_trial import apply_selected, validate
from autospine_workbench.automation.character_dress_trial import PROFILE, prepare
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.resolved_project import canonical_sha256


def source():
    files = fixture()
    m = json.loads(files['character-manifest.json'])
    m['layers'][0]['name'] = 'topwear-front'
    for layer in m['layers']:
        for region in layer['regions']: region['state'] = layer['state']
    files['character-manifest.json'] = canonical_bytes(m)
    files['motion-evidence.json'] = b'{"source":"unchanged"}'
    return files


class DressRecipeTests(unittest.TestCase):
    def test_workbench_dispatch_preserves_reviewed_layers_and_evidence(self):
        files = source(); before = deepcopy(files); saved = {'a'*64: files}
        def publish(output):
            digest = canonical_sha256({n: sha256(b).hexdigest() for n,b in output.items()})
            saved[digest] = output
            return digest
        manager = SimpleNamespace(application=SimpleNamespace(store=SimpleNamespace(read=saved.__getitem__, publish=publish)))
        validate(PROFILE)
        result = apply_selected(manager, {'skirt_profile': PROFILE}, {'artifact_sha256':'a'*64})
        output = saved[result['artifact_sha256']]
        self.assertEqual(files, before)
        self.assertEqual(result['skirt_trial']['layer_ids'], ['skirt-component-0000'])
        self.assertTrue(result['skirt_trial']['geometry_passed'])
        self.assertEqual(output['motion-evidence.json'], files['motion-evidence.json'])
        self.assertEqual(result['manifest']['layers'][1], json.loads(files['character-manifest.json'])['layers'][1])
        self.assertFalse(result['skirt_trial']['selected'])
        self.assertEqual(result['manifest']['layers'][0]['binding_decision'], {'action':'pending'})

    def test_missing_support_keeps_source_topology_and_records_exception(self):
        files = source(); before = deepcopy(files)
        with patch('autospine_workbench.automation.character_dress_trial.propose', side_effect=ValueError('skirt_dress_chest_support_missing')):
            output, selected, blocked = prepare(files)
        self.assertFalse(selected)
        self.assertEqual(output['skeleton.json'], files['skeleton.json'])
        self.assertEqual(files,before)
        self.assertEqual(blocked[0]['reason_code'],'skirt_dress_component_not_found')
        self.assertIn(blocked[0]['reason_code'],json.loads(output['character-manifest.json'])['layers'][0]['reason_codes'])

    def test_residual_default_precedes_partition_and_keeps_request(self):
        files=source();saved={'a'*64:files};order=[]
        store=SimpleNamespace(read=saved.__getitem__,publish=lambda f:saved.setdefault('b'*64,f) and 'b'*64)
        manager=SimpleNamespace(application=SimpleNamespace(store=store))
        request={'skirt_profile':PROFILE,'residual_auto_profile':'preserve'}
        with patch('autospine_workbench.automation.character_residual_defaults.apply',side_effect=lambda m,r,v:order.append(('residual',dict(r))) or v), \
             patch('autospine_workbench.automation.character_dress_trial.prepare',side_effect=lambda f:order.append(('partition',None)) or (f,[],[])):
            apply_selected(manager,request,{'artifact_sha256':'a'*64})
        self.assertEqual([r[0] for r in order],['residual','partition'])
        self.assertEqual(order[0][1],request)
