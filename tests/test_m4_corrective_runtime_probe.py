import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from m4_corrective_runtime_probe import render_inputs, run


class CorrectiveRuntimeInputsTests(unittest.TestCase):
    def test_old_motion_evidence_and_acceptance_cannot_follow_new_skeleton(self):
        source = {'skeleton.json': b'new-skeleton', 'textures/a.png': b'image',
                  'numeric-reference/a.json': b'new-reference',
                  'motion-review.json': b'old-review', 'motion-contact.json': b'old-contact',
                  'motion-depth.json': b'old-depth', 'deformation.json': b'old-geometry',
                  'visual-acceptance.json': b'old-acceptance'}
        evidence = {'geometry': {'passed': False}, 'source_candidate': 'parent', 'authority': 'none'}
        result = render_inputs(source, evidence)
        self.assertEqual(result['skeleton.json'], b'new-skeleton')
        self.assertEqual(result['textures/a.png'], b'image')
        self.assertEqual(result['numeric-reference/a.json'], b'new-reference')
        self.assertFalse(any(name.startswith('motion-') for name in result))
        self.assertNotIn('visual-acceptance.json', result)
        self.assertEqual(json.loads(result['deformation.json']), {'passed': False})
        self.assertEqual(source['deformation.json'], b'old-geometry')

    def test_capture_failure_is_terminal_in_receipt(self):
        evidence = dict(geometry={'passed': True}, source_candidate='parent', skeleton_sha256='new')
        with TemporaryDirectory() as root, \
                patch('m4_corrective_runtime_probe.prepare', return_value=({}, evidence)), \
                patch('m4_corrective_runtime_probe.AnimatedStore') as store, \
                patch('m4_corrective_runtime_probe.capture', side_effect=ValueError('time_collision')):
            store.return_value.publish.return_value = 'candidate'
            output = Path(root)/'output'
            with self.assertRaisesRegex(ValueError, 'time_collision'):
                run(Path(root)/'source', Path(root)/'experiment', output)
            report = json.loads((output/'report.json').read_bytes())
            self.assertEqual(report['runtime_status'], 'failed')
            self.assertEqual(report['runtime_error'], 'time_collision')
            self.assertFalse(report['selected'])


if __name__ == '__main__':
    unittest.main()
