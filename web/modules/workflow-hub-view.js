import { commandHelp, KIND_LABELS, STATUS_LABELS } from "./workflow-hub-model.js";

export function documentViewerHref(doc) {
  return `./document-viewer.html?doc=${encodeURIComponent(doc)}`;
}

function element(document, tagName, options = {}) {
  const node = document.createElement(tagName);
  if (options.className) node.className = options.className;
  if (options.text !== undefined) node.textContent = options.text;
  for (const [name, value] of Object.entries(options.attributes || {})) {
    node.setAttribute(name, value);
  }
  return node;
}

function badge(document, text, className) {
  return element(document, "span", { className: `badge ${className}`, text });
}

function actionFor(document, entry, announce, copyText) {
  if (entry.kind === "page") {
    return element(document, "a", {
      className: "button primary",
      text: "打开页面",
      attributes: { href: entry.href },
    });
  }
  if (entry.kind === "cli") {
    const button = element(document, "button", {
      className: "button primary",
      text: "复制帮助命令",
      attributes: { type: "button", "aria-label": `复制 ${entry.command} 帮助命令` },
    });
    button.addEventListener("click", async () => {
      const copied = await copyText(commandHelp(entry));
      const message = copied ? `已复制 ${entry.command} 帮助命令` : `无法复制 ${entry.command} 帮助命令`;
      button.textContent = copied ? "已复制" : "复制失败";
      announce(message);
      window.setTimeout(() => { button.textContent = "复制帮助命令"; }, 1800);
    });
    return button;
  }
  return element(document, "span", { className: "badge status-planned", text: "尚无可执行入口" });
}

export function createEntryCard(document, entry, announce, copyText) {
  const article = element(document, "article", {
    className: "entry-card",
    attributes: { "aria-labelledby": `${entry.id}-title` },
  });
  const meta = element(document, "div", { className: "entry-meta" });
  meta.append(
    badge(document, STATUS_LABELS[entry.status], `status-${entry.status}`),
    badge(document, KIND_LABELS[entry.kind], "kind-badge"),
  );
  const title = element(document, "h3", {
    text: entry.title,
    attributes: { id: `${entry.id}-title` },
  });
  const summary = element(document, "p", { className: "entry-summary", text: entry.summary });
  article.append(meta, title, summary);
  if (entry.kind === "cli") {
    article.append(element(document, "pre", { className: "command", text: commandHelp(entry) }));
  }
  const footer = element(document, "div", { className: "entry-footer" });
  footer.append(
    actionFor(document, entry, announce, copyText),
    element(document, "a", {
      className: "button secondary",
      text: "打开文档",
      attributes: {
        href: documentViewerHref(entry.doc),
        "aria-label": `打开 ${entry.title} 的文档`,
      },
    }),
    element(document, "code", { className: "doc-path", text: entry.doc }),
  );
  article.append(footer);
  return article;
}

export function renderGroups(container, groups, announce, copyText) {
  const document = container.ownerDocument;
  const fragment = document.createDocumentFragment();
  if (groups.length === 0) {
    fragment.append(element(document, "p", {
      className: "empty-card",
      text: "没有符合条件的功能。请清除部分筛选条件后重试。",
    }));
  }
  for (const group of groups) {
    const section = element(document, "section", {
      className: "stage-group",
      attributes: { "aria-labelledby": `stage-${group.stage}` },
    });
    const heading = element(document, "div", { className: "stage-heading" });
    heading.append(
      element(document, "span", { className: "stage-token", text: group.stage }),
      element(document, "h2", {
        text: group.label,
        attributes: { id: `stage-${group.stage}` },
      }),
      element(document, "span", { className: "stage-count", text: `${group.entries.length} 项` }),
    );
    const grid = element(document, "div", { className: "entry-grid" });
    for (const entry of group.entries) grid.append(createEntryCard(document, entry, announce, copyText));
    section.append(heading, grid);
    fragment.append(section);
  }
  container.replaceChildren(fragment);
}

export function renderLoadError(container, message) {
  const document = container.ownerDocument;
  container.replaceChildren(element(document, "p", {
    className: "error-card",
    text: `功能目录加载失败：${message}`,
    attributes: { role: "alert" },
  }));
}
