import {createSourcePlayer} from './motion-source-player.js';

export async function loadSourceReference(config) {
  const url = new URL(config.source_comparison_url, location.href);
  if (url.origin !== location.origin) throw Error('源动作地址必须同源');
  const response = await fetch(url);
  if (!response.ok) throw Error('读取源动作失败');
  const source = await response.json();
  if (source.artifact_sha256 !== config.artifact) throw Error('源动作对应的候选版本不匹配');
  const [start, end] = config.request.interval;
  if (!Number.isFinite(source.source_start) || !Number.isFinite(source.duration)
      || source.source_start < 0 || start < 0 || end > source.duration + 1e-5)
    throw Error('源动作与修形时间范围不匹配');
  const slider = document.createElement('input');
  slider.type = 'range'; slider.step = 'any';
  const button = document.createElement('button');
  const el = id => document.getElementById(id);
  const player = createSourcePlayer(el('source-canvas'), slider, button, el('source-position'));
  player.load(source.preview, {start: source.source_start, end: source.source_start + source.duration});
  player.setView('front');
  el('source-view').onchange = () => player.setView(el('source-view').value);
  el('source-reference').hidden = false;
  return {seek(time) {
    player.seek(source.source_start + time);
    el('source-position').dataset.requestedTime = String(source.source_start + time);
  }};
}
