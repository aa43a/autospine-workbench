from copy import deepcopy
import math
import unittest
from autospine_workbench.asset.planning.sleeve_regions import build, template, validate
from autospine_workbench.resolved_project import canonical_sha256


class SleeveRegionTests(unittest.TestCase):
    def fixture(self):
        ids=['upperarm_l','forearm_l','hand_l']
        bones=[dict(id=b,parent_id=ids[i-1] if i else 'chest',head_xy=[i*10.,0.],tail_xy=[i*10.+10,0.]) for i,b in enumerate(ids)]
        # Proximal, cuff, distal central, crossing boundary, distal lateral.
        vertices=[[15,0],[16,0],[15,1],[19.5,0],[20.5,0],[20,.5], [23,0],[24,0],[23,.5], [18,0],[23,0],[20,1], [23,8],[24,8],[23,9]]
        skeleton=dict(bones=bones)
        source=dict(schema='autospine.component-axial-correction/v1', project_id='fixture', authority='none',production_authorized=False,
            skeleton_sha256=canonical_sha256(skeleton),records=[dict(layer_id='layer',component_id='part',source_image_sha256='a'*64,
                mesh=dict(bone_ids=ids,vertices_xy=vertices,triangles=[[i,i+1,i+2] for i in range(0,15,3)]))])
        return source,skeleton

    def test_suggestions_never_approve_and_boundary_unknown(self):
        source,skeleton=self.fixture(); original=deepcopy(source); candidate=build(source,skeleton)
        self.assertEqual([s['suggested_role'] for s in candidate['records'][0]['suggestions']],['sleeve','cuff','hand','unknown','unknown'])
        self.assertEqual(source,original);self.assertEqual(candidate,build(source,skeleton))
        self.assertTrue(all(a['origin']=='pending' for a in template(candidate)['records'][0]['assignments']))
        self.assertFalse(candidate['semantic_confirmed'])

    def test_transform_and_project_independence(self):
        source,skeleton=self.fixture(); expected=build(source,skeleton)['records'][0]['suggestions']
        for scale,mirror in [(.3,1),(4,-1)]:
            angle=math.radians(31)
            def transform(p):
                x,y=p[0]*mirror,p[1]
                return [100+scale*(x*math.cos(angle)-y*math.sin(angle)),30+scale*(x*math.sin(angle)+y*math.cos(angle))]
            s,k=deepcopy(source),deepcopy(skeleton);s['project_id']='different'
            for b in k['bones']:b['head_xy']=transform(b['head_xy']);b['tail_xy']=transform(b['tail_xy'])
            s['records'][0]['mesh']['vertices_xy']=list(map(transform,s['records'][0]['mesh']['vertices_xy']))
            s['skeleton_sha256']=canonical_sha256(k)
            self.assertEqual(expected,build(s,k)['records'][0]['suggestions'])

    def test_draft_roundtrip_and_tamper(self):
        candidate=build(*self.fixture());draft=template(candidate)
        item=draft['records'][0]['assignments'][0];item.update(role='sleeve',origin='geometry_prefill')
        draft['records'][0]['assignments'][4].update(role='hanging_cloth',origin='manual_edit')
        self.assertEqual(validate(draft,candidate),draft)
        for mutate in (lambda d:d.update(candidate_sha256='0'*64),lambda d:d['records'][0]['assignments'].pop(),
                       lambda d:d['records'][0]['assignments'][0].update(role='hand'),lambda d:d.update(production_authorized=True)):
            bad=deepcopy(draft);mutate(bad)
            with self.assertRaises(ValueError):validate(bad,candidate)
