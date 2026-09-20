// Independent JSON offset reconstruction, including Runtime Float32 key times.
globalThis.autospineExpectedDrawOrder = (document, animation, time) => {
  const setup = document.slots.map(slot => slot.name);
  const keys = animation === null ? [] : document.animations[animation].drawOrder || [];
  let selected = null;
  for (const key of keys) {
    if (Math.fround(key.time || 0) > time) break;
    selected = key;
  }
  if (!selected?.offsets?.length) return setup;
  const result = Array(setup.length).fill(null), unchanged = [];
  let current = 0;
  for (const offset of selected.offsets) {
    const index = setup.indexOf(offset.slot);
    if (index < current || !Number.isInteger(offset.offset)) throw Error('draw_order_offsets_invalid');
    while (current < index) unchanged.push(setup[current++]);
    const target = current + offset.offset;
    if (target < 0 || target >= setup.length || result[target] !== null) throw Error('draw_order_target_invalid');
    result[target] = setup[current++];
  }
  while (current < setup.length) unchanged.push(setup[current++]);
  for (let i = result.length - 1; i >= 0; i--) if (result[i] === null) result[i] = unchanged.pop();
  if (unchanged.length || result.some(value => !value)) throw Error('draw_order_inventory_invalid');
  return result;
};
