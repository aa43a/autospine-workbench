"""Fresh raw component grids enter sleeve annotation without fabricated history."""
from copy import deepcopy
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest

from PIL import Image
from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from autospine_workbench.asset.planning.component_partitions import build as partition
from autospine_workbench.asset.planning.component_ownership import template as ownership
from autospine_workbench.asset.planning.component_mesh import build as mesh_build
from autospine_workbench.asset.planning.sleeve_regions import build, template, validate
from autospine_workbench.asset.planning.sleeve_weights import build as weights_build
from autospine_workbench.asset.planning.sleeve_region_review import render
from autospine_workbench.benchmark.mesh_storage import publish_mesh_report, read_mesh_report
from autospine_workbench.resolved_project import canonical_sha256


def fixture():
    image = Image.new('RGBA', (12, 48), (80, 120, 200, 255))
    stream = BytesIO(); image.save(stream, format='PNG'); raw = stream.getvalue()
    layer = dict(layer_id='arm', name='handwear-l', bbox=[100, 200, 112, 248],
                 image_sha256=sha256(raw).hexdigest())
    part = partition(layer, raw)
    entries = [(layer, raw, part, 'a'*64)]
    ids = ['upperarm_l', 'forearm_l', 'hand_l']
    skeleton = dict(bones=[dict(id=b, parent_id=ids[i-1] if i else 'chest',
        head_xy=[106, 200+i*16], tail_xy=[106, 216+i*16], world_rotation_degrees=90)
        for i, b in enumerate(ids)])
    draft = ownership('new-character', entries, {}, 'b'*64, ids)
    draft['records'][0].update(status='assigned', semantic='body.arm', side='left', bone_ids=ids)
    source = mesh_build(entries, skeleton, draft, {}, 'b'*64)
    inputs = SimpleNamespace(candidate={'layers': [layer]}, images={'arm': raw}, skeleton=skeleton)
    return source, skeleton, inputs


class SleeveMeshSourceTests(unittest.TestCase):
    def test_new_profile_real_grid_editor_and_weight_pipeline(self):
        source, skeleton, inputs = fixture()
        original = deepcopy(source)
        candidate = build(source, skeleton)
        self.assertEqual(candidate['schema'], 'autospine.sleeve-regions/v2')
        self.assertEqual(candidate['profile'], 'component-mesh-wrist-band12-v1')
        self.assertEqual(candidate['source_sha256'], canonical_sha256(source))
        self.assertEqual(len(candidate['records']), 1)
        draft = template(candidate)
        self.assertTrue(all(a['role'] == 'unknown' for a in draft['records'][0]['assignments']))
        draft['records'][0]['assignments'][0].update(role='sleeve', origin='manual_edit')
        self.assertEqual(validate(draft, candidate), draft)
        page = render(candidate, draft, inputs, source)
        self.assertIn('动画时间轴', page)
        self.assertIn('component-mesh-wrist-band12-v1', page)
        weighted = weights_build(source, candidate, draft, skeleton)
        self.assertEqual(weighted['source_sha256'], canonical_sha256(source))
        self.assertEqual(weighted['candidate_sha256'], canonical_sha256(candidate))
        self.assertEqual(weighted['corrective_status'], 'not_reused')
        self.assertEqual(source, original)
        with tempfile.TemporaryDirectory() as root:
            digest = publish_mesh_report(root, 'project-component-partitions', candidate)
            self.assertEqual(read_mesh_report(root, 'project-component-partitions', digest), candidate)
        old = json.loads(Path('schemas/sleeve-regions-v1.schema.json').read_text())
        schema = json.loads(Path('schemas/sleeve-regions-v2.schema.json').read_text())
        registry = Registry().with_resource('sleeve-regions-v1.schema.json', Resource.from_contents(old))
        Draft202012Validator(schema, registry=registry).validate(candidate)

    def test_legacy_output_identity_is_unchanged_and_draft_not_transferable(self):
        source, skeleton, _ = fixture()
        fresh = build(source, skeleton)
        legacy = deepcopy(source)
        legacy['schema'] = 'autospine.component-axial-correction/v1'
        result = build(legacy, skeleton)
        expected = deepcopy(fresh)
        expected.update(schema='autospine.sleeve-regions/v1',
                        profile='wrist-band12-triangle-suggestions-v1',
                        source_sha256=canonical_sha256(legacy))
        self.assertEqual(result, expected)
        with self.assertRaises(ValueError):
            validate(template(result), fresh)

    def test_invalid_raw_source_profiles_geometry_and_weights_fail(self):
        source, skeleton, _ = fixture()
        mutations = [lambda s: s.update(profile='unrecognized'),
                     lambda s: s['records'].append(deepcopy(s['records'][0])),
                     lambda s: s['records'][0]['mesh']['triangles'][0].__setitem__(0, 999999),
                     lambda s: s['records'][0]['mesh']['weights'][0][0].update(weight=float('nan'))]
        for mutation in mutations:
            bad = deepcopy(source); mutation(bad)
            with self.assertRaises(ValueError):
                build(bad, skeleton)


if __name__ == '__main__':
    unittest.main()
