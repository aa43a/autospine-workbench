"""Read-only sampled FK geometry timeline, distinct from target runtime evidence."""
from html import escape
import json


REASONS = {
    'ordinary_sleeve_region_unavailable': '此残余区域没有可用网格或归属，仍需复核。',
    'ordinary_sleeve_drape_branch_required': '存在宽袖垂布，应进入服装分支。',
    'ordinary_sleeve_roles_required': '尚缺贴臂袖布和袖口归属。',
    'ownership_review_required': '仍有不确定归属。',
    'setup_reconstruction_failure': '初始姿态重建超出容差。',
    'weight_sum_failure': '顶点权重和未通过检查。',
    'loop_failure': '循环首尾位置不一致。',
    'motion_envelope_geometry_failure': '受限动作中存在几何失败。',
    'runtime_and_alpha_contact_required': '仍需官方 Runtime 与透明接缝验证。',
}


def render(source):
    """Return a self-contained diagnostic HTML; never infer acceptance from geometry."""
    if (source.get('schema') != 'autospine.ordinary-sleeve-motion/v1'
            or source.get('authority') != 'none' or source.get('production_authorized') is not False):
        raise ValueError('ordinary_sleeve_review_source_invalid')
    rows, cards = [], []
    for index, row in enumerate(source['records']):
        tracks = row.get('tracks') or []
        available = bool(tracks) and all(t.get('samples') and t.get('qa') for t in tracks)
        reasons = '；'.join(REASONS.get(code, code) for code in row.get('reason_codes', []))
        label = '已阻塞' if row['status'] == 'blocked' else '候选待复核'
        name = f"{row['layer_id']} / {row['component_id']}"
        cards.append(f'<section class="card" data-row="{index}"><h2>{escape(name)}</h2>'
                     f'<p class="state">{label}</p><p>{escape(reasons or "未提供阻塞原因。")}</p>'
                     + ('<label>测试轨道 <select aria-label="测试轨道"></select></label>'
                        '<p class="qa" role="status"></p><svg role="img" aria-label="普通袖几何诊断"></svg>'
                        if available else '<p class="unavailable">无有效动作轨道；该区域保留在清单中，不计为通过。</p>')
                     + '</section>')
        rows.append({key: row[key] for key in ('setup_vertices', 'triangles', 'tracks', 'setup_error') if key in row}
                    | {'available': available})
    payload = json.dumps(rows, ensure_ascii=False, allow_nan=False, separators=(',', ':')).replace('<', '\\u003c')
    title = escape(str(source['project_id']))
    return (f'<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{title} · 普通袖几何时间轴</title><style>{STYLE}</style>'
            f'<header><h1>{title} · 普通袖几何时间轴</h1>'
            '<p>只读诊断 · 未应用修正 · 不代表正式采用或最终 Runtime 播放结果。</p>'
            '<p>前臂 / 手各 ±30°，同向与反向组合共四轨。每轨检查 129 个 tick；画面每 4 tick 展示一个样本，共 33 帧。'
            '绿色是几何区域，红色是面积异常三角形，蓝色是骨骼。未绘制源纹理，未验证透明接缝。</p>'
            '<div class="controls"><button id="play" type="button">播放</button><button id="setup" type="button">初始姿态</button>'
            '<label>时间轴 <input id="time" type="range" min="0" max="32" step="1" value="0"></label>'
            '<output id="clock" aria-live="off"></output></div></header>'
            f'<main>{"".join(cards) or "<p>没有区域记录。</p>"}</main>'
            f'<script type="application/json" id="data">{payload}</script><script>{SCRIPT}</script></html>')


STYLE = '''
:root{color-scheme:dark;font-family:system-ui,sans-serif;background:#0d1822;color:#e5edf5}
body{margin:0}header{padding:20px;background:#132737;position:sticky;top:0;z-index:1;border-bottom:1px solid #426174}
h1{font-size:22px;margin-top:0}p{line-height:1.5}button,select,input{font:inherit}button,select{padding:8px;background:#203c50;color:#fff;border:1px solid #638399;border-radius:5px}
.controls{display:flex;align-items:center;gap:12px;flex-wrap:wrap}.controls label{display:flex;align-items:center;gap:12px;flex:1;min-width:180px}input{width:100%}
main{display:grid;grid-template-columns:repeat(auto-fit,minmax(330px,1fr));gap:16px;padding:16px}.card{padding:16px;border:1px solid #3c566b;border-radius:8px;min-width:0}
h2{font-size:18px;overflow-wrap:anywhere}.state,.unavailable{color:#ffcc80}svg{width:100%;height:540px;background:#1e303e}.qa{min-height:4em;color:#b9d7ec}
:focus-visible{outline:2px solid #67d8ff;outline-offset:3px}@media(max-width:500px){main{grid-template-columns:1fr}svg{height:380px}header{position:static}}
'''

