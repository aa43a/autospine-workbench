"""Same-frame isolated triangle evidence is diagnostic, never automatic admission."""
from html import escape
import math
from ...automation.sleeve_motion_inventory import explicit_frame_count

MODES={'full','first','second','pair','without_first','without_second'}


def summaries(capture, source):
    if capture.get('scope')!='software_visible_peak_pairs_setup_and_same_frame' or capture.get('status')!='needs_review':
        raise ValueError('overlap_capture_scope')
    expected={t['animation']:t['visible_peak'] for t in source['tracks'] if t['visible_peak'] is not None}
    frame_count=explicit_frame_count(source) if 'motion_profile' in source else 257
    rate=(frame_count-1)/2
    selected={}
    for item in capture['captures']:
        name,phase=item['animation'],item['phase'];key=name,phase
        if name not in expected or phase not in ('setup','peak') or key in selected:raise ValueError('overlap_capture_inventory')
        peak=expected[name]
        if (item['pair']!=peak['triangles'] or item['software_peak']!=peak
                or item['time']!=(0 if phase=='setup' else peak['time']) or type(item['index']) is not int
                or not 0<=item['index']<frame_count or item['index']/rate!=item['time']):
            raise ValueError('overlap_capture_source')
        images=item['images']
        if len(images)!=6 or {i['mode'] for i in images}!=MODES:raise ValueError('overlap_capture_images')
        count=item['dual_alpha8_pixels'];samples=item['dual_samples']
        if type(count) is not int or count<0 or count!=len(samples):raise ValueError('overlap_capture_counts')
        roi=item['roi']
        if (any(type(roi[k]) not in (int,float) or not math.isfinite(roi[k]) for k in ('x','y','width','height'))
                or roi['width']<=0 or roi['height']<=0):raise ValueError('overlap_capture_roi')
        for sample in samples:
            xy=sample['world_xy']
            if (not isinstance(xy,list) or len(xy)!=2 or any(type(v) not in (int,float) or not math.isfinite(v) for v in xy)
                    or not roi['x']<=xy[0]<roi['x']+roi['width'] or not roi['y']<=xy[1]<roi['y']+roi['height']):
                raise ValueError('overlap_capture_location')
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


def render(capture, rows, image_url, info=None):
    if info and (any(type(info[k]) not in (int,float) or not math.isfinite(info[k]) for k in ('width','height','left','bottom'))
                 or info['width']<=0 or info['height']<=0):raise ValueError('overlap_capture_viewport')
    if not rows:return '<p>软件报告未给出可见双覆盖峰值；未据此判定全域无重叠。</p>'
    parts=['<h3>同帧三角形双覆盖诊断</h3><p>六种视图仅用于归因。移除三角形的差异不等于视觉损伤程度，不能据此自动删面。</p>']
    labels={'full':'完整网格','first':'三角形 A','second':'三角形 B','pair':'A+B 原顺序合成',
        'without_first':'完整网格移除 A','without_second':'完整网格移除 B'}
    for row in rows:
        parts.append(f'<p>{escape(row["animation"])}：setup {row["setup_pixels"]} → 峰值 {row["peak_pixels"]} 个双覆盖像素；合成 alpha 最大增加 {row["max_alpha_increase"]}。</p>')
        for sample in capture['captures']:
            if sample['animation']!=row['animation'] or sample['phase']!='peak':continue
            if sample.get('context') and info:
                roi=sample['roi'];x=roi['x']-info['left'];y=info['height']-(roi['y']-info['bottom'])-roi['height']
                src=escape(image_url(sample['context']['file']),quote=True)
                parts.append(f'<figure><div style="position:relative"><img style="display:block" src="{src}"><svg style="position:absolute;inset:0;width:100%;height:100%;pointer-events:none" viewBox="0 0 {info["width"]} {info["height"]}"><rect x="{x}" y="{y}" width="{roi["width"]}" height="{roi["height"]}" fill="none" stroke="#ffb000" stroke-width="3"/></svg></div><figcaption>同帧全袖 · 框内为检查区域</figcaption></figure>')
                full=next(i for i in sample['images'] if i['mode']=='full');src=escape(image_url(full['file']),quote=True)
                marks=''.join(f'<rect x="{s["world_xy"][0]-roi["x"]-.5}" y="{roi["height"]-(s["world_xy"][1]-roi["y"])-.5}" width="1" height="1" fill="none" stroke="#00ffff" stroke-width=".3"/>' for s in sample['dual_samples'])
                parts.append(f'<figure><div style="position:relative"><img style="image-rendering:pixelated;display:block" src="{src}"><svg style="position:absolute;inset:0;width:100%;height:100%;pointer-events:none" viewBox="0 0 {roi["width"]} {roi["height"]}">{marks}</svg></div><figcaption>同帧局部 · 青框为双覆盖像素</figcaption></figure>')
            parts.append('<details><summary>展开六种隔离视图（仅诊断）</summary>')
            parts.append('<div>')
            for img in sample['images']:
                src=escape(image_url(img['file']),quote=True)
                parts.append(f'<figure><img style="image-rendering:pixelated" src="{src}"><figcaption>{labels[img["mode"]]}</figcaption></figure>')
            parts.append('</div></details>')
    return ''.join(parts)
