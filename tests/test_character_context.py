import unittest
from unittest.mock import patch
from autospine_workbench.benchmark.character_context_view import cards


class CharacterContextTests(unittest.TestCase):
    def fixture(self):
        source={'layers':[{'layer_id':'back','bbox':[0,0,4,4]},{'layer_id':'leg','bbox':[0,0,4,4]},{'layer_id':'front','bbox':[0,0,4,4]}]}
        atlas={'layers':[{'layer_id':'leg','partitions':[{'id':'leg-left'}]}]}
        attachment={'width':4,'height':4,'uvs':[0,0,1,0,0,1],'triangles':[0,1,2]}
        doc={'skins':[{'attachments':{'leg-left':{'leg-left':attachment}}}]}
        return source,atlas,doc,{'back':b'back','front':b'front'},{'leg-left':b'region'}

    def test_source_order_replacement_and_y_reflection(self):
        with patch('autospine_workbench.benchmark.character_context_view.world',return_value={'leg-left':[[0,-1],[4,-1],[0,-4]]}):
            scene=cards(*self.fixture())
        self.assertEqual([c['name'] for c in scene],['back','leg-left','front'])
        self.assertEqual([c['kind'] for c in scene],['fixed_source_context','animated_candidate','fixed_source_context'])
        self.assertEqual(scene[1]['poses'][0],[[0,1],[4,1],[0,4]])
        self.assertEqual(len(scene[1]['poses']),61)

    def test_missing_and_unrelated_partition_rejected(self):
        args=self.fixture();args[1]['layers'][0]['partitions'][0]['id']='unknown'
        with self.assertRaisesRegex(ValueError,'partition_inventory'):cards(*args)
        args=self.fixture();args[1]['layers'][0]['layer_id']='other'
        with self.assertRaisesRegex(ValueError,'source_layers'):cards(*args)
