"""Exact reviewed post-transform exclusions retain every other texture and sample."""
from hashlib import sha256
import json
import unittest
import importlib.util
from test_character_skirt_candidate import fixture
from autospine_workbench.resolved_project import canonical_sha256
from autospine_workbench.targets.character43.final_region_exclusion import apply_batch
from autospine_workbench.targets.character43.numeric_reference import read


@unittest.skipUnless(importlib.util.find_spec('PIL'), 'optional Pillow')
class FinalExclusionTests(unittest.TestCase):
    def test_exact_scope_and_all_unselected_material_preserved(self):
        f=fixture(); m=json.loads(f['character-manifest.json'])
        for layer in m['layers']:
            layer.update(missing_region_ids=[], reason_codes=[])
            for region in layer['regions']: region['state']=layer['state']
        f['character-manifest.json']=json.dumps(m).encode()
        d=dict(schema='autospine.region-exclusion/v1',decision_source='human_confirmation',
            source_bundle_sha256=canonical_sha256({n:sha256(b).hexdigest() for n,b in f.items()}),
            manifest_sha256=sha256(f['character-manifest.json']).hexdigest(),
            layer_id='skirt',region_id='skirt',image_sha256=sha256(f['images/skirt.png']).hexdigest())
        output=apply_batch(f,[d])
        self.assertEqual(output['images/shirt.png'],f['images/shirt.png'])
        self.assertEqual(output['images/skirt.png'],f['images/skirt.png'])
        for a,b in zip(read(f)['animations']['idle'],read(output)['animations']['idle']):
            self.assertEqual(a['vertices']['shirt'],b['vertices']['shirt'])
            self.assertNotIn('skirt',b['vertices'])
        with self.assertRaisesRegex(ValueError,'duplicate'): apply_batch(f,[d,d])
        with self.assertRaisesRegex(ValueError,'source'): apply_batch(f,[dict(d,source_bundle_sha256='0'*64)])
        with self.assertRaisesRegex(ValueError,'stale'): apply_batch(f,[dict(d,image_sha256='0'*64)])
