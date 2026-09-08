"""Reuse ROI rendering while labelling constrained search hypotheses."""
from html import escape
from .mount_contact_view import render as render_local
POLICIES={'source_upper_quarter':'服装上部25%边界', 'hand_reference_window':'手腕参考点附近',
          'torso_root_window':'躯干参考点附近', 'unsupported_relation':'暂不支持此关系'}
REASONS={'no_boundary_in_search_window':'范围内没有双方边界',
         'requires_other_attachment_evidence':'需要其他挂接证据',
         'pair_evaluation_limit':'达到计算资源限制'}


def render(doc,candidate,images):
    rows=[];missing=[]
    for row in doc['rows']:
        if not row['candidates']:
            missing.append(escape(row['name']+' / '+row['bone_id']+' / '+row['target_layer_id'])+'：'+
                           REASONS.get(row['reason_code'],escape(row['reason_code'])))
        for index,option in enumerate(row['candidates']):
            rows.append({'layer_id':row['layer_id'],
                         'name':row['name']+' · '+POLICIES[row['policy']]+f' · 候选{index+1} / 距离{option["distance_px"]:.2f}px',
                         'bone_id':row['bone_id'],'relations':[{'target_layer_id':row['target_layer_id'],**option['local_evidence']}]})
    # Radius is already encoded in each candidate ROI; the legacy renderer uses this only as caption.
    radii=[int((o['local_evidence']['roi'][2]-o['local_evidence']['roi'][0]-1)/2)
           for row in doc['rows'] for o in row['candidates']]
    html=render_local({'rows':rows,'parameters':{'roi_radius_px':radii[0] if radii else 0}},candidate,images)
    html=html.replace('局部边界接触诊断','语义约束边界搜索')
    html=html.replace('距骨骼参考点最近的源alpha边界像素','受约束范围内的源边界候选像素')
    notice='<p>保留最多3个空间分离的候选，没有自动选中。上缘不等于腰口；手腕附近不等于抓握；躯干近邻不能还原被遮挡的根部。</p>'
    return html.replace('<main>',notice+'<ul>'+''.join('<li>'+v+'</li>' for v in missing)+'</ul><main>')
