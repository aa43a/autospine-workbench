import unittest
from m4_regional_cloth_runtime import complete_chunks


class CompleteClothChunksTests(unittest.TestCase):
    def test_complete_parent_grid_and_anchor_retained(self):
        times=[i/10000 for i in range(17452)]
        batches=complete_chunks(times)
        self.assertEqual(batches[0]+[t for b in batches[1:] for t in b[1:]],times)
        self.assertTrue(all(b[0]==0 and len(b)<=1024 for b in batches))

    def test_invalid_order_rejected(self):
        with self.assertRaises(ValueError):complete_chunks([0,2,1])
