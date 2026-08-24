export const API_BASE = "/api/projects";

export async function apiRequest(url, options = {}) {
  const response = await fetch(url, {
    ...options,
    headers: {
      Accept: "application/json",
      ...(options.body ? { "Content-Type": "application/json" } : {}),
      ...(options.headers || {}),
    },
  });

  const contentType = response.headers.get("content-type") || "";
  let payload = null;
  if (contentType.includes("application/json")) {
    payload = await response.json().catch(() => null);
  } else {
    payload = await response.text().catch(() => "");
  }

  if (!response.ok) {
    const detail = typeof payload === "object" && payload
      ? payload.detail || payload.message || JSON.stringify(payload)
      : payload;
    const error = new Error(detail || `请求失败（HTTP ${response.status}）`);
    error.status = response.status;
    error.payload = payload;
    throw error;
  }
  return payload;
}

export function normalizeProjectSummaries(payload) {
  const list = Array.isArray(payload) ? payload : payload?.projects || payload?.items || [];
  return list.map((item) => {
    if (typeof item === "string") return { id: item, name: item };
    const id = item?.id ?? item?.project_id ?? item?.slug;
    return {
      ...item,
      id: String(id ?? ""),
      name: item?.name || item?.title || String(id ?? "未命名项目"),
    };
  }).filter((item) => item.id);
}
