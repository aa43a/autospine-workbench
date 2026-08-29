export const FOOT_ID_DOMAIN = "autospine-motion-policy-foot-candidate-id/v1";
export const DEPTH_ID_DOMAIN = "autospine-motion-policy-depth-candidate-id/v1";

const encoder = new TextEncoder();

export function canonicalCandidatePayload(value) {
  return canonicalCandidateJson(value);
}

function canonicalCandidateJson(value) {
  if (Array.isArray(value)) return `[${value.map(canonicalCandidateJson).join(",")}]`;
  if (value && typeof value === "object") {
    return `{${Object.keys(value).sort().map((key) => (
      `${JSON.stringify(key)}:${canonicalCandidateJson(value[key])}`
    )).join(",")}}`;
  }
  const encoded = JSON.stringify(value);
  if (encoded === undefined) throw new Error("Canonical JSON 不支持 undefined");
  return encoded;
}

export async function deriveCandidateId(kind, payload, cryptoApi = globalThis.crypto) {
  const domain = kind === "foot_lock" ? FOOT_ID_DOMAIN : DEPTH_ID_DOMAIN;
  const prefix = kind === "foot_lock" ? "foot" : "depth";
  const chunks = [encoder.encode(domain), encoder.encode(canonicalCandidatePayload(payload))];
  const length = chunks.reduce((total, chunk) => total + 8 + chunk.length, 0);
  const framed = new Uint8Array(length);
  let offset = 0;
  for (const chunk of chunks) {
    new DataView(framed.buffer).setBigUint64(offset, BigInt(chunk.length), false);
    offset += 8;
    framed.set(chunk, offset);
    offset += chunk.length;
  }
  return `${prefix}-${await sha256Hex(framed, cryptoApi)}`;
}

export async function deriveCandidateInventorySha(candidateIds, cryptoApi = globalThis.crypto) {
  if (!Array.isArray(candidateIds) || candidateIds.some((value) => typeof value !== "string")) {
    throw new TypeError("Candidate ID inventory 必须是字符串数组");
  }
  const canonical = canonicalCandidatePayload([...candidateIds].sort());
  return sha256Hex(encoder.encode(canonical), cryptoApi);
}

async function sha256Hex(bytes, cryptoApi) {
  if (!cryptoApi?.subtle) throw new Error("当前浏览器不支持 SHA-256 Web Crypto");
  const digest = new Uint8Array(await cryptoApi.subtle.digest("SHA-256", bytes));
  const hex = Array.from(digest, (byte) => byte.toString(16).padStart(2, "0")).join("");
  return hex;
}
