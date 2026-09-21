from copy import deepcopy
import unittest
from test_depth_region_partition import source
from autospine_workbench.targets.character43.depth_region_partition import build
from autospine_workbench.targets.character43.depth_partition_compact import compact
from autospine_workbench.targets.character43.affine_pose import sample


class PartitionCompactTests(unittest.TestCase):
    def test_weighted_deform_and_uv_identity_at_intermediate_times(self):
        doc,_=source();split,report=build(doc,['a']);original=deepcopy(split)
        candidate,receipt=compact(split,report)
        for time in [0,.125,.5,.875,1]:
            before=sample(doc,'test',time)[0];after=sample(candidate,'test',time)[0]
            for row in receipt['regions']:
                self.assertEqual(after[row['slot']],[before['a'][i] for i in row['source_vertex_indices']])
                mesh=candidate['skins'][0]['attachments'][row['slot']][row['slot']]
                self.assertEqual(mesh['uvs'],[v for i in row['source_vertex_indices']
                    for v in doc['skins'][0]['attachments']['a']['a']['uvs'][2*i:2*i+2]])
        self.assertEqual(split,original)
        self.assertFalse(receipt['deformation_index_space_preserved'])

    def test_sparse_deforms_are_expanded_and_unsupported_curve_rejected(self):
        doc,_=source();split,report=build(doc,['a']);name=report['regions'][0]['slot']
        keys=split['animations']['test']['attachments']['default'][name][name]['deform']
        keys[0]={'time':0,'offset':2,'vertices':[.1,.2]}
        candidate,receipt=compact(split,report)
        actual=candidate['animations']['test']['attachments']['default'][name][name]['deform'][0]
        self.assertEqual(actual['vertices'],[0,0,.1,.2,0,0]);self.assertNotIn('offset',actual)
        keys[0]['curve']=[.2,.3,.4,.5]
        with self.assertRaisesRegex(ValueError,'compact_curve'):compact(split,report)

    def test_multi_influence_deform_coordinates_are_remapped_per_influence(self):
        doc,_=source();mesh=doc['skins'][0]['attachments']['a']['a'];data=mesh['vertices']
        index,x,y,_=data[11:15]
        mesh['vertices']=data[:10]+[2,index,x,y,.25,1,x+.2,y-.3,.75]+data[15:]
        keys=doc['animations']['test']['attachments']['default']['a']['a']['deform']
        keys[0]['vertices']=[0]*10;keys[1]['vertices']=[i*.03 for i in range(10)]
        split,report=build(doc,['a']);candidate,receipt=compact(split,report)
        for time in [0,.2,.7,1]:
            expected=sample(doc,'test',time)[0]['a'];actual=sample(candidate,'test',time)[0]
            for row in receipt['regions']:
                self.assertEqual(actual[row['slot']],[expected[i] for i in row['source_vertex_indices']])


if __name__=='__main__':unittest.main()
