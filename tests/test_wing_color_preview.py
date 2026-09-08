from copy import deepcopy
import json
from pathlib import Path
import unittest
from tests import test_wing_split_preview as fixtures
from autospine_workbench.benchmark.wing_split_preview import build as split
from autospine_workbench.benchmark.wing_back_order import build as back
from autospine_workbench.benchmark.wing_projection_groups import build as groups,initial
from autospine_workbench.benchmark.wing_projection_apply import build as clean
from autospine_workbench.benchmark.wing_color_preview import build,verify


class BundleTests(unittest.TestCase):
    def test_identity_replay_and_unchanged_other_assets(self):
        edge,files,draft=fixtures.SplitPreviewTests().fixture()
        source,files=split(edge,files,draft);files.pop('preview-manifest.json');candidate=groups(source,files,edge)
        source,files=back(source,files);files.pop('preview-manifest.json');draft=initial(candidate)
        draft['local_strokes']=[dict(mode='remove',radius=1,points=[[0,0]])]
        source,files=clean(source,files,candidate,edge,draft);files.pop('preview-manifest.json')
        report,outputs=build(source,files)
        for name,raw in files.items():
            if name not in ('README.txt','review.html') and not name.startswith(('editor/images/wing-c','textures/wing-c')):self.assertEqual(outputs[name],raw)
        self.assertEqual(verify(report,source,files),report)
        import jsonschema
        jsonschema.validate(report,json.loads(Path('schemas/wing-color-preview-v1.schema.json').read_text()))
        bad=deepcopy(report);bad['topwear_unchanged']=False
        with self.assertRaises(ValueError):verify(bad,source,files)
        files['projection/removed-topwear.png']=b'changed'
        with self.assertRaises(ValueError):build(source,files)
