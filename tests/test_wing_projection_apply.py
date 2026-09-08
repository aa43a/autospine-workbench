import unittest
from copy import deepcopy
from PIL import Image
from tests import test_wing_split_preview as fixtures
from autospine_workbench.benchmark.wing_split_preview import build as split
from autospine_workbench.benchmark.wing_back_order import build as back
from autospine_workbench.benchmark.wing_projection_groups import build as groups,initial
from autospine_workbench.benchmark.wing_projection_apply import build,verify
from autospine_workbench.asset.planning.wing_edge_ownership import decode


class ApplyTests(unittest.TestCase):
    def test_local_remove_with_uncertain_groups_preserves_back_order(self):
        edge,files,draft=fixtures.SplitPreviewTests().fixture()
        source,files=split(edge,files,draft);files.pop('preview-manifest.json');candidate=groups(source,files,edge)
        ordered,files=back(source,files);files.pop('preview-manifest.json')
        selection=initial(candidate);selection['local_strokes']=[dict(mode='remove',radius=1,points=[[0,0]])]
        inputs=(ordered,files,candidate,edge,selection);before=deepcopy(inputs);report,outputs=build(*inputs)
        self.assertEqual(inputs,before);self.assertEqual(report['projection_apply']['removed_visible_pixels'],3)
        self.assertTrue(all(r['action']=='uncertain' for r in report['projection_apply']['choices']))
        for name,raw in files.items():
            if name not in ('editor/images/topwear.png','textures/topwear.png','README.txt','review.html'):self.assertEqual(outputs[name],raw)
        restored=Image.alpha_composite(decode(outputs['editor/images/topwear.png']),decode(outputs['projection/removed-topwear.png']))
        self.assertEqual(restored.tobytes(),decode(files['editor/images/topwear.png']).tobytes())
        self.assertEqual(verify(report,*inputs),report)
        bad=deepcopy(ordered);bad['source_split_preview_sha256']='0'*64
        with self.assertRaises(ValueError):build(bad,files,candidate,edge,selection)
        selection['source_candidate_sha256']='0'*64
        with self.assertRaises(ValueError):build(ordered,files,candidate,edge,selection)
