"""Source-image strategy cards; no authority-changing controls."""
from html import escape
from .semantic_view import _image_url

LABELS = {'rigid': '刚性绑定候选', 'weighted_mesh': '加权 Mesh 候选',
          'partition_mesh': '分区后 Mesh 候选', 'secondary_motion': '次级运动需求',
          'facial': '眼口／面部动画需求', 'semantic_review': '语义／拆层复核'}


TEXT = {
 'candidate_path_only': '已有候选生成路线，仍需绑定和几何验证',
 'not_implemented_by_planner': '规划需求，尚未生成对应动画',
 'pending': '待处理', 'bind': '已有绑定选择', 'exclude': '已标记排除',
 'requires_split': '需拆层', 'semantic_review': '需语义复核',
 'semantic_and_options_are_candidates': '语义与绑定选项均为候选',
 'no_opaque_alpha_support': '没有达到阈值的不透明区域',
 'conflicting_name_or_semantic_cues': '名称与语义存在冲突',
 'facial_name_or_semantic_cue': '名称或语义提示面部部件',
 'secondary_name_or_semantic_cue': '名称或语义提示次级运动',
 'ambiguous_object_or_garment': '物件或服装类别尚不明确',
 'insufficient_multi_bone_alpha_support': '缺少跨骨段的 alpha 支持',
 'existing_mesh_chain_options_require_coverage_review': '已有骨链选项，需核对覆盖范围',
 'existing_rigid_option_requires_visual_review': '已有单骨候选，需看图确认跟随关系',
 'no_supported_binding_option': '当前没有可用绑定选项',
 'disconnected_alpha_does_not_authorize_split': '区域不连通，但不能据此决定拆层',
 'review_facial_anchors_and_attachment_assets': '核对面部锚点和表情附件需求',
 'review_roots_and_future_chain_requirements': '核对固定根部和辅助骨链需求',
 'review_semantics_and_split_need': '核对部件语义及是否确实需要拆层',
 'review_binding_and_geometry': '核对绑定，随后生成并验证几何',
}


def render(plan, candidate, composite, images):
    layers = {r['layer_id']: r for r in candidate['layers']}
    w, h = candidate['canvas']; source = _image_url(composite, candidate['composite_sha256'])
    cards = []
    for row in plan['layers']:
        layer = layers[row['layer_id']]; x, y, r, b = layer['bbox']
        url = _image_url(images[row['layer_id']], row['image_sha256'])
        options = '、'.join(row['preview']['rigid_option_ids']) or '暂无可用刚性候选'
        hits = '、'.join(v['bone_id']+':'+str(v['opaque_samples'])+'/21'
                         for v in row['evidence']['bone_alpha_samples']) or '无骨段采样命中'
        reasons = '；'.join(TEXT.get(code, code) for code in row['reason_codes'])
        cards.append(f'''<article><h2>{escape(row['name'])} · {escape(row['layer_id'])}</h2>
<svg viewBox="0 0 {w} {h}" role="img" aria-label="源图层位置"><image href="{source}" width="{w}" height="{h}" opacity=".15"/>
<image href="{url}" x="{x}" y="{y}" width="{r-x}" height="{b-y}"/></svg>
<h3>{LABELS[row['strategy']]}</h3><p>静态预览可选：{escape(options)}（仍需复核）</p>
<p>动画能力：{escape(TEXT[row['capability']])}；原决定：{escape(TEXT[row['existing_action']])}</p>
<p>Alpha 连通域：{row['evidence']['component_count']}；骨段采样：{escape(hits)}</p>
<p>依据：{escape(reasons)}</p><p>下一步：{escape(TEXT[row['next_action']])}</p></article>''')
    return f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data:; style-src 'unsafe-inline'; base-uri 'none'">
<title>Rig Planner 策略候选</title><style>body{{font:16px/1.6 system-ui;margin:24px;background:#f4f6f8;color:#233548}}
main{{display:grid;grid-template-columns:repeat(auto-fit,minmax(330px,1fr));gap:20px}}article{{background:white;padding:18px;border-radius:8px;overflow-wrap:anywhere}}
svg{{width:100%;background:#eee}}h2{{font-size:20px}}</style><h1>Rig Planner · {escape(plan['character_id'])}</h1>
<p>共 {len(plan['layers'])} 层。名称和骨段采样仅提供建议，不是置信概率。Alpha 不连通不自动要求拆分。
面部／次级运动尚未由本规划器实现；静态预览绑定不能代替最终动画能力。现有决定未修改，未授予生产权。</p>
<main>{''.join(cards)}</main></html>'''
