from copy import deepcopy
from hashlib import sha256
from types import SimpleNamespace
from unittest import TestCase
import json

from test_multi_animation import source, address
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.targets.character43.multi_animation import build
from autospine_workbench.targets.character43.multi_animation_geometry import inspect


class MultiGeometryTests(TestCase):
    def test_face_compression_keeps_source_bounds_and_inversion_failures(self):
        a, b = source('a'), source('b', 20)
        parent = dict(a['files'])
        parent['deformation.json'] = canonical_bytes(dict(records=[dict(animation='body', slot='eye',
            passed=True, min_area_ratio=1, inversion_samples=0)]))
        parent_sha = address('parent', parent)['artifact_sha256']
        joint = dict(skeleton_sha256=sha256(a['files']['skeleton.json']).hexdigest(),
            parent_skeleton_sha256=sha256(parent['skeleton.json']).hexdigest(),
            inventory=dict(face=dict(parts=[dict(slot='eye', role='eye.white')])),
            config=dict(face=dict(enabled=True)), face=dict(channels={'eye': dict(min_scale_x=1,min_scale_y=.08)}))
        a['files']['joint-animation.json'] = canonical_bytes(joint)
        a['files']['joint-provenance.json'] = canonical_bytes(dict(parent_artifact_sha256=parent_sha))
        a = address('a', a['files'])
        output, _ = build([a,b])
        lookup={a['artifact_sha256']:a['files'], b['artifact_sha256']:b['files'], parent_sha:parent}
        store=SimpleNamespace(read=lambda digest:lookup[digest])
        raw=dict(records=[dict(animation='a-01', slot='eye', passed=False,min_area_ratio=.08,
            max_area_ratio=1,max_edge_stretch=1,inversion_samples=0),
            dict(animation='b-01',slot='eye',passed=True)])
        self.assertTrue(inspect(raw,output,store)['passed'])
        bad=deepcopy(raw);bad['records'][0]['inversion_samples']=1
        self.assertFalse(inspect(bad,output,store)['passed'])
        bad=deepcopy(raw);bad['records'][0]['min_area_ratio']=.01
        self.assertFalse(inspect(bad,output,store)['passed'])
        changed=dict(output);doc=json.loads(changed['skeleton.json'])
        doc['animations']['a-01']['bones']['head']['rotate'][0]['value']=40
        changed['skeleton.json']=canonical_bytes(doc)
        report=json.loads(changed['multi-animation.json'])
        report['skeleton_sha256']=sha256(changed['skeleton.json']).hexdigest()
        changed['multi-animation.json']=canonical_bytes(report)
        with self.assertRaisesRegex(ValueError,'track_changed'):
            inspect(raw,changed,store)
