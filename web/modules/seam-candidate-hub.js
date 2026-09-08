const names = {alice: 'Alice', crino: '琪露诺', lingxian: '铃仙'};
const labels = {sampled_no_new_regression: '仅当前采样未发现新增退化', not_evaluated: '未评估：缺少目标样本',
  review_runtime_alpha_loss: '待复核：合成透明度下降', review_pair_alpha_loss: '待复核：双附件透明度下降',
  blocked_geometry: '阻塞：几何失败', blocked_boundary_distance: '阻塞：边界超限'};
const select = document.querySelector('#character');
try {
  const response = await fetch('/collection.json');
  if (!response.ok) throw Error('collection_unavailable');
  const index = await response.json();
  document.querySelector('#version').textContent = `Spine 导出目标 ${index.export_target} · 官方 Runtime ${index.runtime_version}`;
  for (const item of index.characters) select.add(new Option(names[item.character], item.character));
  function show() {
    const item = index.characters.find(c => c.character === select.value);
    const rows = document.querySelector('#rows'); rows.replaceChildren();
    for (const relation of item.relations) {
      const row = document.createElement('tr');
      for (const value of [relation.driver + ' → ' + relation.follower,
        relation.track === 'reference' ? '原轨道整段回退' : '保留有界增量',
        relation.max_distance_growth_px.toFixed(3) + ' px', relation.sample_count, labels[relation.status] || '待复核']) {
        const cell = document.createElement('td'); cell.textContent = value; row.append(cell);
      }
      rows.append(row);
    }
    document.querySelector('#download').href = `/${item.character}/preview.zip`;
    document.querySelector('#download').download = `${item.character}-candidate.zip`;
    document.querySelector('#report').href = `/${item.character}/admission.json`;
    document.querySelector('#identity').textContent = JSON.stringify(item, null, 2);
    document.querySelector('#player').src = `/player.html?character=${item.character}`;
  }
  select.addEventListener('change', show); show();
} catch {
  document.querySelector('#error').textContent = '候选集合加载失败，请重新校验并启动预览服务。';
}
