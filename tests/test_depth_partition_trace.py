from copy import deepcopy
import unittest
from test_depth_region_partition import source
from autospine_workbench.targets.character43.depth_partition_trace import labels
from autospine_workbench.targets.character43.depth_region_partition import build
from autospine_workbench.targets.character43.affine_pose import sample


class TriangleTraceTests(unittest.TestCase):
    def test_distinct_crossings_preserve_geometry_texture_and_order(self):
        rows=[dict(body='body',time=0,status='requires_partition_or_more_depth',
                   triangles={0:{'front':5},1:{'back':6},2:{'front':5}}),
              dict(body='body',time=.5,status='requires_partition_or_more_depth',
                   triangles={0:{'back':4},1:{'front':4},2:{'back':4}})]
        names,report=labels(3,rows)
        self.assertEqual(names[0],names[2]);self.assertNotEqual(names[0],names[1])
        self.assertEqual(set(report['groups'].values()),{'FB','BF'})
        doc,_=source();original=deepcopy(doc)
        candidate,partition=build(doc,['a'],triangle_labels={'a':names})
        self.assertEqual([t for r in partition['regions'] for t in r['triangles']],[0,1,2])
        for time in [0,.25,.5,.75,1]:
            before=sample(doc,'test',time)[0];after=sample(candidate,'test',time)[0]
            for region in partition['regions']:self.assertEqual(before['a'],after[region['slot']])
        self.assertEqual(doc,original)

    def test_partial_failure_and_ambiguous_pixels_are_not_classified_front(self):
        rows=[dict(body='b',time=0,status='unmeasured',triangles={0:{'front':3}}),
              dict(body='b',time=1,status='requires_partition_or_more_depth',
                   triangles={0:{'front':4,'ambiguous':1},1:{'back':2,'front':1},2:{'unknown':1}})]
        names,report=labels(3,rows)
        self.assertEqual([report['groups'][n] for n in names],['UA','UM','UU'])
        with self.assertRaisesRegex(ValueError,'trace_time'):labels(3,rows+rows)
        doc,_=source()
        with self.assertRaisesRegex(ValueError,'label_inventory'):build(doc,['a'],triangle_labels={'a':['F']})


if __name__=='__main__':unittest.main()
