import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from autospine_workbench.automation.motion_tool_config import blender_location


class ToolConfigTests(unittest.TestCase):
    def test_persisted_path_survives_environment_loss(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict('os.environ', {}, clear=True):
            root=Path(folder); exe=root/'blender.exe'; exe.write_bytes(b'fixture-not-executed')
            (root/'config').mkdir()
            config=root/'config/motion-tools.json'
            config.write_text(json.dumps({'blender_executable':str(exe)}))
            for _ in range(2):
                self.assertEqual(blender_location(root),dict(path=str(exe),source='state_config',status='configured'))
            with patch.dict('os.environ', {'AUTOSPINE_BLENDER':str(root/'missing.exe')}):
                self.assertEqual(blender_location(root)['status'],'executable_missing')
            config.write_text(json.dumps({'blender_executable':'relative.exe'}))
            self.assertEqual(blender_location(root)['status'],'absolute_path_required')
            config.write_text('{broken')
            self.assertEqual(blender_location(root)['status'],'invalid_config')

    def test_path_fallback_only_without_explicit_configuration(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict('os.environ', {}, clear=True):
            exe=Path(folder)/'blender'; exe.write_bytes(b'fixture-not-executed')
            with patch('shutil.which',return_value=str(exe)):
                self.assertEqual(blender_location(folder)['source'],'path')
                with patch.dict('os.environ', {'AUTOSPINE_BLENDER':''}):
                    self.assertEqual(blender_location(folder)['status'],'not_configured')
