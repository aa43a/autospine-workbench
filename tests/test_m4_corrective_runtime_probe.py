import json
import unittest

from m4_corrective_runtime_probe import render_inputs


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


if __name__ == '__main__':
    unittest.main()
