"""Head detail adoption requires an existing face binding and actual pixel overlap."""
from copy import deepcopy
from types import SimpleNamespace
import hashlib
import unittest
from tests.test_layer_binding import fixture
from autospine_workbench.png_rgba import RgbaImage,encode_rgba_png
from autospine_workbench.asset.joints.reviewed_skeleton import build_reviewed_skeleton
from autospine_workbench.asset.joints.rigid_completion import build_completion
from autospine_workbench.benchmark.layer_binding_draft import build_layer_binding_draft
from autospine_workbench.resolved_project import canonical_sha256
from autospine_workbench.automation.head_binding_policy import propose,validate
from autospine_workbench.automation.simple_binding_policy import propose as old_policy


def source(box=None,transparent=False):
    candidate,assisted,_=fixture('mouth')
    candidate['layers'][1]['bbox']=box or [20,30,30,40]
    images={}
    for row in candidate['layers']:
        b=row['bbox'];pixel=bytes([0,0,0,0 if transparent and row['layer_id']=='layer-000' else 255])
        raw=encode_rgba_png(RgbaImage(b[2]-b[0],b[3]-b[1],pixel*((b[2]-b[0])*(b[3]-b[1]))))
        row['image_sha256']=hashlib.sha256(raw).hexdigest()
        row['image']={'sha256':row['image_sha256'],'byte_size':len(raw)}
        images[row['layer_id']]=raw
    assisted['candidate_sha256']=assisted['draft']['candidate_sha256']=canonical_sha256(candidate)
    skeleton=build_reviewed_skeleton(candidate,assisted)
    bindings=build_completion(candidate,assisted,skeleton);draft=build_layer_binding_draft(bindings)
    draft['records'][0].update(action='bind',option_id='rigid:head')
    return SimpleNamespace(candidate=candidate,assisted=assisted,skeleton=skeleton,bindings=bindings,draft=draft,images=images,source_addresses={})


class HeadPolicyTests(unittest.TestCase):
    def test_contained_feature_eligible_and_v1_unchanged(self):
        s=source();before=canonical_sha256(old_policy(s));doc=propose(s)
        row=doc['rows'][1]
        self.assertEqual(row['status'],'eligible');self.assertEqual(row['option_id'],'rigid:head')
        self.assertEqual(row['evidence']['face_overlap_ratio'],1)
        self.assertEqual(doc,validate(s,doc));self.assertEqual(before,canonical_sha256(old_policy(s)))
        self.assertEqual(s.draft['records'][1]['action'],'pending')

    def test_outside_and_transparent_face_rejected(self):
        for s in (source([51,30,61,40]),source(transparent=True)):
            row=propose(s)['rows'][1]
            self.assertEqual(row['status'],'needs_review')
            self.assertIn('visible_face_containment',row['reason_codes'])

    def test_large_feature_and_unreviewed_face_rejected(self):
        self.assertIn('small_head_feature',propose(source([10,20,50,80]))['rows'][1]['reason_codes'])
        s=source();s.draft['records'][0].update(action='pending',option_id=None)
        self.assertEqual(propose(s)['rows'][1]['status'],'needs_review')

    def test_existing_review_or_note_never_overwritten(self):
        s=source();s.draft['records'][1].update(action='exclude',notes='user exclusion')
        self.assertEqual(propose(s)['rows'][1]['status'],'preserved')
        s.draft['records'][1]['action']='pending'
        self.assertEqual(propose(s)['rows'][1]['status'],'preserved')

    def test_evidence_tamper_and_texture_change_rejected(self):
        s=source();doc=deepcopy(propose(s));doc['rows'][1]['evidence']['overlapping_pixels']=0
        with self.assertRaisesRegex(ValueError,'binding_policy_mismatch'):validate(s,doc)
        s.images['layer-001']=s.images['layer-001']+b'x'
        with self.assertRaisesRegex(ValueError,'image_changed'):propose(s)
