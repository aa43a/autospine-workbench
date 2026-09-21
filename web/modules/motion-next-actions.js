// Operator guidance is not part of the immutable technical review evidence.
const actions={
  '投影':'先比较已有视角。若仍出现骨段塌缩，可在源动作时间轴截取可用片段重新适配；明显侧背身缺少的图像需要补充素材。',
  '几何':'按失败时间检查具体部件。若换视角仍拉伸或翻转，应回到角色绑定修正该部件，再建立新的动作候选。',
  '接触':'查看支撑区间和滑移时间。只有已有源证据支持的区间才会自动修正；未验证区间需要检查脚步与接地表现。',
  '遮挡':'先查看遮挡状态中的模型证据，再比较已有视角。区间不确定不等于画面错误；明确的前后穿插可能需要分区或补充侧面素材。',
  'Runtime':'查看捕获诊断后重试。缺少有效捕获时不能保存接受类阶段结论。',
};

export function appendNextActions(panel,report,compare){
  const pending=report.stages.filter(row=>row.status!=='sampled_pass');
  const section=document.createElement('section');
  const title=document.createElement('h4');title.textContent='下一步';section.append(title);
  if(!pending.length){
    const p=document.createElement('p');p.textContent='打开角色时间轴检查完整动作，再使用本任务的阶段验收入口记录结论。';section.append(p);
  }else{
    const list=document.createElement('ul');
    for(const row of pending){
      const li=document.createElement('li');
      li.textContent=`${row.stage}：${actions[row.stage]||'按该项报告定位异常，修正后重新构建。'}`;
      list.append(li);
    }
    section.append(list);
    if(compare&&pending.some(row=>['投影','几何','遮挡'].includes(row.stage))){
      const button=document.createElement('button');button.textContent='在此比较可用视角';
      button.onclick=compare;section.append(button);
    }
  }
  panel.append(section);
}
