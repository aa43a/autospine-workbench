import unittest
from autospine_workbench.targets.spine43.seam_arcs import local_arcs,ordered_paths
from autospine_workbench.targets.spine43.seam_arc_validation import validate


def record(edges,n=100,status='closed_contour'):
    return {'curves':[{'edge_pixels':[[0,0]]*n,'status':status}],
            'anchors':[{'options':[{'curve':0,'edge':e}]} for e in edges]}


def rows(values):
    return [[{'d':i,'f':f,'cost':0.}] for i,f in enumerate(values)]


class SeamArcsTests(unittest.TestCase):
    def test_wrap_does_not_take_long_way(self):
        arcs=local_arcs(record([98,1,2]))
        self.assertEqual(arcs[0]['edges'],[98,99,0,1,2])
        self.assertEqual(arcs[0]['inserted_edges'],2)

    def test_split_large_unsupported_interval(self):
        self.assertEqual([a['edges'] for a in local_arcs(record([2,4,40,42]))],[[40,41,42],[2,3,4]])

    def test_single_and_whole_contour_not_admitted(self):
        self.assertEqual(local_arcs(record([2]))[0]['status'],'single_edge')
        self.assertEqual(local_arcs(record([0,2,4,6],8))[0]['status'],'whole_contour_unsupported')

    def test_ambiguous_endpoint_never_wraps(self):
        arcs=local_arcs(record([98,1,2],status='ambiguous_corner'))
        self.assertEqual(len(arcs),2)

    def test_reversed_order_and_plateaus(self):
        self.assertEqual(ordered_paths(rows([3,2,1]))[0][1],-1)
        self.assertTrue(ordered_paths(rows([1,1,2])))
        self.assertFalse(ordered_paths(rows([1,3,2])))

    def test_global_choice_can_avoid_local_minimum(self):
        candidates=rows([0,1,2])
        candidates[1]=[{'d':1,'f':4,'cost':0.},{'d':1,'f':1,'cost':1.}]
        best=ordered_paths(candidates)[0]
        self.assertEqual(best[0],1.);self.assertEqual([o['f'] for o in best[2]],[0,1,2])

    def test_two_equal_cost_paths_preserve_ambiguity(self):
        candidates=rows([0,1,3]);candidates[1].append({'d':1,'f':2,'cost':0.})
        paths=ordered_paths(candidates)
        self.assertEqual(len(paths),2);self.assertEqual(paths[0][0],paths[1][0])

    def test_source_correspondences_cannot_disappear_or_duplicate(self):
        relation={'source_pair_count':2,'groups':[],'blocked_pairs':[{'pair':0},{'pair':1}]}
        report={'schema':'autospine.seam-arc-pairs/v1','authority':'none','production_authorized':False,
                'status':'needs_review','analysis':{'relations':[relation]}}
        self.assertIs(validate(report),report)
        relation['blocked_pairs'].pop()
        with self.assertRaisesRegex(ValueError,'arc_source_pair_coverage'):validate(report)
        relation['blocked_pairs'].append({'pair':0})
        with self.assertRaisesRegex(ValueError,'arc_source_pair_coverage'):validate(report)
