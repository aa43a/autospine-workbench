const DOCUMENT_PATTERN = /^docs\/[A-Za-z0-9][A-Za-z0-9._/-]*\.md$/;

export function validatedDocumentPath(value) {
  if (typeof value !== "string" || !DOCUMENT_PATTERN.test(value)) return null;
  const parts = value.split("/");
  if (parts.some((part) => !part || part === "." || part === "..")) return null;
  if (value.includes("..")) return null;
  return value;
}

function titleFromPath(path) {
  return path.split("/").at(-1).replace(/\.md$/i, "");
}

async function loadDocument(document, location, fetchDocument) {
  const title = document.querySelector("#documentTitle");
  const pathLabel = document.querySelector("#documentPath");
  const status = document.querySelector("#documentStatus");
  const content = document.querySelector("#documentContent");
  const requested = new URLSearchParams(location.search).get("doc");
  const path = validatedDocumentPath(requested);
  if (!path) {
    title.textContent = "无法打开文档";
    pathLabel.textContent = "只接受仓库 docs/ 下的 Markdown 文件";
    status.textContent = "文档路径无效或缺失。";
    status.classList.add("error");
    content.textContent = "请返回功能入口中心并重新选择文档。";
    return;
  }
  title.textContent = titleFromPath(path);
  pathLabel.textContent = path;
  try {
    const response = await fetchDocument(`../${path}`, { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    content.textContent = await response.text();
    status.textContent = "已加载只读 Markdown 源文件；内容不会作为 HTML 执行。";
  } catch (error) {
    status.textContent = `文档读取失败：${error instanceof Error ? error.message : String(error)}`;
    status.classList.add("error");
    content.textContent = "请确认本地服务仍在运行且文档存在。";
  }
}

if (typeof document !== "undefined" && typeof location !== "undefined") {
  loadDocument(document, location, (...args) => fetch(...args));
}
