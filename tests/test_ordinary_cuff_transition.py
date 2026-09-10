"""Absolute cuff smoothing preserves protected domains and does not depend on scale."""
from copy import deepcopy
import unittest
from autospine_workbench.asset.planning.ordinary_cuff_transition import reweight


def fixture():
    bones = ['upperarm_l', 'forearm_l', 'hand_l']
    # Cuff joins a hand triangle and a sleeve triangle. Vertex 8 is isolated.
    triangles = [[0,1,2], [1,2,3], [2,3,4], [3,4,5], [5,6,7]]
    roles = ['hand','cuff','cuff','sleeve','unknown']
    points = [[float(i),float(i % 2)] for i in range(9)]
    weights = [[dict(bone_id=b,weight=w,local_xy=p[:]) for b,w in zip(bones,[.2,.8,0.])] for p in points]
    for i in (0,1,2):
        for entry,value in zip(weights[i],[.1,.3,.6]): entry['weight']=value
    # Unknown and isolated weights must remain exact despite being nonzero.
    for i in (5,8):
        for entry,value in zip(weights[i],[.1,.2,.7]): entry['weight']=value
    return dict(bone_ids=bones,vertices_xy=points,triangles=triangles,weights=weights), [
        dict(triangle_id=i,role=r) for i,r in enumerate(roles)]


class OrdinaryCuffTransitionTests(unittest.TestCase):
    def test_absolute_influence_can_grow_from_zero_and_preserves_inputs(self):
        mesh, labels = fixture(); before = deepcopy((mesh,labels))
        result,evidence = reweight(mesh,labels)
        self.assertEqual((mesh,labels),before)
        self.assertEqual((result,evidence),reweight(mesh,labels))
        self.assertEqual(evidence['iterations'],128)
        self.assertGreater(result['weights'][3][2]['weight'],0.)
        self.assertEqual(result['triangles'],mesh['triangles'])
        self.assertEqual(result['vertices_xy'],mesh['vertices_xy'])
        for i,row in enumerate(result['weights']):
            self.assertAlmostEqual(sum(e['weight'] for e in row),1.)
            self.assertEqual([e['bone_id'] for e in row],mesh['bone_ids'])
            self.assertEqual([e['local_xy'] for e in row],[e['local_xy'] for e in mesh['weights'][i]])
        # Explicit hand is pinned to 0.6, never promoted to rigid hand.
        for i in (0,1,2,5,6,7,8): self.assertEqual(result['weights'][i],mesh['weights'][i])
        self.assertAlmostEqual(result['weights'][3][0]['weight']/result['weights'][3][1]['weight'],.25)

    def test_pure_sleeve_hand_zero_and_forearm_fallback(self):
        mesh,labels=fixture()
        labels=[dict(triangle_id=i,role='sleeve') for i in range(len(labels))]
        for entry,value in zip(mesh['weights'][3],[0.,0.,1.]): entry['weight']=value
        result,evidence=reweight(mesh,labels)
        self.assertEqual([e['weight'] for e in result['weights'][3]],[0.,1.,0.])
        self.assertTrue(all(result['weights'][i][2]['weight']==0. for i in range(8)))
        self.assertEqual(result['weights'][8],mesh['weights'][8])

    def test_translation_scaling_has_no_influence_on_solution(self):
        mesh,labels=fixture(); moved=deepcopy(mesh)
        moved['vertices_xy']=[[x*7+100,y*7-50] for x,y in mesh['vertices_xy']]
        for row in moved['weights']:
            for entry in row: entry['local_xy']=[p*7 for p in entry['local_xy']]
        a,ea=reweight(mesh,labels); b,eb=reweight(moved,labels)
        self.assertEqual(ea,eb)
        self.assertEqual([[e['weight'] for e in row] for row in a['weights']],
                         [[e['weight'] for e in row] for row in b['weights']])

    def test_invalid_inventory_and_weights_are_rejected(self):
        mesh,labels=fixture()
        with self.assertRaises(ValueError): reweight(mesh,labels[:-1])
        labels[0]['triangle_id']=2
        with self.assertRaises(ValueError): reweight(mesh,labels)
        mesh,labels=fixture(); mesh['weights'][0][0]['weight']=float('nan')
        with self.assertRaises(ValueError): reweight(mesh,labels)


if __name__=='__main__': unittest.main()
