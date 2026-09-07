"""Offline anchor collection, without assigning review authority or fitting in JS."""

from ..resolved_project import canonical_sha256


def render_anchor_controls(candidate):
    return _CONTROLS.replace("__CANDIDATE_SHA__", canonical_sha256(candidate))


_CONTROLS = '''<section aria-labelledby="anchor-title">
<h2 id="anchor-title">标记相同部位的锚点</h2>
<p>先点击上方原始 PNG，再点击 PSD 合成图中的相同部位。至少 2 对，最多 32 对；
建议分布在角色上下左右，避免所有点集中在一条线上。图片框适配产生的留白不能选点；图像内部的透明区域仍可选点。</p>
<p>坐标以各自原图像素为单位。锚点仅是待复核的观测草稿，不代表素材匹配已确认。</p>
<p id="anchor-status" role="status" aria-live="polite"></p>
<ol id="anchor-list"></ol>
<div class="controls"><button id="anchor-undo" type="button">撤销最后一个点或点对</button>
<button id="anchor-clear" type="button">清空锚点</button>
<button id="anchor-download" type="button" disabled>下载锚点草稿去校准</button></div>
<label>载入锚点草稿<input id="anchor-load" type="file" accept="application/json,.json"></label>
<p>用命令行 mapping-review --anchors 读取草稿，生成误差报告和校准后的叠加复核页。</p>
<span id="anchor-binding" hidden data-candidate-sha="__CANDIDATE_SHA__"></span>
<div id="anchor-markers" aria-hidden="true" style="position:fixed;inset:0;pointer-events:none;overflow:hidden;z-index:3"></div>
</section>'''


