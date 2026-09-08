"""Same timestamp and same rectangle heatmaps, without implicit acceptance."""
from html import escape


def render(report):
    rows=[]
    for relation,segment in zip(report['raster']['relations'],report['segments']):
        rows.append('<section><h2>'+escape(relation['driver']+' ↔ '+relation['follower'])+'</h2>'
            +f'<p>共同走廊空白峰值 {relation["max_gap_pixels"][0]} → {relation["max_gap_pixels"][1]}；出现新增空白的帧 {relation["frames_with_new_gap"]}/61。</p>'
            +'<p>'+escape('片段：腿侧 '+', '.join(c['status'] for c in segment['driver_components'])+'；附件侧 '+', '.join(c['status'] for c in segment['follower_components']))+'</p>'
            +f'<p>以下三图使用同一时刻 {relation["selected_time"]:.3f}s、同一矩形、同一像素网格。</p><div class="pair">'
            +''.join('<figure><img src="'+escape(relation['heatmap_prefix']+'-'+suffix+'.png',quote=True)+'"><figcaption>'+title+'</figcaption></figure>' for suffix,title in [('before','原局部过渡'),('after','局部重配'),('difference','红：新增空白；绿：填补；橙：共同空白')])+'</div></section>')
    return '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>同帧接缝对照</title><style>body{max-width:1150px;margin:24px auto;background:#eef1f5;color:#243449;font:16px/1.6 system-ui}section{background:white;padding:18px;margin:18px 0}.pair{display:flex;flex-wrap:wrap}figure{margin:10px}img{width:300px;image-rendering:pixelated;border:1px solid #aaa}aside{background:#fff0cc;padding:16px}</style><h1>同帧接缝栅格与边界片段</h1><aside>CPU 原生像素诊断。每帧取两版走廊并集，再在相同区域对照空白与重叠；并非官方 Runtime 接缝认证。简单像素链仅是形状约束候选，未批准配对或采用。</aside>'+(''.join(rows) or '<p>没有跨附件对应；不计为通过。</p>')+'</html>'
