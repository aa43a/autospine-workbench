import {depthLocation} from './motion-depth-location.js';
const labels={within_frame_mixed:'同帧内部前后冲突',temporal_side_change:'跨帧换侧',uncertain_depth:'深度依据不足',observed_front_only:'仅观察到前侧',observed_back_only:'仅观察到后侧'};
export function appendDepthTriangles(parent,summary,base,inspection){
  const box=document.createElement('details'),title=document.createElement('summary');
  title.textContent='定位到网格区域';box.append(title);parent.append(box);
  if(!summary){box.append(document.createTextNode('此记录没有逐三角形追踪；不能据此判定区域无异常。'));return;}
  const note=document.createElement('p');
  note.textContent='以下为重叠区域的代理深度判断，不是真实衣料归属。跨帧换侧不等于需要细分；定位只切换时间和显示部件，不改变绑定或绘制顺序。';box.append(note);
  for(const pair of summary.pairs){
    const heading=document.createElement('p');heading.textContent=pair.pair.join(' / ')+'：'+Object.entries(pair.counts).map(([k,v])=>`${labels[k]||k} ${v}`).join('；');box.append(heading);
    if(pair.incomplete_samples){const p=document.createElement('p');p.textContent=`另有 ${pair.incomplete_samples} 个未完成采样，未计入区域判断。`;box.append(p);}
    for(const row of pair.locations){
      const p=document.createElement('p'),a=document.createElement('a');
      p.textContent=`三角形 ${row.triangle} · ${labels[row.status]||row.status} · `;
      a.textContent=`定位 ${row.time.toFixed(3)} 秒`;
      depthLocation(a,{time:row.time,pair:pair.pair},base,inspection,p);p.append(a);box.append(p);
    }
    if(pair.locations_truncated)box.append(document.createTextNode('仅显示前 20 个区域，统计包含全部追踪；完整记录保留在补充证据中。'));
  }
}
