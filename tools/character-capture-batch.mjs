// Executed inside the official Runtime page. Every frame still gets its own
// setup pose, animation evaluation, draw and readPixels in captureFrame.
// Only the browser/process round trips are batched; no samples are skipped.
export function captureBatch({animation, start, end, screenshotIndices}) {
  const screenshots = new Set(screenshotIndices), rows = [];
  for (let index = start; index < end; index++) {
    const result = window.captureFrame(animation, index);
    rows.push({result, png: screenshots.has(index) ? window.framePNG() : null});
  }
  return rows;
}

export const CAPTURE_BATCH_SIZE = 8;
