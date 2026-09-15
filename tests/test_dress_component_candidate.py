from copy import deepcopy
import json
import unittest
from test_character_skirt_candidate import fixture
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.targets.character43.component_mount_candidate import generate as split
from autospine_workbench.targets.character43.skirt_candidate import generate
from autospine_workbench.targets.character43.numeric_reference import read


class DressComponentTests(unittest.TestCase):
    def package(self):
        files=fixture();m=json.loads(files['character-manifest.json'])
        m['layers'][0]['name']='topwear'
        for l in m['layers']:
            for r in l['regions']:r['state']=l['state']
        files['character-manifest.json']=canonical_bytes(m)
        return files

    def test_partition_preserves_motion_and_does_not_claim_binding(self):
        files=self.package();before=deepcopy(files)
        output,report=split(files,'skirt',['root'],partition_only=True)
        self.assertEqual(files,before);self.assertTrue(report['partition_only'])
        layer=json.loads(output['character-manifest.json'])['layers'][0]
        self.assertEqual(layer['state'],'static_reference')
        self.assertTrue(all(r['state']=='static_reference' for r in layer['regions']))
        with self.assertRaisesRegex(ValueError,'preserve_parent'):
            split(files,'skirt',['chest'],partition_only=True)

    def test_dress_component_preserves_unselected_motion_and_pixels(self):
        partitioned,_=split(self.package(),'skirt',['root'],partition_only=True)
        result,report=generate(partitioned,'a'*64,['skirt-component-0000'],waist_driver='candidate-chest-v1',dress_components=True)
        self.assertEqual(report['profile'],'isolated-dress-chest-skirt-v1')
        self.assertTrue(report['geometry_passed']);self.assertEqual(len(report['rows']),1)
        self.assertLess(report['setup_error_px'],1e-6)
        for name,raw in partitioned.items():
            if name.endswith('.png'):self.assertEqual(result[name],raw)
        for a,b in zip(read(partitioned)['animations']['idle'],read(result)['animations']['idle']):
            self.assertEqual(a['vertices']['shirt'],b['vertices']['shirt'])
        self.assertFalse(report['selected'])

    def test_non_dress_and_profile_mismatch_rejected(self):
        files=fixture()
        with self.assertRaisesRegex(ValueError,'selection_unsupported'):
            generate(files,'a'*64,['skirt'],waist_driver='candidate-chest-v1',dress_components=True)
        with self.assertRaisesRegex(ValueError,'profile_invalid'):
            generate(files,'a'*64,['skirt'],dress_components=True)
