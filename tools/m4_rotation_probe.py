"""Inspect exact frozen source directions without modifying any animation."""
import argparse
from html import escape
import json
from pathlib import Path

from m4_motion_cohort import api, digest, save
from autospine_workbench.motion_bundle_reader import VerifiedMotionBundleReader
from autospine_workbench.bvh_parser import parse_bvh
from autospine_workbench.targets.character43.rotation_diagnostics import summarize, bvh_vectors, kimodo_vectors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('plan', type=Path); parser.add_argument('output', type=Path)
    args = parser.parse_args()
    plan = json.loads(args.plan.read_text(encoding='utf-8'))
    args.output.mkdir(parents=True, exist_ok=True)
    reader = VerifiedMotionBundleReader(Path('workspace'))
    cards = []
    for source in plan['motions']:
        job = api('http://127.0.0.1:8918', '/api/motions/'+source['job_id'])
        if job['source_sha256'] != source['sha256'] or job['view'] != source['view']:
            raise ValueError('frozen_source_changed')
        identity = job['result']['motion']
        bundle = reader.load(identity['clip_sha256'], identity['bundle_sha256'])
        mapping = json.loads((bundle.path/'map.json').read_bytes())
        data = (kimodo_vectors(bundle.raw_npz, bundle.kimodo_source, mapping)
                if bundle.source_kind == 'kimodo_npz' else bvh_vectors(parse_bvh(bundle.raw_bvh), mapping))
        report = summarize(*data)
        report.update(source_job_id=source['job_id'], source_sha256=source['sha256'],
                      motion_identity=identity, plan_sha256=digest(plan), view=source['view'])
        save(args.output/(source['id']+'.json'), report)
        rows = []
        for row in report['records']:
            events = row['events']
            details = ''.join('<li>'+escape(f"{e['time']:.3f}s / frame {e['frame']}: {e['reason']}")+'</li>' for e in events)
            rows.append('<details><summary>'+escape(row['role'])+f' · {len(events)} samples</summary><ul>'+details+'</ul></details>')
        cards.append('<section><h2>'+escape(source['id'])+'</h2>'+''.join(rows)+'</section>')
        print(source['id'], sum(len(r['events']) for r in report['records']), flush=True)
    (args.output/'index.html').write_text('''<!doctype html><meta charset="utf-8"><title>动作旋转定位</title>
<style>body{background:#101923;color:#e7eff6;font:16px system-ui;max-width:1100px;margin:30px auto}section{padding:16px;border:1px solid #456;margin:16px 0}details{padding:8px}</style>
<h1>源动作旋转与投影退化定位</h1><p>角度跨界不等于错误；投影接近零时不推断旋转圈数。
以下只检查离散源帧方向，尚未检查目标局部角度、轴向扭转或实际画面，也未修改动画。</p>
<p>angle_branch_crossing：角度跨界；projection_direction_unreliable：投影方向不可靠；half_turn_direction_ambiguous：半圈方向无法确定。</p>'''+''.join(cards), encoding='utf-8')


if __name__ == '__main__': main()
