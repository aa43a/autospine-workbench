"""Read-only discovery of fixed official capture tools; explicit choices never fall back."""
import hashlib
import json
import os
from pathlib import Path
import shutil

from .sleeve_workflow import inventory
from .storage_io import directory
from ..safe_input_files import read_real_file


VERSION = '4.3.13'
DEPENDENCIES_ENV = 'AUTOSPINE_CAPTURE_DEPENDENCIES'
BROWSER_ENV = 'AUTOSPINE_CAPTURE_BROWSER'
NODE_ENV = 'AUTOSPINE_CAPTURE_NODE'
STANDARD_BROWSERS = (
    Path('C:/Program Files/Google/Chrome/Application/chrome.exe'),
    Path('C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'),
)


def _configured(name, *, folder=False):
    if name not in os.environ:
        return None
    raw = os.environ[name]
    path = Path(raw)
    if not raw or raw != raw.strip() or not path.is_absolute():
        raise ValueError('sleeve_capture_configuration_invalid')
    try:
        if folder:
            return directory(path)
        directory(path.parent)
        read_real_file(path, 256 << 20, 'capture executable')
        return path
    except (OSError, RuntimeError, ValueError) as exc:
        raise ValueError('sleeve_capture_configuration_invalid') from exc


def dependencies(workspace):
    """Return the chosen dependency tree, retaining the old workspace default."""
    configured = _configured(DEPENDENCIES_ENV, folder=True)
    if configured is not None:
        return configured
    path = Path(workspace)/'tmp/spine43-verification'
    return directory(path) if path.is_dir() else None


def _package(root, name):
    package = directory(Path(root)/'node_modules/@esotericsoftware'/name)
    metadata = json.loads(read_real_file(package/'package.json', 1 << 20, 'capture package'))
    if metadata.get('name') != '@esotericsoftware/'+name or metadata.get('version') != VERSION:
        raise ValueError('sleeve_capture_runtime_version')
    required = 'dist/iife/spine-webgl.js' if name == 'spine-webgl' else 'dist/index.js'
    read_real_file(package/required, 32 << 20, 'capture runtime')
    return package


def webgl_package(workspace):
    """Playback requires fixed WebGL bytes, independently of browser/Node capture."""
    root = dependencies(workspace)
    if root is None:
        return None
    path = root/'node_modules/@esotericsoftware/spine-webgl'
    if not path.exists() and DEPENDENCIES_ENV not in os.environ:
        return None
    return _package(root, 'spine-webgl')


def runtime_core(workspace):
    root = dependencies(workspace)
    if root is None:
        return None
    path = root/'node_modules/@esotericsoftware/spine-core'
    if not path.exists() and DEPENDENCIES_ENV not in os.environ:
        return None
    return _package(root, 'spine-core')


def node_executable():
    configured = _configured(NODE_ENV)
    if configured is not None:
        return str(configured)
    found = shutil.which('node')
    if not found:
        raise ValueError('sleeve_capture_node_missing')
    return str(Path(found).resolve())


def node_identity():
    node = Path(node_executable())
    raw = read_real_file(node, 256 << 20, 'capture Node')
    return dict(sha256=hashlib.sha256(raw).hexdigest(), size_bytes=len(raw))


def _capture_packages(root):
    runtime = _package(root, 'spine-webgl')
    core = _package(root, 'spine-core')
    playwright = directory(Path(root)/'node_modules/playwright-core')
    metadata = json.loads(read_real_file(playwright/'package.json', 1 << 20, 'capture package'))
    if metadata.get('name') != 'playwright-core' or not isinstance(metadata.get('version'), str):
        raise ValueError('sleeve_capture_environment_missing')
    read_real_file(playwright/'index.mjs', 1 << 20, 'capture Playwright')
    return runtime, core, playwright


def identity(dependencies, browser):
    root = directory(dependencies)
    runtime, core, playwright = _capture_packages(root)
    browser_raw = read_real_file(Path(browser), 256 << 20, 'capture browser')
    return dict(runtime=inventory(runtime), core=inventory(core), playwright=inventory(playwright),
        node=node_identity(), browser_sha256=hashlib.sha256(browser_raw).hexdigest(),
        profile='official-webgl-swiftshader-native-v1')


def discover(workspace):
    # Validate explicit choices even when another component is unavailable. An
    # invalid saved path must remain actionable rather than silently using PATH.
    configured_browser = _configured(BROWSER_ENV)
    configured_node = _configured(NODE_ENV)
    root = dependencies(workspace)
    if root is None:
        return []
    required = (root/'node_modules/@esotericsoftware/spine-webgl/package.json',
                root/'node_modules/@esotericsoftware/spine-core/package.json',
                root/'node_modules/playwright-core/index.mjs')
    if not all(path.is_file() for path in required):
        if DEPENDENCIES_ENV in os.environ:
            raise ValueError('sleeve_capture_environment_missing')
        return []
    _capture_packages(root)
    if configured_node is None and not shutil.which('node'):
        return []
    browser = configured_browser or next((p for p in STANDARD_BROWSERS if p.is_file()), None)
    if browser is None:
        return []
    return ['--capture-dependencies', str(root), '--capture-browser', str(browser)]
