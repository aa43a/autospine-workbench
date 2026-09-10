"""Discover existing local capture dependencies; never install or download them."""
import hashlib
import json
from pathlib import Path
from .sleeve_workflow import inventory


def identity(dependencies, browser):
    root=Path(dependencies).resolve();browser=Path(browser).resolve()
    package=root/'node_modules/@esotericsoftware/spine-webgl'
    doc=json.loads((package/'package.json').read_bytes())
    if doc.get('name')!='@esotericsoftware/spine-webgl' or doc.get('version')!='4.3.13':
        raise ValueError('sleeve_capture_runtime_version')
    playwright=root/'node_modules/playwright-core'
    if not (playwright/'index.mjs').is_file() or not browser.is_file():raise ValueError('sleeve_capture_environment_missing')
    return dict(runtime=inventory(package),playwright=inventory(playwright),
        browser_sha256=hashlib.sha256(browser.read_bytes()).hexdigest(),profile='official-webgl-swiftshader-native-v1')


def discover(workspace):
    dependencies=Path(workspace)/'tmp/spine43-verification'
    if not (dependencies/'node_modules/@esotericsoftware/spine-webgl/package.json').is_file():return []
    if not (dependencies/'node_modules/playwright-core/index.mjs').is_file():return []
    for browser in (Path('C:/Program Files/Google/Chrome/Application/chrome.exe'),
                    Path('C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe')):
        if browser.is_file():return ['--capture-dependencies',str(dependencies),'--capture-browser',str(browser)]
    return []
