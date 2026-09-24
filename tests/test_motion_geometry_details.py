import json
from hashlib import sha256
import unittest
from unittest.mock import patch

from autospine_workbench.targets.character43.motion_geometry_details import build


def fixture():
    mesh=dict(type='mesh',uvs=[0,0,1,0,0,1],triangles=[0,1,2],
              vertices=[1,0,0,0,1,1,0,1,0,1,1,0,0,1,1])
    doc=dict(bones=[dict(name='root',rotation=0,x=0,y=0)],slots=[dict(name='leg',bone='root')],
             skins=[dict(name='default',attachments={'leg':{'leg':mesh}})],
             animations={'move':{}})
    raw=json.dumps(doc).encode();digest=sha256(raw).hexdigest()
    def encode(value):return json.dumps(dict(skeleton_sha256=digest,**value)).encode()
    return {'skeleton.json':raw,'images/leg.png':b'png',
            'deformation.json':encode(dict(records=[dict(animation='move',slot='leg',passed=False)])),
            'rig-setup-reference.json':encode(dict(vertices={'leg':[[0,0],[1,0],[0,1]]})),
            'numeric-reference.json':encode(dict(animations={'move':[
                dict(time=0,vertices={'leg':[[0,0],[1,0],[0,1]]}),
                dict(time=.25,vertices={'leg':[[0,0],[1,0],[0,.2]]}),
                dict(time=.75,vertices={'leg':[[0,0],[1,0],[0,3]]})]}))}


class GeometryDetailsTests(unittest.TestCase):
    def test_active_mesh_report_is_not_located_using_setup_triangle_indices(self):
        files=fixture();qa=json.loads(files['deformation.json'])
        qa['profile']='character-active-attachment-deformation-v1'
        files['deformation.json']=json.dumps(qa).encode()
        report=build(files,'a'*64)
        self.assertEqual(report['status'],'unavailable')
        self.assertEqual(report['reason'],'active_attachment_source_locations_not_supported')
        self.assertEqual(report['rows'],[])

    def test_compression_and_expansion_use_their_own_times_and_ratios(self):
        report=build(fixture(),'a'*64)
        events={r['reason']:r for r in report['rows'][0]['details']}
        self.assertEqual(events['area_compression']['time'],.25)
        self.assertEqual(events['area_expansion']['time'],.75)
        self.assertEqual(events['area_expansion']['ratio_to_projected_reference'],3)
        self.assertEqual(events['area_compression']['texture_uv'],[[0,0],[1,0],[0,1]])
        self.assertFalse(report['selected'])

    def test_counterfactual_retains_bone_scale_and_does_not_mutate_files(self):
        files=fixture()
        doc=json.loads(files['skeleton.json'])
        doc['animations']['move']={'bones':{'root':{'scale':[dict(time=0,x=.4,y=1)]}}}
        raw=json.dumps(doc).encode();files['skeleton.json']=raw
        for name in ('deformation.json','rig-setup-reference.json','numeric-reference.json'):
            value=json.loads(files[name]);value['skeleton_sha256']=sha256(raw).hexdigest()
            files[name]=json.dumps(value).encode()
        before=dict(files)
        detail=next(r for r in build(files,'a'*64)['rows'][0]['details'] if r['reason']=='area_compression')
        self.assertAlmostEqual(detail['without_deform_setup_ratio'],.4)
        self.assertAlmostEqual(detail['deform_area_delta_ratio'],-.2)
        self.assertEqual(files,before)

    def test_identity_rejected_and_missing_setup_is_unavailable(self):
        files=fixture();del files['rig-setup-reference.json']
        self.assertEqual(build(files,'a'*64)['status'],'unavailable')
        files=fixture();files['skeleton.json']+=b' '
        with self.assertRaisesRegex(ValueError,'identity_mismatch'):build(files,'a'*64)

    def test_real_deform_is_removed_only_in_counterfactual(self):
        from autospine_workbench.targets.character43.affine_pose import sample
        files=fixture();doc=json.loads(files['skeleton.json'])
        doc['animations']['move']={
            'bones':{'root':{'scale':[dict(time=0,x=.4,y=1)]}},
            'attachments':{'default':{'leg':{'leg':{'deform':[
                dict(time=0,vertices=[0,0,0,0,0,-.5])]}}}}}
        raw=json.dumps(doc).encode();files['skeleton.json']=raw
        for name in ('deformation.json','rig-setup-reference.json','numeric-reference.json'):
            value=json.loads(files[name]);value['skeleton_sha256']=sha256(raw).hexdigest()
            if name=='numeric-reference.json':
                value['animations']={'move':[dict(time=0,vertices=sample(doc,'move',0)[0])]}
            files[name]=json.dumps(value).encode()
        before=dict(files)
        detail=build(files,'a'*64)['rows'][0]['details'][0]
        self.assertAlmostEqual(detail['setup_ratio'],.2)
        self.assertAlmostEqual(detail['without_deform_setup_ratio'],.4)
        self.assertAlmostEqual(detail['deform_area_delta_ratio'],-.2)
        self.assertEqual(files,before)

    def test_proxy_failure_does_not_hide_actual_failure(self):
        with patch('autospine_workbench.targets.character43.motion_geometry_details.projected_reference',
                   side_effect=ValueError('projected_area_orientation_invalid')):
            details=build(fixture(),'a'*64)['rows'][0]['details']
        self.assertEqual(len(details),2)
        self.assertIsNone(details[0]['projected_reference_ratio'])

    def test_endpoint_uses_verified_candidate(self):
        from autospine_workbench.automation.motion_target_jobs import review_file
        with patch('autospine_workbench.automation.motion_target_jobs.context',
                   return_value=(dict(artifact_sha256='a'*64,runtime={'status':'unavailable'}),fixture())):
            raw,kind=review_file(None,'test',['geometry-details.json'])
        self.assertEqual(kind,'application/json')
        self.assertEqual(json.loads(raw)['artifact_sha256'],'a'*64)

    def test_truncation_counts_events_not_unique_triangles(self):
        row=build(fixture(),'a'*64,limit=1)['rows'][0]
        self.assertEqual(row['failed_area_triangles'],1)
        self.assertTrue(row['truncated'])
        self.assertEqual(row['details'][0]['reason'],'area_expansion')
