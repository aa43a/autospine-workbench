"""Synthetic experimental grids never masquerade as approved mesh production."""
from copy import deepcopy
import hashlib
from io import BytesIO
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from autospine_workbench.asset.joints.layer_binding import build_layer_bindings
from autospine_workbench.asset.joints.reviewed_skeleton import build_reviewed_skeleton
from autospine_workbench.asset.joints.mesh_candidate import build_mesh_candidate, validate_mesh_candidate
from autospine_workbench.benchmark.layer_binding_draft import build_layer_binding_draft
from autospine_workbench.resolved_project import canonical_sha256
from tests.test_layer_binding import fixture as binding_fixture


def fixture(two_components=False, bilateral=False):
    from PIL import Image, ImageDraw
    candidate, assisted, _ = binding_fixture('handwear' if bilateral else 'handwear-l')
    image = Image.new('RGBA', (60, 100))
    draw = ImageDraw.Draw(image)
    if two_components:
        draw.rectangle((5, 5, 15, 15), fill=(0, 0, 0, 255))
        draw.rectangle((40, 75, 50, 85), fill=(0, 0, 0, 255))
    else:
        draw.line([(20, 5), (35, 50), (50, 90), (52, 96)], fill=(0, 0, 0, 255), width=9)
    buffer = BytesIO(); image.save(buffer, format='PNG')
    raw = buffer.getvalue(); digest = hashlib.sha256(raw).hexdigest()
    candidate['layers'][1].update(bbox=[120, 130, 180, 230], image_sha256=digest,
                                 image={'sha256': digest, 'byte_size': len(raw)})
    assisted['candidate_sha256'] = assisted['draft']['candidate_sha256'] = canonical_sha256(candidate)
    skeleton = build_reviewed_skeleton(candidate, assisted)
    bindings = build_layer_bindings(candidate, assisted, skeleton)
    draft = build_layer_binding_draft(bindings)
    draft['records'][1].update(action='bind', option_id='mesh_chain:bilateral:arm' if bilateral else 'mesh_chain:l:arm')
    return candidate, assisted, skeleton, bindings, draft, {'layer-001': raw}


class MeshCandidateTests(unittest.TestCase):
    def test_actual_grid_weights_setup_reconstruction_and_purity(self):
        args = fixture()
        before = deepcopy(args)
        report = build_mesh_candidate(*args)
        self.assertEqual(args, before)
        self.assertEqual(validate_mesh_candidate(*args, report), report)
        layer = report['layers'][1]
        self.assertGreater(len(layer['vertices_xy']), 0)
        self.assertEqual(len(layer['vertices_xy']), len(layer['weights']))
        self.assertLessEqual(layer['qa']['setup_max_error'], 1e-6)
        self.assertTrue(all(120 <= x <= 180 and 130 <= y <= 230 for x, y in layer['vertices_xy']))
        self.assertTrue(all(0 <= u <= 1 and 0 <= v <= 1 for u, v in layer['uvs']))
        self.assertTrue(all(abs(sum(i['weight'] for i in influences)-1) < 1e-8 for influences in layer['weights']))
        self.assertEqual(report['layers'][0]['reason_codes'], ['binding_selection_required'])
        self.assertFalse(report['production_authorized'])

    def test_bilateral_and_multiple_components_block_explicitly(self):
        report = build_mesh_candidate(*fixture(bilateral=True))
        self.assertEqual(report['layers'][1]['reason_codes'], ['bilateral_mesh_pending'])
        self.assertEqual(report['layers'][1]['vertices_xy'], [])
        report = build_mesh_candidate(*fixture(two_components=True))
        self.assertEqual(report['layers'][1]['reason_codes'], ['multiple_alpha_components'])
        self.assertEqual(report['layers'][1]['weights'], [])

    def test_rigid_exclude_and_unresolved_actions_do_not_compile(self):
        args = fixture()
        args[4]['records'][0].update(action='bind', option_id='rigid:head')
        args[4]['records'][1].update(action='exclude', option_id=None, notes='Synthetic exclusion')
        args[4]['records'][2].update(action='requires_split', notes='Synthetic split required')
        report = build_mesh_candidate(*args)
        self.assertEqual([r['status'] for r in report['layers']], ['reviewed_noop', 'reviewed_noop', 'blocked'])
        self.assertTrue(all(r['qa'] is None and not r['vertices_xy'] for r in report['layers']))

    def test_failed_qa_preserves_diagnostic_mesh(self):
        with patch('autospine_workbench.asset.joints.mesh_weights.evaluate_mesh', return_value={'passed': False}):
            row = build_mesh_candidate(*fixture())['layers'][1]
        self.assertEqual(row['status'], 'blocked')
        self.assertIn('mesh_deformation_qa_failed', row['reason_codes'])
        self.assertGreater(len(row['triangles']), 0)

    def test_hash_resource_and_report_tamper(self):
        args = fixture()
        images = dict(args[-1]); images['layer-001'] += b'changed'
        with self.assertRaisesRegex(ValueError, 'image_changed'):
            build_mesh_candidate(*args[:-1], images)
        with patch('autospine_workbench.asset.joints.mesh_candidate.MAX_PIXELS', 1):
            with self.assertRaisesRegex(ValueError, 'resource_limit'):
                build_mesh_candidate(*args)
        report = build_mesh_candidate(*args)
        report['layers'][1]['vertices_xy'][0][0] += 1
        with self.assertRaisesRegex(ValueError, 'mismatch'):
            validate_mesh_candidate(*args, report)


if __name__ == '__main__':
    unittest.main()
