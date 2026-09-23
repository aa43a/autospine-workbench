"""Summarize exact partition candidates without rerunning or approving captures."""
import argparse
import json
import math
from pathlib import Path
import shutil
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.targets.character43.affine_pose import sample


def area(points, triangle):
    a, b, c = (points[i] for i in triangle)
    return ((b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0]))/2


def summarize(root):
    probe = json.loads((root/'probe.json').read_bytes())
    results = []
    for label in ('rigid', 'transported'):
        folder = root/label
        receipt = json.loads((folder/'report.json').read_bytes())
        artifact = receipt['candidate_bundle_sha256']
        runtime = json.loads((folder/'runtime/report.json').read_bytes())
        if runtime['bundle_sha256'] != artifact:
            raise ValueError('partition_runtime_identity_mismatch')
        files = AnimatedStore(folder/'isolated-store').read(artifact)
        doc = json.loads(files['skeleton.json'])
        setup = json.loads(files['rig-setup-reference.json'])['vertices']['layer-004']
        indices = doc['skins'][0]['attachments']['layer-004']['layer-004']['triangles']
        triangles = [indices[i*3:i*3+3] for i in probe['partition']['selected_triangles']]
        rows = []
        for time in probe['times']:
            points = sample(doc, 'external-motion', time)[0]['layer-004']
            ratios = [area(points,t)/area(setup,t) for t in triangles]
            rows.append(dict(time=time, min_area_ratio=min(ratios), max_area_ratio=max(ratios),
                inversions=sum(r<=0 for r in ratios), boundary_gap_px=max(
                    math.dist(points[a],points[b]) for a,b in probe['partition']['boundary_pairs'])))
        geometry = json.loads((folder/'runtime/deformation.json').read_bytes())
        results.append(dict(label=label, artifact=artifact, rows=rows,
            runtime_numeric_passed=runtime['passed'], geometry_passed=geometry['passed']))
    return dict(authority='none', selected=False, scope='three_key_times_only_not_full_animation',
        parent=probe['parent'], results=results,
        decision='stop_boundary_transport_parameter_expansion',
        next_requirement='independent_region_connection_or_pose_material_needed')


def write(root):
    result = summarize(root)
    (root/'summary.json').write_bytes(canonical_bytes(result))
    views = [dict(url=f"{r['label']}/runtime/player.html",artifact=r['artifact'],
        geometry_passed=r['geometry_passed'], runtime_status='numeric_passed' if r['runtime_numeric_passed'] else 'failed',
        unreliable_samples='未统计') for r in result['results']]
    comparison = dict(title='独立手部与腕部过渡：失败定位',
        headings=['独立手部：检查边界分离','边界拉回：检查腕部折叠'],
        note='仅捕获 0、2、3.966667 秒。其余时间是未验收插值。边界重合不代表形状正确；两方案均未采用。',
        rows=[dict(label='Alice 独立手部关键姿态', views=views)])
    (root/'comparison.json').write_bytes(canonical_bytes(comparison))
    for source, target in [('m4-reach-comparison.html','index.html'),('m4-reach-comparison.js','comparison.js')]:
        shutil.copy2(Path(__file__).parent/source, root/target)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('root', type=Path)
    print(json.dumps(write(parser.parse_args().root)))
