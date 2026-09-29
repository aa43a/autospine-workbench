/* Count actual RGBA pixels; visit the perimeter once, including 1px dimensions. */
globalThis.autospineFramebufferStats = (pixels, width, height) => {
  if (!Number.isInteger(width) || !Number.isInteger(height) || width < 1 || height < 1 ||
      pixels.length !== width * height * 4) throw Error('framebuffer_stats_dimensions');
  let visible = 0, border = 0;
  // No canvas/DOM property reads in this hot loop, and no per-pixel edge branch.
  for (let alpha = 3; alpha < pixels.length; alpha += 4) visible += pixels[alpha] >= 8;
  for (let x = 0; x < width; x++) {
    border += pixels[x * 4 + 3] >= 8;
    if (height > 1) border += pixels[((height - 1) * width + x) * 4 + 3] >= 8;
  }
  // Top/bottom corners were already counted above.
  for (let y = 1; y < height - 1; y++) {
    border += pixels[y * width * 4 + 3] >= 8;
    if (width > 1) border += pixels[(y * width + width - 1) * 4 + 3] >= 8;
  }
  return {visible, border};
};
