"""Expose every relation crossed by an isolated Runtime order trial."""
import argparse
from hashlib import sha256
from html import escape
import json
from pathlib import Path
from autospine_workbench.automation.storage_io import canonical_bytes


def assess(row, original_order, checks):
    trial = row['counterfactual']; region = row['region']; after = trial['after_slot']
    if not trial.get('restored_full_frame') or trial.get('selected') is not False:
        raise ValueError('order_trial_unrestored_or_selected')
    start, end = original_order.index(region), original_order.index(after)
    expected = list(original_order); expected.remove(region); expected.insert(expected.index(after)+1, region)
    crossed = original_order[start+1:end+1]
    if end <= start or trial['order'] != expected or trial['crossed_slots'] != crossed:
        raise ValueError('order_trial_unreported_relation_change')
    if expected.index(region) >= expected.index(row['body']): raise ValueError('order_trial_front_cover_changed')
    evidence = []
    visibility = trial.get('crossed_visibility', [])
    if len({v['slot'] for v in visibility}) != len(visibility) or any(v['slot'] not in crossed for v in visibility):
        raise ValueError('order_trial_visibility_inventory')
    for slot in crossed:
        found = [r for r in checks if (r['arm'], r['body'], r['time']) == (region, slot, row['time'])]
        if len(found) > 1: raise ValueError('order_trial_duplicate_evidence')
        status = found[0]['status'] if found else 'missing_evidence'
        evidence.append(dict(slot=slot, depth_status=status,
                             compatible=status in ('no_overlap', 'uniform_front_proxy')))
    uncertain = [e['slot'] for e in evidence if not e['compatible']]
    unchanged = [v['slot'] for v in visibility if v['changed_marginal_contribution_pixels'] == 0
                 and v['lost_contribution_pixels'] == 0 and v['gained_contribution_pixels'] == 0
                 and v['before_visible_pixels'] == v['after_visible_pixels']]
    return dict(time=row['time'], region=region, crossed=evidence,
                status='sample_proxy_compatible' if all(e['compatible'] for e in evidence) else 'unresolved_crossed_surface',
                changed_pixels=trial['full_frame_changed_pixels'], alpha_changes=trial['full_frame_alpha_changes'],
                selected_pixel_changes=trial['selected_pixel_changes'],
                crossed_visibility=visibility,
                unmeasured_depth_but_visibility_unchanged=[s for s in uncertain if s in unchanged])


def run(report_path, fixture_path, surfaces, output):
    if output.exists(): raise ValueError('output_exists')
    raw = report_path.read_bytes(); report = json.loads(raw)
    fixture_raw = fixture_path.read_bytes(); fixture = json.loads(fixture_raw)
    surface_raw = (surfaces/'report.json').read_bytes(); surface = json.loads(surface_raw)
    audit = json.loads((surfaces/'coverage-audit.json').read_bytes())
    if (report['fixture_sha256'] != sha256(fixture_raw).hexdigest()
            or report['skeleton_sha256'] != surface['skeleton_sha256']
            or surface['source_artifact_sha256'] != fixture['source_artifact_sha256']
            or audit['report_sha256'] != sha256(surface_raw).hexdigest()
            or report.get('negative_controls') != dict(order=True, image=True)
            or len(report['rows']) != len(fixture['rows'])): raise ValueError('order_trial_identity')
    checks = []
    for region in {r['region'] for r in report['rows']}:
        if Path(region).name != region or '/' in region or '\\' in region: raise ValueError('order_trial_path')
        data = (surfaces/(region+'.json')).read_bytes()
        if sha256(data).hexdigest() != audit['checkpoint_sha256'][region]: raise ValueError('order_trial_checkpoint')
        checks.extend(json.loads(data))
    rows = []
    for row, source in zip(report['rows'], fixture['rows']):
        if any(row[k] != source[k] for k in ('time','region','body','screenshot_sha256')):
            raise ValueError('order_trial_same_frame')
        rows.append(assess(row, source['draw_order'], checks))
    output.mkdir(parents=True, exist_ok=False); cards = []
    for index, (row, source) in enumerate(zip(rows, report['rows'])):
        for kind in ('before','after'):
            item = source['counterfactual'][kind+'_image']; name = item['file']
            if Path(name).name != name: raise ValueError('order_trial_image_path')
            data = (report_path.parent/name).read_bytes()
            if sha256(data).hexdigest() != item['sha256']: raise ValueError('order_trial_image_hash')
            (output/f'{index}-{kind}.png').write_bytes(data)
        crossed = '；'.join(escape(e['slot']+': '+e['depth_status']) for e in row['crossed'])
        visibility = '<br>'.join(f'{escape(v["slot"])}：可见贡献 {v["before_visible_pixels"]} → {v["after_visible_pixels"]}；贡献变化 {v["changed_marginal_contribution_pixels"]} 像素' for v in row['crossed_visibility'])
        cards.append(f'<section><h2>{row["time"]:g} 秒</h2><p>{crossed}</p><p>{visibility}</p><p>全帧变化 {row["changed_pixels"]} 像素，透明度变化 {row["alpha_changes"]} 像素。</p>'
            f'<div><figure><img src="{index}-before.png"><figcaption>原始排序</figcaption></figure>'
            f'<figure><img src="{index}-after.png"><figcaption>手部越过腿部，仍在前裙片后</figcaption></figure></div></section>')
    result = dict(rows=rows, report_sha256=sha256(raw).hexdigest(), surface_report_sha256=sha256(surface_raw).hexdigest(),
                  selected=False, authority='none', scope='isolated_source_times_not_continuous_candidate',
                  unresolved_samples=sum(r['status']=='unresolved_crossed_surface' for r in rows))
    (output/'report.json').write_bytes(canonical_bytes(result))
    (output/'index.html').write_text('<!doctype html><meta charset="utf-8"><title>手与腿局部排序试验</title>'
        '<style>body{font:16px system-ui;background:#15212b;color:#eef;padding:24px}section{margin:24px 0}section>div{display:flex;gap:16px}'
        'figure{margin:0;max-width:48%}img{width:100%;max-width:520px;background:#34424e}a{color:#7cceff}</style>'
        f'<h1>手与腿局部排序试验 · 未采用</h1><p>仅检查 {len(rows)} 个独立时刻，未制作连续动画。保留前方覆盖关系；{result["unresolved_samples"]} 个时刻存在未解决的跨越关系。</p>'
        '<p>没有修改网格或既有验收；原几何和投影异常仍保留。无新增透明度变化不等于遮挡正确。</p>'
        '<a href="report.json">跨越关系与像素变化证据</a>'+''.join(cards), encoding='utf-8')
    print(json.dumps(result))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('report', 'fixture', 'surfaces', 'output'): p.add_argument(name, type=Path)
    a = p.parse_args(); run(a.report, a.fixture, a.surfaces, a.output)