ANCHOR_SCRIPT = r'''
(() => {
  const binding = document.getElementById('anchor-binding');
  if (!binding) return;
  const png = document.getElementById('source'), psd = document.getElementById('composite');
  const list = document.getElementById('anchor-list'), message = document.getElementById('anchor-status');
  const save = document.getElementById('anchor-download');
  const undo = document.getElementById('anchor-undo'), clear = document.getElementById('anchor-clear');
  const anchors = []; let pending = null;
  // object-fit: contain, centered, with image borders excluded from the content box.
  function point(image, event) {
    if (!image.complete || !image.naturalWidth || !image.naturalHeight) return null;
    const rect = image.getBoundingClientRect();
    if (!rect.width || !rect.height || !image.offsetWidth || !image.offsetHeight) return null;
    const x = (event.clientX - rect.left) * image.offsetWidth / rect.width - image.clientLeft;
    const y = (event.clientY - rect.top) * image.offsetHeight / rect.height - image.clientTop;
    const scale = Math.min(image.clientWidth / image.naturalWidth, image.clientHeight / image.naturalHeight);
    if (!(scale > 0)) return null;
    const left = (image.clientWidth - image.naturalWidth * scale) / 2;
    const top = (image.clientHeight - image.naturalHeight * scale) / 2;
    const px = (x - left) / scale, py = (y - top) / scale;
    if (![px,py].every(Number.isFinite) || px < 0 || py < 0 || px > image.naturalWidth || py > image.naturalHeight) return null;
    return [px,py];
  }
  function format(value) { return value.map(number => number.toFixed(2)).join(', '); }
  function markers() {
    const layer = document.getElementById('anchor-markers'); if (!layer) return;
    layer.replaceChildren();
    function mark(image, value, label) {
      const rect = image.getBoundingClientRect();
      const scale = Math.min(image.clientWidth / image.naturalWidth,image.clientHeight / image.naturalHeight);
      if (!Number.isFinite(scale) || !(scale > 0) || !image.offsetWidth || !image.offsetHeight) return;
      const left = image.clientLeft + (image.clientWidth - image.naturalWidth * scale) / 2 + value[0] * scale;
      const top = image.clientTop + (image.clientHeight - image.naturalHeight * scale) / 2 + value[1] * scale;
      const dot = document.createElement('span'); dot.textContent = label;
      dot.style.cssText = 'position:absolute;transform:translate(-50%,-50%);background:#172b4d;color:white;border:2px solid #ffcf33;border-radius:50%;min-width:22px;text-align:center;font:bold 13px/22px system-ui;box-shadow:0 0 0 1px #172b4d';
      dot.style.left = `${rect.left + left * rect.width / image.offsetWidth}px`;
      dot.style.top = `${rect.top + top * rect.height / image.offsetHeight}px`;
      layer.appendChild(dot);
    }
    anchors.forEach((anchor,index) => { mark(png,anchor.png,String(index+1)); mark(psd,anchor.psd,String(index+1)); });
    if (pending) mark(png,pending,'待');
  }
  function update(note = '') {
    list.replaceChildren();
    anchors.forEach((anchor, index) => {
      const row = document.createElement('li');
      row.textContent = `${index + 1}. ${anchor.id}: PNG (${format(anchor.png)}) → PSD (${format(anchor.psd)})`;
      list.appendChild(row);
    });
    message.textContent = note || (pending ? `已选 PNG (${format(pending)})，请点击 PSD 相同部位。` :
      `已有 ${anchors.length} 对锚点；请点击原始 PNG。`);
    save.disabled = anchors.length < 2 || !!pending;
    undo.disabled = clear.disabled = !anchors.length && !pending;
    markers();
  }
  function duplicate(side, value) {
    return anchors.some(anchor => anchor[side][0] === value[0] && anchor[side][1] === value[1]);
  }
  png.addEventListener('click', event => {
    if (pending) { update('请先点击 PSD 配对，或撤销待配对的 PNG 点。'); return; }
    if (anchors.length >= 32) { update('最多支持 32 对锚点。'); return; }
    const value = point(png,event);
    if (!value) { update('请点击图像范围内，图片框适配产生的留白不属于图像。'); return; }
    if (duplicate('png',value)) { update('该 PNG 点已使用，请选择另一个部位。'); return; }
    pending = value; update();
  });
  psd.addEventListener('click', event => {
    if (!pending) { update('请先点击原始 PNG，再点击 PSD 配对。'); return; }
    const value = point(psd,event);
    if (!value) { update('请点击图像范围内，图片框适配产生的留白不属于图像。'); return; }
    if (duplicate('psd',value)) { update('该 PSD 点已使用，请选择对应的另一部位。'); return; }
    let number = 1;
    while (anchors.some(anchor => anchor.id === `anchor-${number}`)) number += 1;
    anchors.push({id:`anchor-${number}`,png:pending,psd:value}); pending = null; update();
  });
  undo.addEventListener('click', () => { if (pending) pending = null; else anchors.pop(); update(); });
  clear.addEventListener('click', () => { pending = null; anchors.length = 0; update(); });
  function validDraft(draft) {
    if (!draft || typeof draft !== 'object' || Array.isArray(draft) ||
        Object.keys(draft).sort().join(',') !== 'anchors,authority,candidate_sha256,schema' ||
        draft.schema !== 'autospine.benchmark-mapping-anchors/v1' || draft.authority !== 'none' ||
        draft.candidate_sha256 !== binding.dataset.candidateSha || !Array.isArray(draft.anchors) ||
        draft.anchors.length < 2 || draft.anchors.length > 32) return false;
    const ids = new Set(), points = {png:new Set(),psd:new Set()};
    for (const anchor of draft.anchors) {
      if (!anchor || typeof anchor !== 'object' || Array.isArray(anchor) ||
          Object.keys(anchor).sort().join(',') !== 'id,png,psd' || typeof anchor.id !== 'string' ||
          !/^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,63}$/.test(anchor.id) || ids.has(anchor.id)) return false;
      ids.add(anchor.id);
      for (const [side,image] of [['png',png],['psd',psd]]) {
        const value = anchor[side];
        if (!Array.isArray(value) || value.length !== 2 || !value.every(Number.isFinite) ||
            !image.naturalWidth || !image.naturalHeight || value[0] < 0 || value[1] < 0 ||
            value[0] > image.naturalWidth || value[1] > image.naturalHeight) return false;
        const key = JSON.stringify(value);
        if (points[side].has(key)) return false;
        points[side].add(key);
      }
    }
    return true;
  }
  const load = document.getElementById('anchor-load');
  if (load) load.addEventListener('change', async () => {
    const file = load.files && load.files[0]; if (!file) return;
    try {
      if (file.size > 65536) throw new Error('size');
      const draft = JSON.parse(await file.text());
      if (!validDraft(draft)) throw new Error('draft');
      anchors.splice(0,anchors.length,...draft.anchors);
      pending = null; update('已载入同一候选的锚点草稿，仍需复核。');
    } catch (_) { update('无法载入：候选身份不符、图像未加载或锚点数据无效；已有点已保留。'); }
    load.value = '';
  });
  save.addEventListener('click', () => {
    if (save.disabled || pending || anchors.length < 2 || anchors.length > 32) return;
    const draft = {schema:'autospine.benchmark-mapping-anchors/v1',
      candidate_sha256:binding.dataset.candidateSha,authority:'none',anchors};
    const url = URL.createObjectURL(new Blob([JSON.stringify(draft,null,2)+'\n'],{type:'application/json'}));
    const link = document.createElement('a'); link.href = url; link.download = 'mapping-anchors-draft.json';
    document.body.appendChild(link); link.click(); link.remove(); setTimeout(() => URL.revokeObjectURL(url),1000);
  });
  if (typeof window !== 'undefined') {
    window.addEventListener('resize',markers); window.addEventListener('scroll',markers,{passive:true});
  }
  png.addEventListener('load',markers); psd.addEventListener('load',markers);
  update();
})();
'''
