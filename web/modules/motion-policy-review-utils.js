export function downloadJson(filename, value, doc = document) {
  downloadJsonText(filename, jsonText(value), doc);
}

export function jsonText(value) {
  return `${JSON.stringify(value, null, 2)}\n`;
}

export function downloadJsonText(filename, text, doc = document) {
  const url = URL.createObjectURL(new Blob([text], { type: "application/json" }));
  const link = doc.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 0);
}

export function setStatus(element, text, tone) {
  element.textContent = text;
  element.dataset.tone = tone;
}

export function requireFile(input, label) {
  const file = input.files?.[0];
  if (!file) throw new Error(`请选择 ${label} JSON`);
  return file;
}

export function integerOrNull(value) {
  return /^\d+$/.test(value) ? Number(value) : null;
}

export function errorMessage(error) {
  return error instanceof Error ? error.message : String(error);
}
