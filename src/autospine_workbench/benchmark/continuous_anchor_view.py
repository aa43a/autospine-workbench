"""Same-frame raster review for remapped versus continuous-anchor animations."""
from html import escape


def render(report):
    cards=[]
    for r in report['common_frame_comparison']['relations']:
        cards.append(f'<section><h2>{escape(r["driver"])} ↔ {escape(r["follower"])}</h2>'
                     f'<p>共同走廊空白峰值 {r["max_gap_pixels"][0]} → {r["max_gap_pixels"][1]}；新增空白帧 {r["frames_with_new_gap"]}/61；以下三图均为 {r["selected_time"]:.3f}s。</p><div>'
                     +''.join(f'<figure><img src="continuous-raster/{escape(r["heatmap_prefix"])}-{suffix}.png"><figcaption>{label}</figcaption></figure>' for suffix,label in
                              [('before','原局部重配'),('after','连续锚点 Bake'),('difference','红：新增空白；绿：填补；橙：共同空白')])+'</div></section>')
    return '<!doctype html><meta charset="utf-8"><title>连续锚点 Bake 栅格对照</title><style>body{font:16px system-ui;background:#edf1f5;color:#20344b;margin:24px}section{background:white;padding:20px;margin:16px 0}section div{display:flex;flex-wrap:wrap}figure{margin:10px}img{width:300px;image-rendering:pixelated}</style><h1>连续锚点 Bake 栅格对照</h1><p>沿用原局部平滑求解器，仅替换可行组目标锚点。保留原对应验算；CPU 走廊探针不是官方 Runtime 接缝认证，结果尚未采用。</p>'+(''.join(cards) or '<p>无接缝关系，不计为通过。</p>')
