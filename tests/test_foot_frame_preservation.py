from copy import deepcopy
import unittest
from autospine_workbench.targets.character43.foot_frame_preservation import preserve
from autospine_workbench.targets.character43.affine_pose import matrices


class FootFramePreservationTests(unittest.TestCase):
    def fixture(self):
        bones=[dict(name='root',x=0,y=0,rotation=0)];tracks={}
        for side in ('l','r'):
            bones.extend([dict(name='calf_'+side,parent='root',x=0,y=0,rotation=10),
                          dict(name='foot_'+side,parent='calf_'+side,x=3,y=0,rotation=20)])
            tracks['foot_'+side]=dict(rotate=[dict(time=0,value=0),dict(time=1,value=25)])
        reference=dict(bones=bones,animations={'a':dict(bones=tracks)})
        candidate=deepcopy(reference)
        for side in ('l','r'):
            candidate['animations']['a']['bones']['calf_'+side]=dict(
                rotate=[dict(time=0,value=0),dict(time=1,value=80)],
                scale=[dict(time=0,x=1,y=1),dict(time=1,x=.4,y=1.2)])
        return candidate,reference

    def test_rebases_existing_channels_without_changing_ankle_or_reference(self):
        candidate,reference=self.fixture();before=deepcopy(candidate)
        result,report=preserve(candidate,reference,'a',[0,1])
        self.assertEqual(candidate,before);self.assertFalse(report['selected'])
        for i in range(101):
            t=i/100;a,b,c=(matrices(d,'a',t) for d in (candidate,reference,result))
            for name in ('foot_l','foot_r'):
                self.assertEqual(a[name][4:],c[name][4:])
                self.assertLess(max(abs(x-y) for x,y in zip(b[name][:4],c[name][:4])),.002)
        self.assertGreater(report['key_count'],2)

    def test_bind_change_rejected(self):
        candidate,reference=self.fixture();candidate['bones'][1]['x']=2
        with self.assertRaisesRegex(ValueError,'bind_changed'):preserve(candidate,reference,'a',[0,1])
