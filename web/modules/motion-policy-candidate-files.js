import {
  MAX_CANDIDATE_BYTES, parseJsonFile, unwrapCandidate,
} from "./motion-policy-contracts.js";
import {
  errorMessage, requireFile, setStatus,
} from "./motion-policy-review-utils.js";

export async function readCandidateFile({ kind, fileInput, shaInput, guard, statusElement }) {
  const token = guard.begin();
  shaInput.value = "";
  const shaAtStart = shaInput.value;
  try {
    const file = requireFile(fileInput, `${kind} candidates`);
    if (file.size > MAX_CANDIDATE_BYTES) {
      throw new Error(`${kind} candidates 超过 16 MiB 上限`);
    }
    setStatus(statusElement, `正在读取 ${kind} candidates…`, "warning");
    const text = await file.text();
    if (!current(guard, token, fileInput, file, shaInput, shaAtStart)) return null;
    const unwrapped = parseCandidateText(kind, text);
    if (!current(guard, token, fileInput, file, shaInput, shaAtStart)) return null;
    if (unwrapped.reportSha256) shaInput.value = unwrapped.reportSha256;
    setStatus(statusElement, `${kind} 文件已读取；${unwrapped.reportSha256 ?
      "已从 CLI envelope 暂填报告 SHA，仍需 Python 重算。" :
      "请填写 CLI 报告 SHA。"}`, "warning");
    return { ...unwrapped, rawText: text };
  } catch (error) {
    if (guard.isCurrent(token)) setStatus(statusElement, errorMessage(error), "error");
    return null;
  }
}

export function parseCandidateText(kind, text, declaredSha = null) {
  if (!["foot", "depth"].includes(kind) || typeof text !== "string" ||
      new TextEncoder().encode(text).length > MAX_CANDIDATE_BYTES) {
    throw new Error("自动候选输入无效或超过 16 MiB 上限");
  }
  const unwrapped = unwrapCandidate(
    parseJsonFile(text, `${kind} candidates`, MAX_CANDIDATE_BYTES), kind,
  );
  if (declaredSha && unwrapped.reportSha256 && unwrapped.reportSha256 !== declaredSha) {
    throw new Error(`${kind} CLI envelope SHA 与自动包身份不一致`);
  }
  return { ...unwrapped, rawText: text };
}

function current(guard, token, fileInput, file, shaInput, shaAtStart) {
  return guard.isCurrent(token) && fileInput.files?.[0] === file && shaInput.value === shaAtStart;
}
