export function createSourcePlayer(canvas, slider, button, label) {
  const ctx = canvas.getContext('2d');
  let data = null, playing = false, previous = 0, elapsed = 0, handle = null;
  let bounds = [0, 0, 1, 1];
  const xy = point => data.view === 'side' ? [-point[2], -point[1]] : [point[0], -point[1]];

  function draw() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    if (!data) return;
    const time = Number(slider.value);
    const frame = data.frames.reduce((a, b) => Math.abs(a.time - time) < Math.abs(b.time - time) ? a : b);
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
    label.textContent = `${frame.time.toFixed(2)} 秒 · 帧 ${frame.frame + 1}`;
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
    if (elapsed >= Number(slider.max)) elapsed = 0;
    previous = performance.now();
    playing = true;
    button.textContent = '暂停';
    handle = requestAnimationFrame(tick);
  };
  slider.oninput = () => { stop(); draw(); };
  return {
    clear() {
      stop(); data = null;
      button.disabled = slider.disabled = true;
      slider.value = 0;
      label.textContent = '0.00 秒';
      draw();
    },
    load(value) {
      stop(); data = value;
      let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
      for (const frame of data.frames) for (const point of frame.joints) {
        const [x, y] = xy(point);
        minX = Math.min(minX, x); maxX = Math.max(maxX, x);
        minY = Math.min(minY, y); maxY = Math.max(maxY, y);
      }
      // One envelope for the entire clip; playback must not introduce camera jitter.
      bounds = [minX, minY, Math.max(1e-6, maxX - minX), Math.max(1e-6, maxY - minY)];
      slider.max = data.frames.at(-1).time;
      slider.value = 0;
      button.disabled = slider.disabled = false;
      draw();
    },
  };
}
