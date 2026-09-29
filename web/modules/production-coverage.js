const states={static_reference:'静态参考，尚未绑定',weighted_candidate:'加权候选',rigid_candidate:'刚性候选',excluded:'已排除',missing:'缺失',partial:'部分覆盖'};
function node(tag,text){const value=document.createElement(tag);value.textContent=text;return value;}
export function createProductionCoverage(api){
  let key=null;
  return async run=>{
    const panel=document.getElementById('coverage');const stage=run.stages.character;
    const next=stage.status==='succeeded'?`${run.run_id}:${stage.artifact_sha256}`:null;
    if(next===key)return;key=next;panel.replaceChildren();panel.hidden=!next;if(!next)return;
    panel.textContent='正在核对整角色覆盖…';
    try{const result=await api(`/api/production/${run.run_id}/coverage`);if(key!==next)return;
      panel.replaceChildren(node('h2',result.unresolved_layer_count?`仍有 ${result.unresolved_layer_count} 层包含未绑定区域`:'已读取整角色覆盖'));
      panel.append(node('p',`共 ${result.layer_count} 层。构建完成不代表每层已绑定；动作、遮挡和阶段验收另行记录。`));
      const details=node('details',''),summary=node('summary','查看逐层处理状态');details.append(summary);
      for(const layer of result.layers){const line=node('p',`${layer.name} · ${states[layer.state]||layer.state}${layer.unresolved?' · 需要处理':''}`);details.append(line);}
      panel.append(details);
      if(result.unresolved_layer_count){const view=node('a','定位未绑定区域');view.href=result.static_regions_url;const edit=node('a','修改归属与绑定');edit.href=result.edit_url;panel.append(view,document.createTextNode('　'),edit,node('p','修改后使用“按当前角色修正重建”，旧候选和异常记录保留。'));}
    }catch(e){if(key===next){panel.textContent=`覆盖检查未完成：${e.message}`;key=null;}}
  };
}
