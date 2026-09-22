from copy import deepcopy
import unittest
from hashlib import sha256
import json
from autospine_workbench.targets.character43.final_motion_contact import recheck, for_candidate
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.targets.character43.motion_contacts import analyze


def fixture():
    document=dict(bones=[dict(name='root',x=0,y=0,rotation=0),
                         dict(name='foot_l',parent='root',x=10,y=0,rotation=0)],
        animations={'a':{'bones':{'root':{'rotate':[dict(time=0,value=0),dict(time=1,value=360)]}}}})
    motion=dict(ticks_per_second=100,duration_ticks=100,
                markers=[dict(kind='contact',limb='leg.left',start_tick=0,end_tick=100)])
    return document,motion


class FinalContactTests(unittest.TestCase):
    def test_exact_runtime_grid_required_for_existing_candidate(self):
        doc,motion=fixture();doc['animations']['external-motion']=doc['animations'].pop('a')
        raw=canonical_bytes(doc)
        data={'motion-ir.json':motion,'motion-contact.json':{'selected':False},
              'motion-review.json':{'reference_length_px':100},
              'numeric-reference.json':dict(skeleton_sha256=sha256(raw).hexdigest(),
                  animations={'external-motion':[dict(time=t,vertices={}) for t in (0,.5,1)]})}
        files={k:canonical_bytes(v) for k,v in data.items()};files['skeleton.json']=raw
        runtime=dict(bundle_sha256='a'*64,passed=True,
                     results=[dict(animation='external-motion',time=t) for t in (0,.5,1)])
        result=for_candidate(files,'a'*64,runtime)
        self.assertEqual(result['status'],'needs_changes')
        self.assertEqual(result['artifact_sha256'],'a'*64)
        with self.assertRaisesRegex(ValueError,'runtime_mismatch'):for_candidate(files,'b'*64,runtime)
        runtime['results'].pop(1)
        with self.assertRaisesRegex(ValueError,'times_mismatch'):for_candidate(files,'a'*64,runtime)

    def test_final_midpoint_exposes_drift_hidden_by_original_samples(self):
        document,motion=fixture(); before=deepcopy((document,motion))
        old=analyze(document,'a',motion,[0,1],100)
        self.assertTrue(old['passed'])
        report=recheck(document,'a',motion,dict(selected=True,after=old),[0,.5,1],100)
        self.assertEqual(report['status'],'needs_changes')
        self.assertAlmostEqual(report['after']['max_drift_px'],20)
        self.assertEqual(report['after']['intervals'][0]['worst_time'],.5)
        self.assertEqual(report['pre_final_after'],old)
        self.assertEqual(report['final_timeline_check']['samples'],3)
        self.assertEqual((document,motion),before)

    def test_inferred_markers_retained_and_wrong_rate_rejected(self):
        doc,motion=fixture(); markers=motion.pop('markers');motion['markers']=[]
        contact={'hypothesis':dict(ticks_per_second=100,markers=markers)}
        self.assertEqual(recheck(doc,'a',motion,contact,[0,.5,1],100)['status'],'inferred_proxy_drift')
        contact['hypothesis']['ticks_per_second']=50
        with self.assertRaisesRegex(ValueError,'tick_rate'):recheck(doc,'a',motion,contact,[0,.5,1],100)
        self.assertEqual(recheck(doc,'a',motion,{},[0,.5,1],100)['status'],'unavailable_no_labels')

    def test_incomplete_or_unordered_grid_rejected(self):
        doc,motion=fixture()
        for times in ([0,.5],[.5,1],[0,.5,.5,1],[0,1,.5],[0,float('nan'),1]):
            with self.assertRaisesRegex(ValueError,'times_invalid'):recheck(doc,'a',motion,{},times,100)
