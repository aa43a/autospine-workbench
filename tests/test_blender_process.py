"""FBX conversion must isolate task state without mutating software or inputs."""
import builtins
from hashlib import sha256
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch

from autospine_workbench.automation.blender_process import fbx_command, process_options
from autospine_workbench.automation.motion_intake_worker import execute
from autospine_workbench.automation.pipeline_run import PipelineRunError
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.bvh_fk import _origin, _world_matrices
from autospine_workbench.bvh_parser import parse_bvh
from test_mixamo_map import source


class BlenderProcessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.folder = self.root / 'task with spaces'
        self.folder.mkdir()

    def test_hostile_inherited_resource_paths_are_removed_and_state_is_task_local(self):
        inherited = dict(PATH='preserved-system-path', SystemRoot='preserved-system-root',
            PYTHONPATH='outside/imports', PythonHome='outside/python', PYTHONSTARTUP='outside/start.py',
            BLENDER_SYSTEM_PYTHON='outside/blender-python', blender_user_config='outside/config',
            BLENDER_USER_SCRIPTS='outside/addons', OCIO='outside/colors',
            Temp='outside/temp', AppData='outside/profile', CUDA_CACHE_PATH='outside/cuda')
        before = inherited.copy()
        options = process_options(self.folder, environment=inherited)
        env = options['env']
        self.assertEqual(inherited, before)
        self.assertEqual(env['PATH'], inherited['PATH'])
        self.assertEqual(env['SystemRoot'], inherited['SystemRoot'])
        for key in ('PYTHONPATH', 'PythonHome', 'PYTHONSTARTUP', 'BLENDER_SYSTEM_PYTHON',
                    'blender_user_config', 'OCIO', 'Temp', 'AppData'):
            self.assertNotIn(key, env)
        for key, value in env.items():
            if key.startswith('BLENDER_') or key in ('APPDATA', 'LOCALAPPDATA', 'TEMP', 'TMP',
                    'TMPDIR', 'XDG_CACHE_HOME', 'CUDA_CACHE_PATH', 'OPTIX_CACHE_PATH',
                    'MESA_SHADER_CACHE_DIR', 'DXVK_STATE_CACHE_PATH'):
                self.assertTrue(Path(value).is_relative_to(self.folder))
                self.assertTrue(Path(value).is_dir())
        self.assertEqual(env['PYTHONDONTWRITEBYTECODE'], '1')
        self.assertEqual(env['PYTHONNOUSERSITE'], '1')
        self.assertEqual(env['PYTHONSAFEPATH'], '1')
        self.assertEqual(options['cwd'], str(self.folder))
        self.assertFalse(options['shell'])
        self.assertEqual(options['stdin'], subprocess.DEVNULL)

    def test_runtime_state_alias_cannot_write_outside_task(self):
        outside = self.root / 'outside'
        outside.mkdir()
        try:
            os.symlink(outside, self.folder / 'blender-runtime', target_is_directory=True)
        except OSError:
            self.skipTest('directory symlinks unavailable')
        with self.assertRaises(PipelineRunError):
            process_options(self.folder, environment={})
        self.assertEqual(list(outside.iterdir()), [])

    def test_fixed_converter_arguments_keep_paths_literal_and_legacy_executable(self):
        blender = self.root / 'legacy blender.exe'
        blender.write_bytes(b'not executed')
        command = fbx_command(blender, self.folder)
        self.assertEqual(command[0], str(blender))
        self.assertIn('--disable-autoexec', command)
        self.assertIn('--factory-startup', command)
        self.assertIn('--python-use-system-env', command)
        script = Path(command[command.index('--python') + 1])
        self.assertEqual(script, Path(__file__).resolve().parents[1] / 'tools/export-fbx-bvh.py')
        self.assertEqual(command[command.index('--') + 1:],
            [str(self.folder / 'source.fbx'), str(self.folder / 'source.bvh'), '--root-only'])
        self.assertNotIn('--python-expr', command)
        with self.assertRaisesRegex(ValueError, 'motion_blender_unavailable'):
            fbx_command('relative/blender.exe', self.folder)

    def test_tool_entrypoints_disable_bytecode_before_addon_or_engine_imports(self):
        io_anim = ModuleType('io_anim_bvh')
        io_anim.export_bvh = SimpleNamespace()
        io_scene = ModuleType('io_scene_fbx')
        io_scene.parse_fbx = SimpleNamespace()
        fake_modules = {'bpy': ModuleType('bpy'), 'io_anim_bvh': io_anim, 'io_scene_fbx': io_scene}
        original_import = builtins.__import__
        observed = []

        def importing(name, *args, **kwargs):
            if name in fake_modules or name.startswith('autospine_workbench'):
                observed.append(name)
                self.assertTrue(sys.dont_write_bytecode, name)
            return original_import(name, *args, **kwargs)

        previous = sys.dont_write_bytecode
        previous_path = sys.path.copy()
        try:
            with patch.dict(sys.modules, fake_modules), patch('builtins.__import__', side_effect=importing):
                for name in ('export-fbx-bvh.py', 'inspect-fbx-motion.py'):
                    sys.dont_write_bytecode = False
                    runpy.run_path(str(Path(__file__).resolve().parents[1] / 'tools' / name))
                    self.assertTrue(sys.dont_write_bytecode)
        finally:
            sys.dont_write_bytecode = previous
            sys.path[:] = previous_path
        self.assertIn('io_anim_bvh', observed)
        self.assertIn('io_scene_fbx', observed)
        self.assertIn('autospine_workbench.bvh_parser', observed)

    def test_worker_uses_isolated_converter_then_real_bridge_and_motion_compiler(self):
        raw = source('mixamorig:')
        bvh = parse_bvh(raw)
        original = b'test-only fbx bytes'
        (self.folder / 'source.fbx').write_bytes(original)
        expected_sha = sha256(original).hexdigest()
        (self.folder / 'request.json').write_bytes(canonical_bytes(dict(
            format='fbx', view='front', source_sha256=expected_sha)))
        blender = self.root / 'manually configured blender.exe'
        blender.write_bytes(b'not executed')
        evidence = dict(source_sha256=expected_sha, blender_version='legacy-version',
            bridge=dict(bvh_sha256=sha256(raw).hexdigest(),
                        local_to_blender_world=[[1,0,0,0],[0,1,0,0],[0,0,1,0],[0,0,0,1]]),
            bones=[dict(name=bone.name, parent=bvh.joints[bone.parent_index].name
                        if bone.parent_index is not None else None) for bone in bvh.joints],
            samples=[dict(seconds=index*bvh.frame_time_seconds,
                joints={bone.name:list(_origin(matrix)) for bone,matrix in
                        zip(bvh.joints,_world_matrices(bvh,frame))})
                     for index,frame in enumerate(bvh.frames)])

        def converted(command, **options):
            self.assertEqual(command, fbx_command(blender, self.folder))
            self.assertEqual(options['cwd'], str(self.folder))
            self.assertEqual(options['timeout'], 180)
            self.assertEqual(options['stdin'], subprocess.DEVNULL)
            self.assertFalse(options['shell'])
            self.assertNotIn('PYTHONPATH', options['env'])
            self.assertTrue(Path(options['env']['TEMP']).is_relative_to(self.folder))
            (self.folder / 'source.bvh').write_bytes(raw)
            (self.folder / 'source.inspection.json').write_text(json.dumps(evidence))
            return SimpleNamespace(returncode=0)

        with patch.dict(os.environ, {'PYTHONPATH': 'outside/user-imports'}), patch(
                'autospine_workbench.automation.motion_intake_worker.subprocess.run', side_effect=converted):
            execute(self.folder, self.root / 'state', str(blender))
        result = json.loads((self.folder / 'worker-result.json').read_bytes())
        self.assertEqual(result['motion_status'], 'compiled')
        self.assertTrue(result['fbx_bridge']['passed'])
        self.assertEqual(result['fbx_bridge']['frames'], 2)
        self.assertEqual((self.folder / 'source.fbx').read_bytes(), original)
        self.assertEqual(blender.read_bytes(), b'not executed')
        self.assertEqual(result['character_animation_status'], 'not_built')


if __name__ == '__main__':
    unittest.main()
