"""Localize unobservable contact edges in exact exported texture coordinates."""
import argparse
import base64
import hashlib
from html import escape
import io
import json
import math
from pathlib import Path

from PIL import Image
from autospine_workbench.safe_input_files import read_real_file, strict_json_object
from autospine_workbench.resolved_project import canonical_sha256
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.manifest_artifacts import require_safe_token


def read(path):
    value = strict_json_object(read_real_file(path, 128 << 20, 'interface input'), 'interface input')
    if canonical_sha256(value) != path.stem:
        raise ValueError('interface_document_identity')
    return value


def sample_edge(a, b, alpha):
    width, height = alpha.size
    count = max(1, math.ceil(math.dist(a, b)))
    result = []
    for i in range(count):
        u = (i + .5) / count
        x, y = [math.floor(a[k]*(1-u)+b[k]*u) for k in (0, 1)]
        center = alpha.getpixel((x, y)) if 0 <= x < width and 0 <= y < height else None
        margin = alpha.crop((x-1, y-1, x+2, y+2)).getextrema()[0] if 1 <= x < width-1 and 1 <= y < height-1 else None
        result.append(dict(u=u, pixel=[x, y], alpha=center, margin_alpha=margin))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--contacts', type=Path, required=True)
    parser.add_argument('--export', dest='bundle_root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    contacts = read(args.contacts)
    source = read(args.bundle_root/(contacts['source_sha256']+'.json'))
    if (contacts['schema'] != 'autospine.sleeve-contact-coverage/v1'
            or source['schema'] != 'autospine.sleeve-export-report/v1'
            or any(d.get('authority') != 'none' or d.get('production_authorized') is not False for d in (source, contacts))
            or source['project_id'] != contacts['project_id']):
        raise ValueError('interface_project_identity')
    records, views = [], []
    for row in contacts['records']:
        name = row['layer_id']+'-'+row['component_id']
        require_safe_token(name, 'sleeve region')
        exported = next(r for r in source['records'] if r['layer_id'] == row['layer_id'] and r['component_id'] == row['component_id'])
        if exported['files'] != row['asset_sha256']:
            raise ValueError('interface_asset_identity')
        files = {}
        for filename, digest in exported['files'].items():
            path = args.bundle_root/name/filename
            if (args.bundle_root/name).resolve() not in path.resolve().parents:
                raise ValueError('interface_asset_path')
            raw = read_real_file(path, 128 << 20, 'interface asset')
            if hashlib.sha256(raw).hexdigest() != digest:
                raise ValueError('interface_asset_changed')
            files[filename] = raw
        doc = strict_json_object(files['skeleton.json'], 'skeleton')
        attachment = doc['skins'][0]['attachments'][name][name]
        raw = files['images/'+name+'.png']
        alpha = Image.open(io.BytesIO(raw)).convert('RGBA').getchannel('A')
        width, height = alpha.size
        points = [[attachment['uvs'][i]*width, attachment['uvs'][i+1]*height] for i in range(0, len(attachment['uvs']), 2)]
        for edge in row['interfaces']:
            if edge['samples']:
                continue
            a, b = [points[i] for i in edge['edge']]
            samples = sample_edge(a, b, alpha)
            if any(s['margin_alpha'] is not None and s['margin_alpha'] >= 224 for s in samples):
                raise ValueError('interface_observability_mismatch')
            record = dict(layer_id=row['layer_id'], edge=edge['edge'], triangles=edge['triangles'], samples=samples,
                          max_center_alpha=max((s['alpha'] for s in samples if s['alpha'] is not None), default=None))
            records.append(record)
            x, y = min(a[0], b[0])-20, min(a[1], b[1])-20
            w, h = abs(a[0]-b[0])+40, abs(a[1]-b[1])+40
            url = 'data:image/png;base64,'+base64.b64encode(raw).decode()
            views.append(f'<h2>{escape(name)} · {edge["edge"]}</h2><p>最高中心 alpha {record["max_center_alpha"]}；没有满足原 3×3 不透明边距的采样。</p>'
                         f'<svg viewBox="{x} {y} {w} {h}"><image href="{url}" width="{width}" height="{height}"/>'
                         f'<path d="M {a[0]} {a[1]} L {b[0]} {b[1]}" fill="none" stroke="orange" stroke-width=".4"/></svg>')
    result = dict(project_id=contacts['project_id'], contact_sha256=args.contacts.stem,
                  export_sha256=contacts['source_sha256'], authority='none', production_authorized=False,
                  scope='source_texture_only_no_runtime_gate_change', records=records)
    args.output.mkdir(parents=True, exist_ok=True)
    digest = canonical_sha256(result)
    (args.output/(digest+'.json')).write_bytes(canonical_bytes(result))
    (args.output/'index.html').write_text('<!doctype html><meta charset="utf-8"><style>body{background:#172330;color:white;font:18px system-ui}svg{width:48%;height:400px;background:#394856}a{color:#9df}</style><h1>源贴图接口定位</h1><p>橙线为原探针边，不改变门槛，不把透明接口自动判为通过。</p>'+''.join(views)+f'<p><a href="{digest}.json">原始采样</a></p>', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=True))


if __name__ == '__main__':
    main()
