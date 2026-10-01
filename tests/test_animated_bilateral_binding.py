"""A paired source is independently partitioned, never attached to one foot."""
from contextlib import nullcontext
from copy import deepcopy
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from autospine_workbench.asset.joints.reviewed_skeleton import build_reviewed_skeleton
from autospine_workbench.asset.joints.rigid_completion import build_completion
from autospine_workbench.automation.animated_binding_safety import bilateral_hints, check_binding_change
from autospine_workbench.automation.animated_compile import prepare_mesh, compile_preview
from autospine_workbench.automation.animated_inputs import AnimatedSourceError, save_binding_review
from autospine_workbench.benchmark.layer_binding_draft import build_layer_binding_draft
from autospine_workbench.resolved_project import canonical_sha256
from tests.test_layer_binding import fixture


def pair_source(*, one_shoe=False, ambiguous=False):
    from PIL import Image, ImageDraw
    candidate, assisted, _ = fixture('footwear')
    images = {}
    for source, name, box, rects in (
        (candidate['layers'][0], 'legwear', [55, 230, 145, 365], [(5, 2, 25, 130), (65, 2, 85, 130)]),
        (candidate['layers'][1], 'footwear', [55, 335, 145, 365], [(5, 3, 25, 28), (65, 3, 85, 28)]),
        (candidate['layers'][2], 'face', [90, 45, 110, 65], [(1, 1, 18, 18)]),
    ):
        if name == 'footwear':
            if one_shoe:
                rects = rects[:1]
            if ambiguous:
                rects = [(44, 3, 44, 28), (46, 3, 46, 28)]
        image = Image.new('RGBA', (box[2]-box[0], box[3]-box[1]))
        draw = ImageDraw.Draw(image)
        for rect in rects:
            draw.rectangle(rect, fill=(140, 120, 90, 255))
        stream = BytesIO(); image.save(stream, format='PNG'); raw = stream.getvalue()
        # Keep a faint source pixel outside either effective mesh as retained residual.
        if name == 'footwear':
            draw.point((45, 29), fill=(0, 0, 0, 1)); stream = BytesIO()
            image.save(stream, format='PNG'); raw = stream.getvalue()
        source.update(name=name, bbox=box, semantic=None if name != 'face' else 'body.face',
                      image_sha256=sha256(raw).hexdigest(),
                      image={'sha256': sha256(raw).hexdigest(), 'byte_size': len(raw)})
        images[source['layer_id']] = raw
    assisted['candidate_sha256'] = assisted['draft']['candidate_sha256'] = canonical_sha256(candidate)
    skeleton = build_reviewed_skeleton(candidate, assisted)
    bindings = build_completion(candidate, assisted, skeleton)
    draft = build_layer_binding_draft(bindings)
    return SimpleNamespace(candidate=candidate, assisted=assisted, skeleton=skeleton,
                           bindings=bindings, draft=draft, images=images, composite=b'',
                           source_addresses={}, assert_current=lambda: None)


