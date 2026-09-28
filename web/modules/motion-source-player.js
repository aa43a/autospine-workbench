import {sampleSourceFrame} from './motion-source-sample.js';
export function createSourcePlayer(canvas, slider, button, label, onTime = () => {}, {maxYaw=90,interpolateFrames=false}={}) {
  if(![90,3600].includes(maxYaw))throw Error('source_yaw_limit_invalid');
  const ctx = canvas.getContext('2d');
  let data = null, playing = false, previous = 0, elapsed = 0, handle = null;
  let bounds = [0, 0, 1, 1];
  let view = null;
  const xy = point => {
    const selected = view ?? data.view;
    const yaw = typeof selected === 'number' ? selected : selected === 'side' ? 90 : 0;
    const angle = yaw * Math.PI / 180;
    return [Math.cos(angle) * point[0] - Math.sin(angle) * point[2], -point[1]];
  };
  function fitBounds() {
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    for (const frame of data.frames) for (const point of frame.joints) {
      const [x, y] = xy(point);
      minX = Math.min(minX, x); maxX = Math.max(maxX, x);
      minY = Math.min(minY, y); maxY = Math.max(maxY, y);
    }
    // Fixed envelope across the clip, never follow individual frames.
    bounds = [minX, minY, Math.max(1e-6, maxX - minX), Math.max(1e-6, maxY - minY)];
  }

  function draw() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    if (!data) return;
    const time = Number(slider.value);
    const frame = interpolateFrames?sampleSourceFrame(data.frames,time):data.frames.reduce((a, b) => Math.abs(a.time - time) < Math.abs(b.time - time) ? a : b);
    const [x, y, w, h] = bounds;
    const scale = Math.min((canvas.width - 80) / w, (canvas.height - 80) / h);
    const map = point => {
      const value = xy(point);
      return [(value[0] - x - w / 2) * scale + canvas.width / 2,
        (value[1] - y - h / 2) * scale + canvas.height / 2];
    };
    ctx.lineWidth = 3;
    ctx.strokeStyle = '#5cc9ed';
    ctx.fillStyle = '#d7f3ff';
    frame.joints.forEach((point, index) => {
      const value = map(point), parent = data.parents[index];
      if (parent !== null) {
        const start = map(frame.joints[parent]);
        ctx.beginPath(); ctx.moveTo(...start); ctx.lineTo(...value); ctx.stroke();
      }
      ctx.beginPath(); ctx.arc(...value, 2.5, 0, Math.PI * 2); ctx.fill();
    });
    label.textContent = `${frame.time.toFixed(3)} 秒 · 帧 ${frame.frame + 1}${frame.interpolated?'＋补间':''}`;
    onTime(time, Number(slider.max));
  }

  function stop() {
    playing = false;
    button.textContent = '播放';
    if (handle !== null) cancelAnimationFrame(handle);
    handle = null;
  }

  function tick(now) {
    if (!playing) return;
    elapsed += (now - previous) / 1000;
    previous = now;
    if (elapsed >= Number(slider.max)) { elapsed = Number(slider.max); stop(); }
    slider.value = elapsed;
    draw();
    if (playing) handle = requestAnimationFrame(tick);
  }

  button.onclick = () => {
    if (playing) { stop(); return; }
    if (!data) return;
    elapsed = Number(slider.value);
    if (elapsed >= Number(slider.max)) elapsed = Number(slider.min);
    previous = performance.now();
    playing = true;
    button.textContent = '暂停';
    handle = requestAnimationFrame(tick);
  };
  slider.oninput = () => { stop(); draw(); };
  return {
    setView(value) {
      if (![null, 'front', 'side'].includes(value)
          && !(typeof value === 'number' && Number.isFinite(value) && Math.abs(value) <= maxYaw))
        throw Error('source_view_invalid');
      view = value;
      if (data) { fitBounds(); draw(); }
    },
    seek(time) {
      if (!data || !Number.isFinite(time)) return;
      stop(); slider.value = Math.max(Number(slider.min), Math.min(Number(slider.max), time)); draw();
    },
    clear() {
      stop(); data = null;
      button.disabled = slider.disabled = true;
      slider.value = 0;
      label.textContent = '0.00 秒';
      draw();
    },
    load(value, {start=0, end=value.frames.at(-1).time} = {}) {
      if (!Number.isFinite(start) || !Number.isFinite(end) || start < 0 || end < start)
        throw Error('source_time_range_invalid');
      stop(); data = value;
      fitBounds();
      slider.min = start; slider.max = end;
      slider.value = start;
      button.disabled = slider.disabled = false;
      draw();
    },
  };
}
