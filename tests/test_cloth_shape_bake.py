from copy import deepcopy
import json
import unittest
from autospine_workbench.targets.character43.cloth_shape_bake import bake
from autospine_workbench.targets.character43.affine_pose import sample


class ClothBakeTests(unittest.TestCase):
    def test_existing_deform_and_fixed_vertices_survive_bake(self):
        vertices = []
        for i, (x, y) in enumerate(((0, 0), (1, 0), (1, 1), (0, 1))):
            vertices += [1, int(i > 1), x, y, 1]
        doc = dict(bones=[dict(name='forearm_l', x=0, y=0, rotation=0),
            dict(name='cloth-fabric', parent='forearm_l', x=0, y=0, rotation=0),
            dict(name='hand_l', parent='forearm_l', x=0, y=0, rotation=0)],
            skins=[dict(attachments={'fabric': {'fabric': dict(vertices=vertices, triangles=[0, 1, 2, 0, 2, 3])}})],
            animations={'wave-left': dict(bones={'forearm_l': {'rotate': [
                dict(time=0, value=0), dict(time=1, value=20), dict(time=2, value=0)]}},
                attachments={'default': {'fabric': {'fabric': {'deform': [
                    dict(time=0, vertices=[0.]*8), dict(time=1, vertices=[.05, 0.]*4),
                    dict(time=2, vertices=[0.]*8)]}}}})})
        original = deepcopy(doc)
        files = bake(doc, 'wave-left', 'cloth-fabric', samples=3)
        result = json.loads(files['skeleton.json'])
        self.assertEqual(doc, original)
        for time in (0, .5, 1, 1.5, 2):
            before = sample(doc, 'wave-left', time)[0]['fabric']
            after = sample(result, 'wave-left', time)[0]['fabric']
            for a, b in zip(before[:2], after[:2]):
                for x, y in zip(a, b): self.assertAlmostEqual(x, y, places=10)
        self.assertEqual(result['animations']['wave-left']['bones'], doc['animations']['wave-left']['bones'])
        self.assertFalse(json.loads(files['cloth-shape.json'])['selected'])
        self.assertEqual(json.loads(files['cloth-shape.json'])['dense_sample_count'], 1025)
