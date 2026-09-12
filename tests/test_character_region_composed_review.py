"""A review on a multi-motion view must replay on the pre-motion character."""
import json
import unittest
import test_character_region_decisions as flat_review
from test_character_motion_composition import package
from autospine_workbench.automation.storage_io import canonical_bytes as raw
from autospine_workbench.automation.character_region_decisions import save, apply_saved, overview
from autospine_workbench.targets.character43.motion_composition import compose


class ComposedReviewTests(unittest.TestCase):
    def setUp(self):
        flat_review.RegionDecisionTests.setUp(self)
        base, motion = package('idle'), package('walk')
        manifest = json.loads(base['character-manifest.json'])
        manifest['layers'] = [dict(layer_id='source', state='static_reference',
            regions=[dict(region_id='leg', state='static_reference')],
            reason_codes=['static_reference_not_bound'], missing_region_ids=[])]
        base['character-manifest.json'] = raw(manifest)
        self.packages.update({'a'*64: base, 'b'*64: motion,
                              'c'*64: compose(base, motion, 'a'*64, 'b'*64)})
        self.manager.get = lambda *_: dict(status='needs_review', artifact_sha256='c'*64)
        self.body.update(expected_artifact_sha256='c'*64, region_id='leg')

    def test_save_rebuild_and_revoke_restore_original_without_erasing_history(self):
        current = save(self.manager, 'project', self.body)
        decision = current['active'][0]
        self.assertEqual(decision['reviewed_bundle_sha256'], 'c'*64)
        self.assertEqual(decision['source_bundle_sha256'], 'a'*64)
        original = dict(artifact_sha256='a'*64)
        built = apply_saved(self.manager, 'project', original, current['head_sha256'])
        self.assertEqual(built['manifest']['layers'][0]['state'], 'excluded')
        revoked = save(self.manager, 'project', dict(action='revoke',
            expected_head_sha256=current['head_sha256'], decision_sha256=decision['decision_sha256']))
        self.assertEqual(apply_saved(self.manager, 'project', original, revoked['head_sha256']), original)

    def test_changed_source_does_not_silently_reuse_decision(self):
        files = self.packages['c'*64]
        manifest = json.loads(files['character-manifest.json'])
        manifest['unverified_change'] = True
        files['character-manifest.json'] = raw(manifest)
        with self.assertRaisesRegex(RuntimeError, 'source_changed'):
            save(self.manager, 'project', self.body)
        self.assertEqual(overview(self.manager, 'project')['active'], [])
