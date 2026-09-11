"""Compare one verified runtime setup frame with the exact source texture inventory."""
import argparse
from hashlib import sha256
import json
from pathlib import Path

from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.targets.character43.setup_raster import compare_setup


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('bundle'); parser.add_argument('capture'); parser.add_argument('output')
    args = parser.parse_args(); bundle = Path(args.bundle).resolve(); capture = Path(args.capture)
    files = AnimatedStore(bundle.parent.parent.parent).read(bundle.name)
    report_raw = (capture/'report.json').read_bytes(); capture_report = json.loads(report_raw)
    if capture_report['bundle_sha256'] != bundle.name:
        raise ValueError('character_capture_source_mismatch')
    ref = json.loads(files['numeric-reference.json']); doc = json.loads(files['skeleton.json'])
    if ref['skeleton_sha256'] != sha256(files['skeleton.json']).hexdigest():
        raise ValueError('character_reference_source_mismatch')
    shot = next(s for s in capture_report['screenshots'] if s['index']==0)
    relative = Path(shot['file'])
    if relative.is_absolute() or '..' in relative.parts:
        raise ValueError('character_capture_path')
    png = (capture/relative).read_bytes()
    if sha256(png).hexdigest()!=shot['sha256']:
        raise ValueError('character_capture_frame_mismatch')
    frame = ref['animations'][shot['animation']][0]
    if frame['time'] != 0:
        raise ValueError('character_capture_not_setup')
    result, source = compare_setup(doc, frame, files, png, capture_report['info'])
    result.update(bundle_sha256=bundle.name, capture_report_sha256=sha256(report_raw).hexdigest(),
                  frame_sha256=shot['sha256'], animation=shot['animation'])
    output = Path(args.output); output.mkdir(parents=True, exist_ok=True)
    for name, raw in {'source.png':source, 'runtime.png':png,
                      'report.json':json.dumps(result,ensure_ascii=False,indent=2).encode(),
                      'index.html':('<!doctype html><meta charset="utf-8"><title>整角色 setup 对照</title>'
                        '<style>body{background:#182531;color:white;font:16px sans-serif}main{display:flex}figure{margin:8px}'
                        'img{width:42vw;background:repeating-conic-gradient(#34424e 0% 25%,#263540 0% 50%) 0/20px 20px}</style>'
                        '<h1>源 RGBA / 官方 Runtime setup 对照</h1><p>透明度保持原值；尚未评估动态遮挡和接触。</p>'
                        '<a href="report.json">定量报告</a><main><figure><img src="source.png"><figcaption>源纹理顺序合成</figcaption></figure>'
                        '<figure><img src="runtime.png"><figcaption>官方 WebGL</figcaption></figure></main>').encode()}.items():
        path = output/name
        if path.exists() and path.read_bytes()!=raw:
            raise ValueError('character_setup_output_exists')
        if not path.exists(): path.write_bytes(raw)
    print(json.dumps({k:v for k,v in result.items() if k!='records'},ensure_ascii=False))


if __name__=='__main__': main()
