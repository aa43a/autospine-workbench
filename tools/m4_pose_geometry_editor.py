"""Export a version-bound pose editor; never modify the source candidate."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import shutil

from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.targets.character43.pose_geometry_patch import compile_patch


def export(source, template, output):
    receipt = json.loads((source/'report.json').read_bytes())
    runtime = json.loads((source/'runtime/report.json').read_bytes())
    artifact = receipt['candidate_bundle_sha256']
    if runtime['bundle_sha256'] != artifact or runtime['passed'] is not True:
        raise ValueError('pose_editor_runtime_identity')
    files = AnimatedStore(source/'isolated-store').read(artifact)
    document = json.loads(files['skeleton.json'])
    request = json.loads(template.read_bytes())
    compile_patch(document, request)  # Validate the scope with the same compiler.
    assets = source/'runtime/player-assets'
    scene = json.loads((assets/'scene.json').read_bytes())
    if scene['artifact_sha256'] != artifact or scene['skeleton'] != document:
        raise ValueError('pose_editor_scene_identity')
    raw = (assets/'runtime.js').read_bytes()
    if sha256(raw).hexdigest() != runtime['runtime_sha256']:
        raise ValueError('pose_editor_runtime_changed')
    output.mkdir(parents=True, exist_ok=False)
    for src, dest in [('pose-geometry-editor.html', 'index.html'),
                      ('pose-geometry-editor.css', 'editor.css'), ('pose-geometry-editor.js', 'editor.js')]:
        shutil.copyfile(Path('web')/src, output/dest)
    shutil.copyfile(assets/'scene.json', output/'scene.json')
    shutil.copyfile(Path('web/modules/pose-geometry-metrics.js'), output/'pose-geometry-metrics.js')
    (output/'runtime.js').write_bytes(raw)
    # Template authoring is not implicitly applied or accepted. Import explicitly.
    (output/'editor-config.json').write_bytes(canonical_bytes(dict(
        artifact=artifact, request=dict(request, poses=[]), authority='none', selected=False)))
    (output/'README.txt').write_text(
        '通过本地 HTTP 服务打开 index.html。拖动顶点后草稿按候选版本保存到浏览器，支持导出/导入。\n'
        '未自动导入模板中的姿态；模板只限定候选、部件、顶点和区间。\n'
        '导出的 JSON 可交给 tools/m4_pose_geometry_probe.py 构建独立候选并执行 Runtime 检查。\n'
        '实时预览不代表几何、接缝或视觉验收。原候选与历史记录不改。\n', encoding='utf-8')
    print(json.dumps(dict(artifact=artifact, slot=request['slot'], vertices=len(request['vertices']))))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('source', type=Path)
    parser.add_argument('template', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    export(args.source, args.template, args.output)
