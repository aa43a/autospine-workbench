import unittest
from copy import deepcopy
import contextlib
import io
import json
from pathlib import Path
import tempfile
from autospine_workbench.targets.character43.attachment_exit_pose import exits,outgoing_document
from autospine_workbench.targets.character43.active_mesh_pose import sample_active
from autospine_workbench.resolved_project import canonical_sha256
from m4_compile_foot_transition import run


class AttachmentExitTests(unittest.TestCase):
    def fixture(self):
        return dict(slots=[dict(name='leg',attachment='base')],animations={'move':dict(slots={'leg':dict(
            attachment=[dict(time=0,name='base'),dict(time=.7,name='variant'),dict(time=1.2,name='base')],
            rgba=[dict(time=0,color='ffffffff')])})})

    def test_outgoing_boundaries_keep_original_and_other_channels(self):
        doc=self.fixture();rows=exits(doc,'move','leg')
        self.assertEqual([r['attachment'] for r in rows],['base','variant'])
        self.assertNotEqual(rows[0]['time'],.7)
        pinned=outgoing_document(doc,'move','leg','base',rows[0]['time'])
        self.assertNotIn('attachment',pinned['animations']['move']['slots']['leg'])
        self.assertIn('rgba',pinned['animations']['move']['slots']['leg'])
        self.assertEqual(len(doc['animations']['move']['slots']['leg']['attachment']),3)

    def test_arbitrary_inactive_pose_cannot_be_claimed_as_exit(self):
        with self.assertRaisesRegex(ValueError,'verified_boundary'):
            outgoing_document(self.fixture(),'move','leg','base',.8)

    def test_baked_exit_guard_prevents_interpolation_toward_later_reentry(self):
        doc=self.fixture();doc['animations']['move']['slots']['leg'].pop('rgba')
        doc['bones']=[dict(name='root',x=0,y=0,rotation=0)]
        doc['slots'][0]['bone']='root'
        mesh=dict(type='mesh',uvs=[0,0,1,0,0,1],triangles=[0,1,2],
                  vertices=[1,0,0,0,1,1,0,1,0,1,1,0,0,1,1])
        doc['skins']=[dict(name='default',attachments={'leg':{k:deepcopy(mesh) for k in ('base','variant')}})]
        boundary=exits(doc,'move','leg');start,end=[r['time'] for r in boundary]
        rows=[]
        for time,name,x in ((0,'base',0),(.6,'base',0),(start,'variant',0),(end,'base',10),(1.3,'base',10)):
            rows.append(dict(time=time,slot='leg',attachment=name,transition_passed=True,
                points=[[x,0],[x+1,0],[x,1]]))
        report=dict(source_sha256=canonical_sha256(doc),animation='move',
                    times=sorted({r['time'] for r in rows}),records=rows)
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp);scene=folder/'scene.json';poses=folder/'poses.json'
            scene.write_text(json.dumps(dict(skeleton=doc)),encoding='utf-8')
            poses.write_text(json.dumps(report),encoding='utf-8')
            with contextlib.redirect_stdout(io.StringIO()):run(scene,scene,poses,folder/'without')
            for row in boundary:
                rows.append(dict(time=row['time'],slot='leg',attachment=row['attachment'],
                    guard='attachment_exit',transition_passed=True,points=[[0,0],[1,0],[0,1]]))
            poses.write_text(json.dumps(report),encoding='utf-8')
            with contextlib.redirect_stdout(io.StringIO()):run(scene,scene,poses,folder/'with')
            old=json.loads((folder/'without/candidate.json').read_bytes())['skeleton']
            fixed=json.loads((folder/'with/candidate.json').read_bytes())['skeleton']
            self.assertGreater(sample_active(old,'move',.65)['vertices']['leg'][0][0],.5)
            self.assertEqual(sample_active(fixed,'move',.65)['vertices']['leg'][0],[0.,0.])
            self.assertEqual(sample_active(fixed,'move',1.25)['vertices']['leg'][0],[10.,0.])
