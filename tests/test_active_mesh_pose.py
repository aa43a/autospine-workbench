import struct
import unittest

from test_pose_attachment_variant import PoseAttachmentVariantTests
from autospine_workbench.targets.character43.active_mesh_pose import sample_active
from autospine_workbench.targets.character43.affine_pose import sample
from autospine_workbench.asset.planning.component_local_solver import metrics


class ActiveMeshPoseTests(unittest.TestCase):
    def fixture(self):
        helper = PoseAttachmentVariantTests()
        doc, variant = helper.fixtures()
        return helper.compile(doc, variant)

    def test_topology_and_identity_follow_actual_attachment(self):
        document, report = self.fixture()
        for t, count in ((0, 4), (.5, 5), (1, 5), (1.5, 4)):
            frame = sample_active(document, 'move', t)
            self.assertEqual(len(frame['vertices']['leg']), count)
            self.assertEqual(frame['attachments']['leg'], report['variant_attachment'] if count==5 else 'leg')
            self.assertEqual(len(frame['setup_vertices']['leg']), count)
        with self.assertRaisesRegex(ValueError, 'requires_active'):
            sample(document, 'move', 1)

    def test_sparse_variant_deform_and_late_first_key(self):
        document, report = self.fixture()
        keys = document['animations']['move']['attachments']['default']['leg'][report['variant_attachment']]
        keys['deform'] = [dict(time=1, offset=17, vertices=[-20, 0, -20, 0, -20])]
        early = sample_active(document, 'move', .7)
        late = sample_active(document, 'move', 1)
        def quality(frame):
            flat = frame['triangles']['leg']
            return metrics(frame['setup_vertices']['leg'], frame['vertices']['leg'],
                           [flat[i:i+3] for i in range(0, len(flat), 3)])
        self.assertEqual(quality(early)['inversions'], 0)
        self.assertGreater(quality(late)['inversions'], 0)

    def test_hidden_attachment_and_float32_boundary(self):
        document, _ = self.fixture()
        keys = document['animations']['move']['slots']['leg']['attachment']
        keys[1] = dict(time=.1, name=None)
        effective = struct.unpack('f', struct.pack('f', .1))[0]
        self.assertIn('leg', sample_active(document, 'move', .1)['vertices'])
        frame = sample_active(document, 'move', effective)
        self.assertIsNone(frame['attachments']['leg'])
        self.assertNotIn('leg', frame['vertices'])

    def test_unknown_attachment_and_collapsed_times_fail_closed(self):
        document, _ = self.fixture()
        keys = document['animations']['move']['slots']['leg']['attachment']
        keys[1]['name'] = 'missing'
        with self.assertRaisesRegex(ValueError, 'missing'):
            sample_active(document, 'move', 1)
        keys[2]['time'] = .500000001
        with self.assertRaisesRegex(ValueError, 'collision'):
            sample_active(document, 'move', 0)
