"""Explicit optional-runtime choices govern every production use without fallback."""
from hashlib import sha256
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from autospine_workbench.automation import sleeve_capture_environment as environment
from autospine_workbench.automation.character_player import read


def dependency_tree(root):
    for name in ('spine-webgl', 'spine-core'):
        folder = root/'node_modules/@esotericsoftware'/name
        filename = 'dist/iife/spine-webgl.js' if name == 'spine-webgl' else 'dist/index.js'
        (folder/filename).parent.mkdir(parents=True)
        (folder/filename).write_bytes(b'official-test-'+name.encode())
        (folder/'package.json').write_text(json.dumps(dict(name='@esotericsoftware/'+name, version='4.3.13')))
    playwright = root/'node_modules/playwright-core'
    playwright.mkdir()
    (playwright/'package.json').write_text(json.dumps(dict(name='playwright-core', version='test-fixed')))
    (playwright/'index.mjs').write_bytes(b'playwright-entry')
    return root


class CaptureEnvironmentTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.workspace = self.root/'workspace';self.workspace.mkdir()
        self.browser = self.root/'browser.exe';self.browser.write_bytes(b'browser')
        self.node = self.root/'node.exe';self.node.write_bytes(b'node')
        self.env_patch = patch.dict(os.environ, {}, clear=True)
        self.env_patch.start();self.addCleanup(self.env_patch.stop)

    def configured(self, dependencies):
        return {environment.DEPENDENCIES_ENV: str(dependencies),
                environment.BROWSER_ENV: str(self.browser), environment.NODE_ENV: str(self.node)}

    def test_missing_old_environment_is_unavailable_without_launch_or_install(self):
        self.assertEqual(environment.discover(self.workspace), [])
        self.assertIsNone(environment.webgl_package(self.workspace))
        self.assertIsNone(environment.runtime_core(self.workspace))

    def test_old_workspace_default_and_path_node_remain_supported(self):
        dependencies = dependency_tree(self.workspace/'tmp/spine43-verification')
        with (patch.object(environment, 'STANDARD_BROWSERS', (self.browser,)),
              patch.object(environment.shutil, 'which', return_value=str(self.node))):
            self.assertEqual(environment.discover(self.workspace),
                ['--capture-dependencies', str(dependencies), '--capture-browser', str(self.browser)])
            self.assertEqual(environment.node_executable(), str(self.node.resolve()))
            identity = environment.identity(dependencies, self.browser)
            self.assertEqual(identity['node']['sha256'], sha256(b'node').hexdigest())
            self.assertEqual(identity['browser_sha256'], sha256(b'browser').hexdigest())

    def test_explicit_environment_is_used_outside_workspace_and_without_path(self):
        dependencies = dependency_tree(self.root/'chosen-dependencies')
        with (patch.dict(os.environ, self.configured(dependencies)),
              patch.object(environment.shutil, 'which', side_effect=AssertionError('fallback'))):
            self.assertEqual(environment.discover(self.workspace),
                ['--capture-dependencies', str(dependencies), '--capture-browser', str(self.browser)])
            self.assertEqual(environment.node_executable(), str(self.node))
            self.assertEqual(environment.runtime_core(self.workspace),
                dependencies/'node_modules/@esotericsoftware/spine-core')

    def test_empty_relative_and_missing_choices_never_fall_back(self):
        dependency_tree(self.workspace/'tmp/spine43-verification')
        for name in (environment.DEPENDENCIES_ENV, environment.BROWSER_ENV, environment.NODE_ENV):
            for value in ('', 'relative/path', str(self.root/'missing')):
                with self.subTest(name=name, value=value), patch.dict(os.environ, {name:value}):
                    with self.assertRaisesRegex(ValueError, 'configuration_invalid'):
                        environment.discover(self.workspace)

    def test_partial_explicit_dependencies_do_not_use_complete_workspace_defaults(self):
        dependency_tree(self.workspace/'tmp/spine43-verification')
        empty = self.root/'empty-dependencies';empty.mkdir()
        with patch.dict(os.environ, self.configured(empty)):
            with self.assertRaisesRegex(ValueError, 'environment_missing'):
                environment.discover(self.workspace)

    def test_both_runtime_packages_are_exactly_pinned(self):
        dependencies = dependency_tree(self.root/'chosen-dependencies')
        for name in ('spine-core','spine-webgl'):
            file = dependencies/'node_modules/@esotericsoftware'/name/'package.json'
            original = file.read_bytes()
            file.write_text(json.dumps(dict(name='@esotericsoftware/'+name, version='4.3.26')))
            with self.subTest(name=name), patch.dict(os.environ, self.configured(dependencies)):
                with self.assertRaisesRegex(ValueError, 'runtime_version'):
                    environment.discover(self.workspace)
            file.write_bytes(original)

    def test_full_identity_tracks_core_playwright_and_node_changes(self):
        dependencies = dependency_tree(self.root/'chosen-dependencies')
        with patch.dict(os.environ, self.configured(dependencies)):
            expected = environment.identity(dependencies,self.browser)
            targets = (dependencies/'node_modules/@esotericsoftware/spine-core/dist/index.js',
                       dependencies/'node_modules/playwright-core/index.mjs', self.node)
            for file in targets:
                original = file.read_bytes();file.write_bytes(original+b'changed')
                self.assertNotEqual(environment.identity(dependencies,self.browser), expected)
                file.write_bytes(original)
            self.assertEqual(environment.identity(dependencies,self.browser), expected)
            self.assertIn('package.json', expected['runtime'])
            self.assertIn('dist/index.js', expected['core'])
            self.assertIn('index.mjs', expected['playwright'])

    def test_playback_needs_only_exact_webgl_even_when_capture_browser_node_unavailable(self):
        from types import SimpleNamespace
        dependencies = dependency_tree(self.root/'chosen-dependencies')
        package = dependencies/'node_modules/@esotericsoftware/spine-webgl'
        raw = (package/'dist/iife/spine-webgl.js').read_bytes()
        report = dict(bundle_sha256='a'*64, runtime_package='@esotericsoftware/spine-webgl',
            runtime_version='4.3.13', runtime_sha256=sha256(raw).hexdigest())
        manager = SimpleNamespace(projects=SimpleNamespace(workspace_root=self.workspace),
            review_context=lambda *_: (dict(artifact_sha256='a'*64),{},json.dumps(report).encode()))
        with (patch.dict(os.environ, {environment.DEPENDENCIES_ENV:str(dependencies),
              environment.BROWSER_ENV:str(self.root/'missing-browser'),
              environment.NODE_ENV:str(self.root/'missing-node')}),
              patch.object(environment.shutil,'which',side_effect=AssertionError('PATH lookup'))):
            self.assertEqual(read(manager,'p','j',['player-assets','runtime.js'])[0], raw)
            with self.assertRaisesRegex(ValueError,'configuration_invalid'):
                environment.discover(self.workspace)


if __name__ == '__main__': unittest.main()
