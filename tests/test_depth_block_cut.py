import unittest
from autospine_workbench.targets.character43.depth_block_cut import solve_blocks,energy


class BlockCutTests(unittest.TestCase):
    def test_boundary_costs_converge_without_increasing_global_energy(self):
        unary=[[40,0]]+[[1,0] for _ in range(4)]+[[40,0]]
        edges=[(i,i+1,8) for i in range(5)];initial=[0,1,0,1,0,1]
        result=solve_blocks(unary,edges,initial,block_size=2)
        self.assertEqual(result['status'],'locally_stable')
        self.assertEqual(result['labels'],[1]*6)
        self.assertLessEqual(result['energy'],energy(unary,edges,initial))
        self.assertEqual(initial,[0,1,0,1,0,1])

    def test_unfinished_sweep_keeps_original_labels(self):
        result=solve_blocks([[10,0],[10,0]],[(0,1,8)],[0,0],block_size=1,sweeps=1)
        self.assertEqual(result['status'],'held_iteration_limit')
        self.assertEqual(result['labels'],[0,0])
