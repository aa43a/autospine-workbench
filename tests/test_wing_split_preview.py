"""Explicit split choices preserve retained pixels, other files and rollback data."""
import json
from copy import deepcopy
from pathlib import Path
import unittest
from PIL import Image
from tests import test_wing_spine_preview as fixtures
from autospine_workbench.benchmark.wing_spine_preview import build as hinge
from autospine_workbench.benchmark.wing_edge_preview import build as edge
from autospine_workbench.benchmark.wing_split_draft import initial,rasterize
from autospine_workbench.benchmark.wing_split_preview import build,verify
from autospine_workbench.asset.planning.wing_edge_ownership import decode


class SplitPreviewTests(unittest.TestCase):
    def fixture(self):
        base,files=hinge(*fixtures.WingSpineTests().fixture());files.pop('preview-manifest.json')
        source,files=edge(base,files);files.pop('preview-manifest.json')
        return source,files,initial(source)

    def test_reversible_mask_and_retained_pixels(self):
        source,files,draft=self.fixture();draft['strokes']=[dict(mode='remove',radius=2,points=[[0,0]]),dict(mode='keep',radius=1,points=[[0,0]])]
        before=deepcopy((source,files,draft));report,outputs=build(source,files,draft)
        self.assertEqual((source,files,draft),before)
        original=decode(files['editor/images/topwear.png']);remaining=decode(outputs['editor/images/topwear.png']);removed=decode(outputs['split/removed-topwear.png'])
        self.assertEqual(Image.alpha_composite(remaining,removed).tobytes(),original.tobytes())
        mask=rasterize(source,draft)
        for i,value in enumerate(mask):
            point=(i%4,i//4)
            self.assertEqual(remaining.getpixel(point),(0,0,0,0) if value==1 else original.getpixel(point))
        for name,raw in files.items():
            if name not in ('editor/images/topwear.png','textures/topwear.png','README.txt','review.html'):
                self.assertEqual(outputs[name],raw)
        self.assertEqual(report['split_counts']['removed_visible_pixels'],3)
        self.assertEqual(verify(report,source,files,draft),report)
        import jsonschema
        jsonschema.validate(report,json.loads(Path('schemas/wing-split-preview-v1.schema.json').read_text()))
        bad=deepcopy(report);bad['ghosting_resolved']=True
        with self.assertRaises(ValueError):verify(bad,source,files,draft)

    def test_empty_or_erase_does_not_remove_visible_pixels(self):
        source,files,draft=self.fixture();draft['strokes']=[dict(mode='erase',radius=3,points=[[0,0]])]
        report,outputs=build(source,files,draft)
        self.assertEqual(report['split_counts']['removed_visible_pixels'],0)
        self.assertEqual(decode(outputs['editor/images/topwear.png']).tobytes(),decode(files['editor/images/topwear.png']).tobytes())
        files['editor/images/topwear.png']=b'changed'
        with self.assertRaises(ValueError):build(source,files,draft)
