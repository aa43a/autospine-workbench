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
        legacy,legacy_report=fit(doc,'a',observation,temporal=False)
        self.assertEqual(len(legacy['animations']['a']['bones']['foot_l']['rotate']),2)
        self.assertEqual(legacy_report['profile'],'source-foot-world-frame-fit-v1')
        self.assertNotIn('timeline',legacy_report)
        self.assertEqual(doc,before);self.assertEqual(result['bones'],doc['bones'])
        self.assertLess(report['maximum_matrix_error'],1e-10)
        rest=matrices(result,'a',0);old=matrices(doc,'a',1);current=matrices(result,'a',1)
        for s in ('l','r'):
            n='foot_'+s
            for a,b in zip(current[n][:4],rest[n][:4]):self.assertAlmostEqual(a,b)
            self.assertEqual(current[n][4:],old[n][4:])
        self.assertGreater(report['timeline']['fitted_key_count'],2)
        self.assertLessEqual(report['timeline']['maximum_relative_matrix_error'],1e-3)
        # Independent dense samples, not just the solver's quarter-point checks.
        for index in range(101):
            t=index/100
            posed=matrices(result,'a',t);original=matrices(doc,'a',t)
            for n in ('foot_l','foot_r'):
                self.assertLess(max(abs(a-b) for a,b in zip(posed[n][:4],rest[n][:4])),.002)
                self.assertEqual(posed[n][4:],original[n][4:])
        with self.assertRaisesRegex(ValueError,'existing_channels'):fit(result,'a',observation)

    def test_refinement_budget_does_not_return_unverified_fit(self):
        from unittest.mock import patch
        bones=[dict(name='root',x=0,y=0,rotation=0)]
        tracks={}
        for s in ('l','r'):
            bones.extend([dict(name='calf_'+s,parent='root',x=0,y=0,rotation=0),
                          dict(name='foot_'+s,parent='calf_'+s,x=1,y=0,rotation=0)])
            tracks['calf_'+s]={'scale':[dict(time=0,x=1,y=1),dict(time=1,x=.2,y=1)]}
        doc=dict(bones=bones,animations={'a':{'bones':tracks}})
        with patch('autospine_workbench.targets.character43.foot_orientation_timeline.MAX_PASSES',0):
            with self.assertRaisesRegex(ValueError,'timeline_budget_exceeded'):
                fit(doc,'a',dict(times=[0,1],tracks={'foot_l':[0,0],'foot_r':[0,0]}))

    def test_parent_keys_between_source_samples_are_included(self):
        bones=[dict(name='root',x=0,y=0,rotation=0)]
        tracks={}
        for s in ('l','r'):
            bones.extend([dict(name='calf_'+s,parent='root',x=0,y=0,rotation=0),
                          dict(name='foot_'+s,parent='calf_'+s,x=1,y=0,rotation=0)])
            tracks['calf_'+s]={'rotate':[dict(time=t,value=v) for t,v in
                [(0,0),(.12,0),(.13,60),(.14,0),(1,0)]]}
        doc=dict(bones=bones,animations={'a':{'bones':tracks}})
        result,report=fit(doc,'a',dict(times=[0,1],tracks={'foot_l':[0,0],'foot_r':[0,0]}))
        self.assertIn(.13,[key['time'] for key in result['animations']['a']['bones']['foot_l']['rotate']])
        for time in (.125,.13,.135):
            self.assertAlmostEqual(matrices(result,'a',time)['foot_l'][0],1)

    def test_singular_shear_is_rejected(self):
        doc=dict(bones=[dict(name='root',x=0,y=0,rotation=0)],
                 animations={'a':{'bones':{'root':{'shear':[dict(time=0,x=0,y=-90)]}}}})
        with self.assertRaisesRegex(ValueError,'shear_singular'):matrices(doc,'a',0)
