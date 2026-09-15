import json
from types import SimpleNamespace
from unittest.mock import Mock
import unittest
from autospine_workbench.automation.character_weighted_replay import derive
from autospine_workbench.automation.character_component_replay import derive as component_replay


class PartitionReplayTests(unittest.TestCase):
    def test_unreviewed_partition_does_not_lookup_nonexistent_mount_predecessor(self):
        store=Mock();store.read.side_effect=AssertionError('must not load a rigid-mount predecessor')
        manager=SimpleNamespace(application=SimpleNamespace(store=store))
        files={'component-mount.json':json.dumps(dict(
            schema='autospine.character-component-mount/v1',
            profile='same-parent-component-partition-v1',partition_only=True,
            motion='original_parent_preserved',authority='none',selected=False,
            source_bundle_sha256='a'*64)).encode()}
        self.assertIsNone(derive(manager,{},files))
        store.read.assert_not_called()

    def test_legacy_rigid_mount_still_requires_its_exact_source(self):
        store=Mock();store.read.side_effect=ValueError('missing exact source')
        manager=SimpleNamespace(application=SimpleNamespace(store=store))
        files={'component-mount.json':json.dumps(dict(
            motion='rigid_parent_follow_no_added_tracks',source_bundle_sha256='a'*64)).encode()}
        with self.assertRaisesRegex(ValueError,'missing exact source'):
            component_replay(manager,{},files)
        store.read.assert_called_once_with('a'*64)
