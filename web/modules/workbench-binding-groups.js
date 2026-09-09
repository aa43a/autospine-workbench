"use strict";

// Review navigation only: these hints do not generate options or grant QA.
export const BINDING_GROUPS = {
  all: "全部图层", rigid: "单骨刚性建议", mesh: "多骨网格建议",
  partition: "分区待复核", secondary: "衣饰与次级运动待复核",
  facial: "眼口细节待复核", unresolved: "缺少明确方案",
};

export function bindingGroup(binding) {
  const name = binding.name || binding.layer_id;
  const tokens = String(name).normalize("NFKC").toLowerCase().split(/[^a-z]+/);
  const has = (...names) => names.some((name) => tokens.includes(name));
  const reasons = binding.reason_codes || [];
  if (reasons.some((reason) => /bilateral|partition|requires_split/.test(reason))) return "partition";
  if (has("hair", "ribbon", "skirt", "sleeve", "bottomwear", "objects", "wing", "wings")) return "secondary";
  if (has("eye", "eyes", "eyebrow", "eyewhite", "eyelash", "irides", "iris", "mouth", "nose", "ears")) return "facial";
  const options = binding.options || [];
  if (options.some((option) => ["mesh_chain", "weighted_mesh"].includes(option.mode))) return "mesh";
  if (!/^layer-\d+$/.test(name) && options.length === 1 && options[0].mode === "rigid" && options[0].bone_ids?.length === 1
    && options[0].id === binding.suggested_option_id
    && !reasons.some((reason) => /unsupported|conflict|unobservable|side.*review|coverage/.test(reason))) return "rigid";
  return "unresolved";
}

export function prefillRigidBindings(bindings, records) {
  const eligible = new Map(bindings.filter((row) => bindingGroup(row) === "rigid")
    .map((row) => [row.layer_id, row.suggested_option_id]));
  return records.map((row) => row.action === "pending" && eligible.has(row.layer_id)
    ? { ...row, action: "bind", option_id: eligible.get(row.layer_id) } : { ...row });
}
