from copy import deepcopy
import json
from pathlib import Path
import unittest
from tests import test_wing_split_preview as fixtures
from autospine_workbench.benchmark.wing_split_preview import build as split
from autospine_workbench.benchmark.wing_back_order import build,reorder,verify


class BackOrderTests(unittest.TestCase):
    def test_stable_order_and_animated_order_rejected(self):
        doc=dict(slots=[dict(name=n) for n in ['body','wing2','face','wing1']],animations={'idle':{}})
        old=deepcopy(doc);result=reorder(doc,{'wing1','wing2'})
        self.assertEqual([s['name'] for s in result['slots']],['wing2','wing1','body','face']);self.assertEqual(doc,old)
        with self.assertRaises(ValueError):reorder(doc,{'missing'})
        doc['animations']['idle']['drawOrder']=[]
        with self.assertRaises(ValueError):reorder(doc,{'wing1'})

    def test_only_slot_order_changes(self):
        edge,files,draft=fixtures.SplitPreviewTests().fixture();source,files=split(edge,files,draft);files.pop('preview-manifest.json')
        report,outputs=build(source,files)
        import jsonschema
        jsonschema.validate(report,json.loads(Path('schemas/wing-back-order-preview-v1.schema.json').read_text()))
        for name in ('skeleton.json','editor/skeleton.json'):
            before=json.loads(files[name]);after=json.loads(outputs[name]);after['slots']=before['slots'];self.assertEqual(before,after)
        for name,raw in files.items():
            if name not in ('skeleton.json','editor/skeleton.json','README.txt','review.html'):self.assertEqual(outputs[name],raw)
        self.assertEqual(report['slot_order_change']['after'][-1],'topwear')
        self.assertEqual(verify(report,source,files),report)
        bad=deepcopy(report);bad['textures_unchanged']=False
        with self.assertRaises(ValueError):verify(bad,source,files)
