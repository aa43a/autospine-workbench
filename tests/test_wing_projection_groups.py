from copy import deepcopy
import json
from pathlib import Path
import unittest
from tests import test_wing_split_preview as fixtures
from autospine_workbench.benchmark.wing_split_preview import build as split
from autospine_workbench.benchmark.wing_projection_groups import build,initial,validate,effective_mask


class ProjectionTests(unittest.TestCase):
    def fixture(self):
        edge,files,draft=fixtures.SplitPreviewTests().fixture()
        draft['strokes']=[dict(mode='remove',radius=1,points=[[0,0]])]
        source,files=split(edge,files,draft);files.pop('preview-manifest.json')
        candidate=build(source,files,edge)
        return candidate,edge,initial(candidate)

    def test_projection_excludes_previous_removed_pixels(self):
        c,e,d=self.fixture();self.assertEqual(c['groups'][0]['pixel_count'],13)
        self.assertFalse(any(effective_mask(c,e,d)))
        d['choices'][0]['action']='remove';mask=effective_mask(c,e,d)
        self.assertEqual(sum(mask),13);self.assertEqual(mask[0],0)
        d['local_strokes']=[dict(mode='keep',radius=1,points=[[3,3]])]
        self.assertEqual(sum(effective_mask(c,e,d)),10)

    def test_choices_source_and_veto(self):
        c,e,d=self.fixture();before=deepcopy(d);self.assertEqual(validate(c,e,d),d);self.assertEqual(before,d)
        import jsonschema
        jsonschema.validate(c,json.loads(Path('schemas/wing-projection-groups-v1.schema.json').read_text()))
        schema=json.loads(Path('schemas/wing-projection-draft-v1.schema.json').read_text())
        schema['properties']['local_strokes']=json.loads(Path('schemas/wing-split-draft-v1.schema.json').read_text())['properties']['strokes']
        jsonschema.validate(d,schema)
        for change in [lambda d:d.update(production_authorized=0),lambda d:d['choices'][0].update(action='approved'),lambda d:d['choices'].pop(),lambda d:d.update(source_candidate_sha256='0'*64)]:
            bad=deepcopy(d);change(bad)
            with self.assertRaises(ValueError):validate(c,e,bad)
        c['groups'].append(dict(c['groups'][0],id='other'));d=initial(c);d['choices'][0]['action']='remove'
        self.assertEqual(sum(effective_mask(c,e,d)),0)
