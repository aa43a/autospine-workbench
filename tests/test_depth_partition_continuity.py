from copy import deepcopy
import unittest
from test_motion_depth_overlap import fixture
from autospine_workbench.targets.character43.depth_region_partition import build
from autospine_workbench.targets.character43.depth_partition_continuity import analyze,boundaries


def setup(transparent=False):
    doc,files=fixture(transparent);doc['animations']={'external-motion':{}}
    split,receipt=build(doc,['a'],triangle_labels={'a':['front','unknown']})
    names=[r['slot'] for r in receipt['regions']]+['b']
    order=[names[1],'b',names[0]]
    split['animations']['external-motion']['drawOrder']=[dict(time=0,offsets=[
        dict(slot=n,offset=order.index(n)-i) for i,n in enumerate(names)])]
    return doc,split,receipt,files


class VisibilityContinuityTests(unittest.TestCase):
    def test_detects_opaque_cut_on_shared_source_edge(self):
        doc,candidate,receipt,files=setup()
        result=analyze(doc,candidate,receipt,files,{'a':['b']},[0,.5])
        self.assertEqual(result['status'],'needs_review');self.assertEqual(len(result['records']),2)
        self.assertEqual(result['records'][0]['edge'],[0,2])
        self.assertGreater(result['records'][0]['opaque_cut_points'],0)
        self.assertFalse(result['selected'])

    def test_transparent_body_and_unchanged_order_are_not_reported(self):
        doc,candidate,receipt,files=setup(True)
        self.assertEqual(analyze(doc,candidate,receipt,files,{'a':['b']},[0])['status'],'no_sampled_cut')
        doc,candidate,receipt,files=setup()
        candidate['animations']['external-motion'].pop('drawOrder')
        self.assertEqual(analyze(doc,candidate,receipt,files,{'a':['b']},[0])['records'],[])

    def test_budget_and_duplicate_ownership_cannot_pass(self):
        doc,candidate,receipt,files=setup()
        self.assertEqual(analyze(doc,candidate,receipt,files,{'a':['b']},[0],work_limit=1)['status'],'incomplete')
        receipt['regions'].append(deepcopy(receipt['regions'][0]))
        with self.assertRaisesRegex(ValueError,'duplicate_triangle'):boundaries(doc,receipt)

    def test_coherent_front_move_and_boundary_outside_body_are_not_rejected(self):
        doc,candidate,receipt,files=setup()
        names=[s['name'] for s in candidate['slots']];desired=['b']+names[:-1]
        candidate['animations']['external-motion']['drawOrder'][0]['offsets']=[
            dict(slot=n,offset=desired.index(n)-i) for i,n in enumerate(names)]
        self.assertEqual(analyze(doc,candidate,receipt,files,{'a':['b']},[0])['status'],'no_sampled_cut')
        doc,candidate,receipt,files=setup()
        # The occluder covers only one side of the common diagonal.
        doc['skins'][0]['attachments']['b']['b']['triangles']=[0,1,2]
        self.assertEqual(analyze(doc,candidate,receipt,files,{'a':['b']},[0])['status'],'no_sampled_cut')


if __name__=='__main__':unittest.main()
