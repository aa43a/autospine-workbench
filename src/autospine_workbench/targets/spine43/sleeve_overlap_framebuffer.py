"""Same-frame isolated triangle evidence is diagnostic, never automatic admission."""
from html import escape

MODES={'full','first','second','pair','without_first','without_second'}


def summaries(capture, source):
    if capture.get('scope')!='software_visible_peak_pairs_setup_and_same_frame' or capture.get('status')!='needs_review':
        raise ValueError('overlap_capture_scope')
    expected={t['animation']:t['visible_peak'] for t in source['tracks'] if t['visible_peak'] is not None}
    selected={}
    for item in capture['captures']:
        name,phase=item['animation'],item['phase'];key=name,phase
        if name not in expected or phase not in ('setup','peak') or key in selected:raise ValueError('overlap_capture_inventory')
        peak=expected[name]
        if (item['pair']!=peak['triangles'] or item['software_peak']!=peak
                or item['time']!=(0 if phase=='setup' else peak['time']) or item['index']/128!=item['time']):
            raise ValueError('overlap_capture_source')
        images=item['images']
        if len(images)!=6 or {i['mode'] for i in images}!=MODES:raise ValueError('overlap_capture_images')
        count=item['dual_alpha8_pixels'];samples=item['dual_samples']
        if type(count) is not int or count<0 or count!=len(samples):raise ValueError('overlap_capture_counts')
        for sample in samples:
            for name in ('first_alpha','second_alpha'):
                if type(sample[name]) is not int or not 8<=sample[name]<=255:raise ValueError('overlap_capture_alpha')
            if type(sample['alpha_increase']) is not int or not -255<=sample['alpha_increase']<=255:
                raise ValueError('overlap_capture_alpha')
        if item['max_alpha_increase']!=max([0]+[s['alpha_increase'] for s in samples]):raise ValueError('overlap_capture_alpha')
        selected[key]=item
    if set(selected)!={(n,p) for n in expected for p in ('setup','peak')}:raise ValueError('overlap_capture_inventory')
    rows=[]
    for name in sorted(expected):
        setup,peak=selected[name,'setup'],selected[name,'peak']
        rows.append(dict(animation=name,setup_pixels=setup['dual_alpha8_pixels'],peak_pixels=peak['dual_alpha8_pixels'],
            excess_pixels=max(0,peak['dual_alpha8_pixels']-setup['dual_alpha8_pixels']),
            max_alpha_increase=peak['max_alpha_increase'],status='needs_review',authority='none',production_authorized=False))
    return rows


def render(capture, rows, image_url):
    if not rows:return '<p>软件报告未给出可见双覆盖峰值；未据此判定全域无重叠。</p>'
    parts=['<h3>同帧三角形双覆盖诊断</h3><p>六种视图仅用于归因。移除三角形的差异不等于视觉损伤程度，不能据此自动删面。</p>']
    labels={'full':'完整网格','first':'三角形 A','second':'三角形 B','pair':'A+B 原顺序合成',
        'without_first':'完整网格移除 A','without_second':'完整网格移除 B'}
    for row in rows:
        parts.append(f'<p>{escape(row["animation"])}：setup {row["setup_pixels"]} → 峰值 {row["peak_pixels"]} 个双覆盖像素；合成 alpha 最大增加 {row["max_alpha_increase"]}。</p>')
        for sample in capture['captures']:
            if sample['animation']!=row['animation'] or sample['phase']!='peak':continue
            parts.append('<div>')
            for img in sample['images']:
                src=escape(image_url(img['file']),quote=True)
                parts.append(f'<figure><img style="image-rendering:pixelated" src="{src}"><figcaption>{labels[img["mode"]]}</figcaption></figure>')
            parts.append('</div>')
    return ''.join(parts)
