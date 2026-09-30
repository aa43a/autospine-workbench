"""Fixed FBX converter arguments and task-local Blender runtime state.

The installed software and trusted engine scripts remain read-only. This
profile also isolates legacy manually configured Blender executables; their
version is not silently replaced or restricted to the private bundle version.
"""
import os
from pathlib import Path
import subprocess

from .storage_io import directory

BLENDER_BUNDLE_PROFILE = 'blender-5.2.1-isolated-task-v1'


def fbx_command(blender, folder):
    """Only the engine-owned conversion script is executable Python input."""
    root = directory(Path(folder))
    executable = Path(blender)
    if not executable.is_absolute() or not executable.is_file():
        raise ValueError('motion_blender_unavailable')
    script = Path(__file__).resolve().parents[3] / 'tools/export-fbx-bvh.py'
    return [str(executable), '--background', '--factory-startup', '--disable-autoexec',
            '--python-use-system-env', '--python-exit-code', '1', '--python', str(script),
            '--', str(root / 'source.fbx'), str(root / 'source.bvh'), '--root-only']


def process_options(folder, *, environment=None):
    """Sanitize inherited resource overrides before enabling fixed Python flags.

    Blender initializes Python before executing the conversion script. Enabling
    system environment support is safe only with this cleaned environment: the
    fixed flags disable startup bytecode and user site packages, and no inherited
    Python path, home, startup hook or system/user Blender resource path survives.
    """
    root = directory(Path(folder))
    state = directory(root / 'blender-runtime', create=True)
    inherited = os.environ if environment is None else environment
    env = {key: value for key, value in inherited.items()
           if not key.upper().startswith(('PYTHON', 'BLENDER_'))
           and key.upper() not in {'OCIO', 'XDG_CACHE_HOME', 'CUDA_CACHE_PATH',
                                  'OPTIX_CACHE_PATH', 'MESA_SHADER_CACHE_DIR',
                                  'DXVK_STATE_CACHE_PATH', 'APPDATA', 'LOCALAPPDATA',
                                  'TEMP', 'TMP', 'TMPDIR'}}
    locations = {
        'BLENDER_USER_RESOURCES': 'user',
        'BLENDER_USER_CONFIG': 'user/config',
        'BLENDER_USER_SCRIPTS': 'user/scripts',
        'BLENDER_USER_EXTENSIONS': 'user/extensions',
        'BLENDER_USER_DATAFILES': 'user/datafiles',
        'APPDATA': 'user/appdata',
        'LOCALAPPDATA': 'user/localappdata',
        'TEMP': 'temporary', 'TMP': 'temporary', 'TMPDIR': 'temporary',
        'XDG_CACHE_HOME': 'cache', 'CUDA_CACHE_PATH': 'cache/cuda',
        'OPTIX_CACHE_PATH': 'cache/optix', 'MESA_SHADER_CACHE_DIR': 'cache/mesa',
        'DXVK_STATE_CACHE_PATH': 'cache/dxvk',
    }
    for key, relative in locations.items():
        env[key] = str(directory(state / relative, create=True))
    env.update(PYTHONDONTWRITEBYTECODE='1', PYTHONNOUSERSITE='1', PYTHONSAFEPATH='1')
    return dict(cwd=str(root), env=env, stdin=subprocess.DEVNULL, shell=False,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
