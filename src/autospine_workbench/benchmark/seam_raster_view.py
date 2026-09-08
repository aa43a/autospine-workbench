"""Local report for independent native alpha corridor diagnostics."""
from html import escape


def render(report):
    rows=[]
    for before,after,conflict in zip(report['before']['relations'],report['after']['relations'],report['conflicts']):
        rows.append('<section><h2>'+escape(after['driver']+' ↔ '+after['follower'])+'</h2>'
            +f'<p>对应 {conflict["pair_count"]}；互为最近 {conflict["reciprocal_pair_count"]}；多对一目标最大分歧 {conflict["max_target_spread_px"]:.3f} px。未删除对应。</p>'
            +f'<p>走廊内空白像素峰值：{before["max_gap_pixels"]} → {after["max_gap_pixels"]}；双层覆盖像素峰值：{before["max_overlap_pixels"]} → {after["max_overlap_pixels"]}。</p>'
            +'<div class="pair">'+''.join('<figure><img src="'+stage+'/'+escape(r['heatmap'],quote=True)+'"><figcaption>'+title+f' · 空白最多时刻 {r["worst_time"]:.3f}s</figcaption></figure>' for stage,title,r in [('before','原连续候选',before),('after','局部过渡候选',after)])+'</div></section>')
    return '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>Alpha 接缝栅格对照</title><style>body{max-width:1080px;margin:28px auto;background:#eef1f5;color:#243449;font:16px/1.6 system-ui}section{padding:18px;background:white;margin:18px 0}.pair{display:flex;flex-wrap:wrap}figure{margin:12px}img{min-width:240px;max-width:450px;image-rendering:pixelated;border:1px solid #aaa}aside{background:#fff0cc;padding:16px}</style><h1>Alpha 接缝栅格与对应冲突</h1><aside>CPU 原生像素、双线性 alpha 诊断；仅覆盖候选对应之间的走廊，不是完整 Runtime 栅格认证。红：走廊空白；蓝/绿：两侧素材；紫：重叠。左右图各自选择空白最多时刻，不能直接视为同帧差分。所有决定仍待复核。</aside>'+(''.join(rows) or '<p>没有可观测跨附件对应；不计为接缝通过。</p>')+'</html>'
