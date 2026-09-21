from copy import deepcopy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from autospine_workbench.targets.character43.affine_pose import matrices
from autospine_workbench.targets.character43.foot_orientation_fit import fit


class FootFitTests(unittest.TestCase):
    def test_observed_foot_rotation_uses_declared_basis(self):
        from test_mixamo_map import source
        from autospine_workbench.bvh_parser import parse_bvh
        from autospine_workbench.motion2d.mixamo_map import build_map
        from autospine_workbench.targets.character43.source_foot_orientation import extract
        raw=source();parsed=parse_bvh(raw);offset=0
        for joint in parsed.joints:
            if joint.name=='LeftFoot':break
            offset+=len(joint.channels)
        lines=raw.decode().splitlines();frame=lines[-1].split();frame[offset+2]='30';lines[-1]=' '.join(frame)
        raw=('\n'.join(lines)+'\n').encode()
        mapping=build_map(parse_bvh(raw),clip_id='test',reference_length=10,screen_x='+X',screen_y='-Y',depth='+Z')
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder);(path/'map.json').write_text(json.dumps(mapping))
            observed=extract(SimpleNamespace(path=path,source_kind='bvh',raw_bvh=raw))
        self.assertAlmostEqual(observed['tracks']['foot_l'][1],30)
        self.assertAlmostEqual(observed['tracks']['foot_r'][1],0)

    def test_cancels_rotated_nonuniform_parent_without_moving_ankle(self):
        bones=[dict(name='root',x=0,y=0,rotation=0)]
        tracks={}
        for s in ('l','r'):
            bones.extend([dict(name='calf_'+s,parent='root',x=1,y=2,rotation=20),
                          dict(name='foot_'+s,parent='calf_'+s,x=10,y=0,rotation=-15)])
            tracks['calf_'+s]={'rotate':[dict(time=0,value=0),dict(time=1,value=70)],
                               'scale':[dict(time=0,x=1,y=1),dict(time=1,x=.4,y=1.2)]}
        doc=dict(bones=bones,animations={'a':{'bones':tracks}});before=deepcopy(doc)
        observation=dict(times=[0,1],tracks={'foot_l':[0,0],'foot_r':[0,0]})
        result,report=fit(doc,'a',observation)
        self.assertEqual(doc,before);self.assertEqual(result['bones'],doc['bones'])
        self.assertLess(report['maximum_matrix_error'],1e-10)
        rest=matrices(result,'a',0);old=matrices(doc,'a',1);current=matrices(result,'a',1)
        for s in ('l','r'):
            n='foot_'+s
            for a,b in zip(current[n][:4],rest[n][:4]):self.assertAlmostEqual(a,b)
            self.assertEqual(current[n][4:],old[n][4:])
        with self.assertRaisesRegex(ValueError,'existing_channels'):fit(result,'a',observation)

    def test_singular_shear_is_rejected(self):
        doc=dict(bones=[dict(name='root',x=0,y=0,rotation=0)],
                 animations={'a':{'bones':{'root':{'shear':[dict(time=0,x=0,y=-90)]}}}})
        with self.assertRaisesRegex(ValueError,'shear_singular'):matrices(doc,'a',0)