SCRIPT = r'''
const rows=JSON.parse(document.querySelector('#data').textContent),slider=document.querySelector('#time'),play=document.querySelector('#play');
const names={forearm:'前臂 ±30°',hand:'手 ±30°',combined_same:'前臂与手同向',combined_opposed:'前臂与手反向'};
let running=false,last=0;
const node=(tag,attrs)=>{const n=document.createElementNS('http://www.w3.org/2000/svg',tag);for(const[k,v]of Object.entries(attrs))n.setAttribute(k,v);return n;};
const views=rows.map((row,index)=>{
  if(!row.available)return null;
  const card=document.querySelector(`[data-row="${index}"]`),select=card.querySelector('select');
  row.tracks.forEach((track,i)=>select.add(new Option(`${names[track.bone_id]||track.bone_id} · ${track.failed_ticks}/${track.qa.length} 失败`,i)));
  select.addEventListener('change',draw);
  return {row,select,svg:card.querySelector('svg'),qa:card.querySelector('.qa')};
}).filter(Boolean);
function bounds(track){
  let left=Infinity,top=Infinity,right=-Infinity,bottom=-Infinity;
  for(const frame of track.samples)for(const p of frame.points){left=Math.min(left,p[0]);top=Math.min(top,p[1]);right=Math.max(right,p[0]);bottom=Math.max(bottom,p[1]);}
  return `${left-12} ${top-12} ${Math.max(1,right-left)+24} ${Math.max(1,bottom-top)+24}`;
}
for(const view of views)view.boxes=view.row.tracks.map(bounds);
function draw(){
  const index=Number(slider.value);document.querySelector('#clock').textContent=`${(index/16).toFixed(3)} 秒 · tick ${index*4}/128 · 样本 ${index+1}/33`;
  for(const {row,select,svg,qa,boxes} of views){
    const track=row.tracks[Number(select.value)],frame=track.samples[index];svg.replaceChildren();
    if(!frame){qa.textContent='该轨缺少当前样本，不能判断通过。';continue;}
    const report=track.qa[frame.tick];if(!report){qa.textContent='该帧缺少 QA，不能判断通过。';continue;}
    svg.setAttribute('viewBox',boxes[Number(select.value)]);
    const bad=new Set(report.bad_triangles||[]);
    row.triangles.forEach((triangle,i)=>svg.append(node('polygon',{points:triangle.map(v=>frame.points[v].join(',')).join(' '),fill:bad.has(i)?'#ff586b77':'#55cca833',stroke:'#b5c8d5','stroke-width':'.6'})));
    for(const bone of frame.bones||[]){
      svg.append(node('line',{x1:bone.head_xy[0],y1:bone.head_xy[1],x2:bone.tail_xy[0],y2:bone.tail_xy[1],stroke:'#62cdff','stroke-width':2}));
      const title=node('text',{x:bone.head_xy[0],y:bone.head_xy[1],fill:'#b5e9ff','font-size':9});title.textContent=bone.id;svg.append(title);
    }
    qa.textContent=`本轨失败 ${track.failed_ticks}/${track.qa.length} tick · 当前翻转 ${report.inversions} · 面积比 ${report.min_area_ratio.toFixed(3)}–${report.max_area_ratio.toFixed(3)} · 边长拉伸 ${report.max_edge_stretch.toFixed(3)} · 角度 ${(frame.angles||[]).map(a=>a.toFixed(1)).join(' / ')}°`;
  }
}
const stop=()=>{running=false;play.textContent='播放';};
slider.addEventListener('input',()=>{stop();draw();});
document.querySelector('#setup').addEventListener('click',()=>{stop();slider.value='0';draw();});
play.addEventListener('click',()=>{running=!running;play.textContent=running?'暂停':'播放';last=performance.now();});
document.addEventListener('visibilitychange',()=>{if(document.hidden)stop();});
function step(now){if(running&&now-last>=62.5){slider.value=String((Number(slider.value)+1)%33);last=now;draw();}requestAnimationFrame(step);}
if(!views.length){play.disabled=true;slider.disabled=true;}draw();requestAnimationFrame(step);
'''
