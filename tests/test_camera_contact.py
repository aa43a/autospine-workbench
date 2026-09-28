from copy import deepcopy
import unittest
import test_camera_ankle_targets as fixtures
from autospine_workbench.targets.character43.source_ankle_targets import targets
from autospine_workbench.targets.character43.camera_contact import build,recheck


class CameraContactTests(unittest.TestCase):
    def fixture(self,moving=0):
        observation=fixtures.CameraAnkleTests().observe(moving=moving)
        rows=targets(observation,[[-30,-100],[30,-100]],100)
        bones=[dict(name='root',x=0,y=0,rotation=0)]+[dict(name='foot_'+s,parent='root',x=x,y=-100,rotation=0) for s,x in [('l',-30),('r',30)]]
        tracks={}
        for i,side in enumerate(('l','r')):
            tracks['foot_'+side]=dict(translate=[dict(time=r['time'],x=r['targets'][i][0]-bones[i+1]['x'],
                y=r['targets'][i][1]+100) for r in rows])
        doc=dict(bones=bones,animations={'external-motion':dict(bones=tracks)})
        motion=dict(ticks_per_second=1000000,duration_ticks=1000000,markers=[dict(kind='contact',limb='leg.'+s,
            start_tick=0,end_tick=1000000) for s in ('left','right')])
        return doc,motion,observation

    def test_orbit_is_not_misclassified_as_foot_slide(self):
        doc,motion,obs=self.fixture()
        report=build(doc,'external-motion',motion,obs,obs['times'],100)
        self.assertEqual(report['status'],'camera_contact_proxy_passed')
        self.assertLess(report['after']['max_drift_px'],1e-9)
        self.assertFalse(report['selected'])
        from autospine_workbench.targets.character43.motion_contact_review import render
        self.assertIn('相机旋转'.encode('utf-8'),render(report))
        fixed=deepcopy(doc);fixed['animations']['external-motion']['bones']={}
        checked=recheck(fixed,'external-motion',motion,report,obs['times'],100)
        self.assertEqual(checked['status'],'needs_changes')
        self.assertGreater(checked['after']['max_drift_px'],50)

    def test_source_slide_stays_failure_even_when_target_tracks_exactly(self):
        doc,motion,obs=self.fixture(moving=2)
        report=build(doc,'external-motion',motion,obs,obs['times'],100)
        self.assertEqual(report['status'],'needs_changes')
        self.assertGreater(report['after']['max_drift_px'],10)
        self.assertLess(max(s['tracking_error_px'] for r in report['after']['intervals'] for s in r['samples']),1e-9)

    def test_missing_labels_and_changed_observation_cannot_pass(self):
        doc,motion,obs=self.fixture();motion['markers']=[]
        report=build(doc,'external-motion',motion,obs,obs['times'],100)
        self.assertEqual(report['status'],'unavailable_no_labels')
        obs['keys'][-1]['yaw']=180
        with self.assertRaisesRegex(ValueError,'identity'):
            recheck(doc,'external-motion',motion,report,obs['times'],100)
