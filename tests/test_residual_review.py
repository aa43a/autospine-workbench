"""Bounded reassignment cannot drop pixels or silently choose a policy."""
from copy import deepcopy
from io import BytesIO
import json
from pathlib import Path
import shutil
import subprocess
import unittest
from PIL import Image

from tests.test_partition_pixels import fixture
from autospine_workbench.asset.joints.partition_pixels import partition,png
from autospine_workbench.asset.joints.residual_policy import apply_policy
from autospine_workbench.benchmark.residual_draft import build_draft,validate_draft
from autospine_workbench.benchmark.residual_controls import SCRIPT


class ResidualReviewTests(unittest.TestCase):
    def test_bounded_reassignment_and_byte_reconstruction(self):
        raw,source,proposal,image=fixture();parts,_=partition(raw,source,proposal)
        result,qa=apply_policy(raw,parts['ownership.png'],'nearest_4px')
        mask=Image.open(BytesIO(result['ownership.png']))
        self.assertEqual(mask.getpixel((0,7)),1)
        self.assertEqual(mask.getpixel((5,3)),3)
        self.assertEqual(mask.getpixel((0,0)),3)
        self.assertGreater(qa['moved_pixels'],0)
        buffers=[Image.open(BytesIO(result[k+'.png'])).tobytes() for k in ('left','right','residual')]
        self.assertEqual(bytes(sum(v) for v in zip(*buffers)),image.tobytes())
        self.assertEqual(apply_policy(raw,parts['ownership.png'],'nearest_4px'),(result,qa))
        for policy in ('pending','retain'):
            unchanged,metric=apply_policy(raw,parts['ownership.png'],policy)
            self.assertEqual(unchanged,parts)
            self.assertEqual(metric['moved_pixels'],0)

    def test_distant_and_high_alpha_residual_not_reassigned(self):
        image=Image.new('RGBA',(20,10));mask=Image.new('L',image.size,3)
        for xy,owner in (((1,1),1),((5,1),2)):
            image.putpixel(xy,(30,40,50,100));mask.putpixel(xy,owner)
        image.putpixel((19,9),(1,2,3,4));image.putpixel((2,1),(1,2,3,9))
        raw=png('RGBA',image.size,image.tobytes());ownership=png('L',mask.size,mask.tobytes())
        result,qa=apply_policy(raw,ownership,'nearest_4px')
        self.assertEqual(qa['moved_pixels'],0)
        self.assertEqual(Image.open(BytesIO(result['ownership.png'])).getpixel((2,1)),3)
        with self.assertRaises(ValueError):apply_policy(raw,ownership,'discard')

    def test_draft_requires_exact_source_notes_and_no_authority(self):
        source={'layers':[{'layer_id':'layer-001'}]};base=build_draft(source)
        self.assertEqual(base['records'][0]['policy'],'pending')
        self.assertEqual(validate_draft(source,base),base)
        for mutate in (lambda d:d.update(source_partitions_sha256='0'*64),lambda d:d.update(production_authorized=True),
                       lambda d:d['records'][0].update(policy='nearest_4px'),lambda d:d['records'].append(deepcopy(d['records'][0]))):
            bad=deepcopy(base);mutate(bad)
            with self.assertRaises(ValueError):validate_draft(source,bad)
        base['records'][0].update(policy='nearest_4px',notes='reviewed isolated edge')
        self.assertEqual(validate_draft(source,base),base)

    def test_browser_validation(self):
        node=shutil.which('node')
        if not node:self.skipTest('Node unavailable')
        base=build_draft({'layers':[{'layer_id':'layer-001'}]})
        program=SCRIPT+'\nconst base='+json.dumps(base)+''';
const assert=require('node:assert/strict');assert.deepEqual(validateResidualDraft(base,base),base);
const edited=structuredClone(base);edited.records[0].policy='nearest_4px';assert.throws(()=>validateResidualDraft(base,edited));
edited.records[0].notes='review';assert.equal(validateResidualDraft(base,edited).records[0].policy,'nearest_4px');
edited.source_partitions_sha256='0'.repeat(64);assert.throws(()=>validateResidualDraft(base,edited));
'''
        result=subprocess.run([node,'-'],input=program,text=True,capture_output=True)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_selected_policy_report_and_schema(self):
        from autospine_workbench.benchmark.residual_cli import analyze
        from autospine_workbench.benchmark.elbow_target_cli import archive
        raw,source,proposal,_=fixture();parts,_=partition(raw,source,proposal)
        partitions={'layers':[{'layer_id':'layer-001'}]}
        data=archive({'layer-001/source.png':raw,'layer-001/ownership.png':parts['ownership.png']})
        draft=build_draft(partitions)
        pending,_=analyze(partitions,data,draft)
        self.assertEqual(pending['layers'][0]['selected_qa']['moved_pixels'],0)
        draft['records'][0].update(policy='nearest_4px',notes='synthetic reviewed choice')
        selected,_=analyze(partitions,data,draft)
        self.assertGreater(selected['layers'][0]['selected_qa']['moved_pixels'],0)
        self.assertEqual(pending['layers'][0]['selected_policy'],'pending')
        try:
            from jsonschema import Draft202012Validator
        except ImportError:
            self.skipTest('jsonschema unavailable')
        root=Path(__file__).resolve().parents[1]/'schemas'
        for name,doc in (('residual-draft-v1',draft),('residual-review-v1',selected)):
            Draft202012Validator(json.loads((root/(name+'.schema.json')).read_text('utf-8'))).validate(doc)