class BilateralBindingTests(unittest.TestCase):
    def test_measured_pair_has_recovery_and_anatomical_mapping_without_source_mutation(self):
        source = pair_source(); before = deepcopy(vars(source))
        hints = bilateral_hints(source.candidate, source.skeleton, source.bindings, source.draft, source.images)
        foot = next(r for r in hints if r['layer_id'] == 'layer-001')
        self.assertEqual(foot['side_bone_ids'], {'r': ['foot_r'], 'l': ['foot_l']})
        self.assertEqual(set(foot['excluded_option_ids']), {'rigid:foot_l', 'rigid:foot_r'})
        self.assertEqual((foot['recovery_action'], foot['recovery_option_id']), ('pending', None))
        self.assertFalse(foot['production_authorized'])
        self.assertEqual(vars(source), before)

    def test_single_shoe_and_ambiguous_pair_do_not_get_auto_side_evidence(self):
        for kwargs in ({'one_shoe': True}, {'ambiguous': True}):
            source = pair_source(**kwargs)
            hints = bilateral_hints(source.candidate, source.skeleton, source.bindings, source.draft, source.images)
            self.assertNotIn('layer-001', {r['layer_id'] for r in hints})

    def test_stale_raster_cannot_create_a_partition_hint(self):
        source = pair_source(); source.images['layer-001'] += b'changed'
        with self.assertRaisesRegex(ValueError, 'structure_image_changed'):
            bilateral_hints(source.candidate, source.skeleton, source.bindings, source.draft, source.images)

    def test_completion_and_auto_rigid_policy_leave_unsuffixed_pair_for_partition(self):
        from autospine_workbench.automation.simple_binding_policy import propose
        from autospine_workbench.asset.joints.rigid_completion import inherit_unchanged
        from autospine_workbench.asset.joints.layer_binding import build_layer_bindings
        source = pair_source()
        base = build_layer_bindings(source.candidate, source.assisted, source.skeleton)
        inherited = inherit_unchanged(base, build_layer_binding_draft(base), source.bindings)
        self.assertEqual(inherited['records'][1]['action'], 'pending')
        source.draft = inherited
        row = next(r for r in propose(source)['rows'] if r['layer_id'] == 'layer-001')
        self.assertEqual(row['status'], 'needs_review')
        self.assertIsNone(row['option_id'])
        self.assertIn('side_name_required', row['reason_codes'])

    def test_new_single_foot_selection_is_rejected_before_registration_publication(self):
        source = pair_source()
        source.source_addresses = {'input_identity_sha256': 'a'*64, 'animated_registration_sha256': 'b'*64}
        source_info = {**vars(source)}
        records = deepcopy(source.draft['records'])
        records[1].update(action='bind', option_id='rigid:foot_r')
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            for row in source.candidate['layers']:
                (root/(row['layer_id']+'.png')).write_bytes(source.images[row['layer_id']])
            store = SimpleNamespace(state_root=root,
                get_project=lambda _: {'layers': [{'id': r['layer_id'], 'source_index': r['traversal_index']}
                                                    for r in source.candidate['layers']]},
                resolve_asset=lambda _, __, layer: root/(layer+'.png'))
            with patch('autospine_workbench.automation.animated_input_index.inspect_registration', return_value=source_info), \
                 patch('autospine_workbench.automation.animated_inputs.project_authoring_transaction', return_value=nullcontext()), \
                 patch('autospine_workbench.benchmark.artifacts.publish_report') as publish:
                with self.assertRaisesRegex(AnimatedSourceError, 'animated_bilateral_binding_requires_partition'):
                    save_binding_review(store, 'project', 'a'*64, records)
                publish.assert_not_called()
            self.assertEqual(source.draft['records'][1]['action'], 'pending')

    def test_existing_choice_stays_readable_noop_and_recovery_do_not_rewrite_it(self):
        source = pair_source(); source.draft['records'][1].update(action='bind', option_id='rigid:foot_r')
        info = {**vars(source)}
        # No-op and return-to-partition do not need source image analysis or mutation.
        with patch('autospine_workbench.automation.animated_binding_safety.partition_hints', return_value=[]) as analyze:
            check_binding_change(object(), 'project', info, deepcopy(source.draft))
            recovery = deepcopy(source.draft); recovery['records'][1].update(action='pending', option_id=None)
            check_binding_change(object(), 'project', info, recovery)
            self.assertTrue(all(call.kwargs['selected_layer_ids'] == [] for call in analyze.call_args_list))
        self.assertEqual(source.draft['records'][1]['option_id'], 'rigid:foot_r')
        with self.assertRaisesRegex(AnimatedSourceError, 'animated_bilateral_binding_requires_partition'):
            prepare_mesh(source)

    def test_restored_pair_generates_both_leg_and_shoe_meshes_retains_rgba_and_same_side_foot(self):
        source = pair_source(); before = deepcopy(source.draft)
        stage = prepare_mesh(source)
        parts = {p['source_layer_id']: p for p in stage['partitions']}
        self.assertEqual(set(parts), {'layer-000', 'layer-001'})
        for side in ('l', 'r'):
            leg = next(r for r in parts['layer-000']['meshes'] if r['side'] == side)
            shoe = next(r for r in parts['layer-001']['meshes'] if r['side'] == side)
            self.assertEqual(leg['bone_ids'], [f'{part}_{side}' for part in ('thigh', 'calf', 'foot')])
            self.assertEqual(shoe['bone_ids'], [f'foot_{side}'])
            self.assertTrue(all(len(w) == 1 and w[0]['bone_id'] == f'foot_{side}' and w[0]['weight'] == 1
                                for w in shoe['weights']))
            self.assertTrue(any(w[-1]['bone_id'] == f'foot_{side}' and w[-1]['weight'] == 1
                                for w in leg['weights']))
        self.assertTrue(all(p['qa']['rgba_reconstruction_exact'] for p in parts.values()))
        self.assertGreater(parts['layer-001']['qa']['visible_pixel_counts']['3'], 0)
        compiled = compile_preview(source, stage, 'limb-flex-15')
        self.assertEqual(compiled['summary']['partition_source_layers'], 2)
        self.assertFalse(compiled['summary']['rejected_mesh_layers'])
        for side in ('l', 'r'):
            expected = {f'layer-000-{side}', f'layer-001-{side}'}
            seam = next(r for r in compiled['qa']['geometry']['seam_proxy'] if set(r['regions']) == expected)
            self.assertGreater(seam['pair_count'], 0)
            self.assertLess(seam['max_distance_growth_px'], 1e-7)
        # Vertex proximity is useful connection evidence, not alpha seam certification.
        self.assertEqual(compiled['qa']['geometry']['seam_coverage'], 'unproven')
        self.assertEqual(source.draft, before)


if __name__ == '__main__':
    unittest.main()
