import itertools
import random
import unittest
from autospine_workbench.targets.character43.depth_binary_cut import solve
from autospine_workbench.targets.character43.depth_coherent_frame import infer


class BinaryCutTests(unittest.TestCase):
    def test_matches_exhaustive_energy_with_hard_evidence(self):
        rng=random.Random(79)
        for n in range(1,7):
            for _ in range(15):
                unary=[(rng.randrange(7),rng.randrange(7)) for i in range(n)]
                edges=[(a,b,rng.randrange(9)) for a in range(n) for b in range(a+1,n) if rng.random()<.4]
                fixed={i:rng.randrange(2) for i in range(n) if rng.random()<.2}
                energies=[sum(unary[i][v] for i,v in enumerate(labels))+sum(w for a,b,w in edges if labels[a]!=labels[b])
                    for labels in itertools.product((0,1),repeat=n) if all(labels[i]==v for i,v in fixed.items())]
                result=solve(unary,edges,fixed)
                self.assertEqual(result['energy'],min(energies));self.assertEqual(result,solve(unary,edges,fixed))

    def test_ambiguous_neighbor_is_inferred_but_unknown_is_not(self):
        mesh={'triangles':[0,1,2,0,2,3]}
        row=dict(status='requires_partition_or_more_depth',triangles={0:{'front':4},1:{'ambiguous':4}})
        result=infer(mesh,row,[0,0],False)
        self.assertEqual(result['labels'],[1,1]);self.assertEqual(result['inferred_triangles'],[1])
        self.assertEqual(result['observed_states'],'FA')
        row['triangles'][1]={'unknown':4}
        result=infer(mesh,row,[1,1],False)
        self.assertEqual(result['labels'],[1,0]);self.assertEqual(result['unresolved_triangles'],[1])

    def test_unmeasured_rows_cannot_reuse_partial_front_counts(self):
        mesh={'triangles':[0,1,2,0,2,3]}
        result=infer(mesh,dict(status='unmeasured',triangles={0:{'front':10}}),[1,1],False)
        self.assertEqual(result['labels'],[0,0]);self.assertEqual(result['observed_states'],'UU')
        self.assertEqual(result['inferred_triangles'],[])

    def test_observed_conflict_is_preserved_even_with_large_adjacency_cost(self):
        result=solve([(0,0),(0,0)],[(0,1,1000000)],{0:0,1:1})
        self.assertEqual(result['labels'],[0,1]);self.assertEqual(result['energy'],1000000)
        with self.assertRaisesRegex(ValueError,'resource_limit'):solve([],[])
        with self.assertRaisesRegex(ValueError,'edge'):solve([(0,1)],[(0,1,1)])


if __name__=='__main__':unittest.main()
