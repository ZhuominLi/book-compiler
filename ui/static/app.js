/** Minimal Markdown → HTML (no CDN). */

function escPre(s) {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;");
}

let mermaidReady = false;

function initMermaid() {
  if (mermaidReady || typeof mermaid === "undefined") return;
  const theme = document.documentElement.dataset.readerTheme === "night" ? "dark" : "default";
  mermaid.initialize({
    startOnLoad: false,
    securityLevel: "loose",
    theme,
    htmlLabels: true,
  });
  mermaidReady = true;
}

function normalizeMermaidText(src) {
  return src
    .replace(/[\u201C\u201D\u201E\u201F\u2033\u2036]/g, '"')
    .replace(/[\u2018\u2019\u2032]/g, "'")
    .replace(/\uFF1E/g, ">")
    .replace(/\uFF1C/g, "<")
    .replace(/\uFF1A/g, ":")
    .replace(/\uFF08/g, "(")
    .replace(/\uFF09/g, ")");
}

function mermaidLabelNeedsQuotes(text, aggressive = false) {
  const t = text.trim();
  if (!t || (t.startsWith('"') && t.endsWith('"'))) return false;
  if (aggressive) return true;
  return !/^[\u4e00-\u9fffA-Za-z0-9_\s]+$/.test(t);
}

function quoteMermaidLabel(text) {
  return `"${text.trim().replace(/"/g, "#quot;")}"`;
}

/** LLM 常写出 B( (说明) )，修正为 B((说明)) */
function fixFlowchartDoubleParens(line) {
  return line.replace(/(\b[A-Za-z][\w]*)\(\s*\(\s*([^)]*?)\s*\)\s*\)/g, "$1(($2))");
}

function fixMindmapIconLine(content) {
  const m = content.match(/^[：:\s]*:?[：:]\s*icon\s*\(([^)]*)\)\s*$/i);
  if (m) return `::icon(${m[1].trim()})`;
  if (/^::icon\s*\(/i.test(content)) return content;
  return null;
}

/** mindmap 靠缩进表达层级，给节点加引号会破坏嵌套解析；做字符规范化、icon 行修正与常见 LLM 语法纠错 */
function sanitizeMindmap(src) {
  return src
    .split("\n")
    .map((line) => {
      const m = line.match(/^(\s*)(.+)$/);
      if (!m) return line;
      let indent = m[1];
      let content = m[2].trim();
      if (!content || /^mindmap$/i.test(content)) return indent + content;

      if (indent.length % 2 === 1) indent += " ";

      const iconLine = fixMindmapIconLine(content);
      if (iconLine) return `${indent}${iconLine}`;

      // LLM 常写 `[标签] 说明文字`，mindmap 要求整行是一个节点：`[标签 说明文字]`
      const bracketTail = content.match(/^\[([^\]]+)\]\s+(.+)$/);
      if (bracketTail) content = `[${bracketTail[1]} ${bracketTail[2]}]`;

      return `${indent}${content}`;
    })
    .join("\n");
}

function sanitizeFlowchartNodeLabels(line, aggressive) {
  const quoteIf = (label) =>
    mermaidLabelNeedsQuotes(label, aggressive) ? quoteMermaidLabel(label) : label.trim();

  return line
    .replace(/\[([^\]]+)\]/g, (full, label) => `[${quoteIf(label)}]`)
    .replace(/\(\(([^)]+)\)\)/g, (full, label) => `((${quoteIf(label)}))`)
    .replace(/\{([^}]+)\}/g, (full, label) => `{${quoteIf(label)}}`)
    .replace(/(\b[A-Za-z][\w]*)\(([^()]+)\)/g, (full, id, label) => {
      if (/-->|---|\|/.test(label)) return full;
      return `${id}(${quoteIf(label)})`;
    });
}

function sanitizeFlowchart(src, { aggressive = false } = {}) {
  const q = quoteMermaidLabel;

  return normalizeMermaidText(src)
    .split("\n")
    .map((line) => {
      let L = fixFlowchartDoubleParens(line);
      if (/^style\s/i.test(L.trim())) return L;

      const subgraph = L.match(/^(\s*subgraph\s+)(.+)$/i);
      if (subgraph) {
        const title = subgraph[2].trim().replace(/^["']|["']$/g, "");
        if (title && !/^\w+$/.test(title)) return `${subgraph[1]}${q(title)}`;
        return L;
      }

      if (/^end\s*$/i.test(L.trim())) return L;

      return sanitizeFlowchartNodeLabels(L, aggressive);
    })
    .join("\n");
}

function prepareMermaidSource(raw, { aggressive = false } = {}) {
  const trimmed = raw.trim();
  const normalized = normalizeMermaidText(trimmed);
  if (/^mindmap\b/i.test(trimmed)) {
    return patchMermaidStyles(sanitizeMindmap(normalized));
  }
  const base = normalized.split("\n").map(fixFlowchartDoubleParens).join("\n");
  if (!aggressive) return patchMermaidStyles(base);
  return patchMermaidStyles(sanitizeFlowchart(base, { aggressive: true }));
}

async function renderMermaidIn(root) {
  if (!root || typeof mermaid === "undefined") return;
  const pending = [...root.querySelectorAll("pre.mermaid:not([data-rendered])")];
  if (!pending.length) {
    fixMermaidContrast(root);
    return;
  }
  initMermaid();
  for (const el of pending) {
    const raw = el.textContent.trim();
    const attempts = [
      () => prepareMermaidSource(raw),
      () => prepareMermaidSource(raw, { aggressive: true }),
    ];
    let rendered = false;
    for (const build of attempts) {
      el.textContent = build();
      el.classList.remove("mermaid-failed");
      try {
        await mermaid.run({ nodes: [el] });
        el.dataset.rendered = "1";
        rendered = true;
        break;
      } catch (err) {
        console.warn("mermaid render failed", err);
      }
    }
    if (!rendered) {
      el.dataset.rendered = "1";
      el.classList.add("mermaid-failed");
      el.innerHTML =
        `<div class="mermaid-fallback">` +
        `<p class="mermaid-fallback-title">图表语法有误，无法渲染</p>` +
        `<pre class="mermaid-fallback-src">${escPre(raw)}</pre></div>`;
    }
  }
  fixMermaidContrast(root);
}

function parseCssColor(c) {
  const s = (c || "").trim().replace(/\s*!important\s*$/i, "");
  if (!s || s === "none" || s.startsWith("url(")) return null;
  let m = s.match(/^#([0-9a-f]{3,8})$/i);
  if (m) {
    let h = m[1];
    if (h.length === 3) h = h.split("").map((x) => x + x).join("");
    const n = parseInt(h.slice(0, 6), 16);
    return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
  }
  m = s.match(/^rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)/);
  if (m) return [+m[1], +m[2], +m[3]];
  return null;
}

function colorLuminance(rgb) {
  const [r, g, b] = rgb.map((v) => {
    const x = v / 255;
    return x <= 0.03928 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function isLightFill(fill) {
  const rgb = parseCssColor(fill);
  return rgb ? colorLuminance(rgb) > 0.55 : false;
}

function setMermaidLabelDark(node) {
  node.querySelectorAll(".nodeLabel, .nodeLabel *, foreignObject, foreignObject *").forEach((el) => {
    el.style.setProperty("color", "#111", "important");
  });
  node.querySelectorAll("text, tspan").forEach((el) => {
    el.setAttribute("fill", "#111");
    el.style.setProperty("fill", "#111", "important");
  });
}

function patchMermaidStyles(src) {
  return src.replace(/^(\s*style\s+\S+\s+.+)$/gm, (line) => {
    if (!/fill\s*:/i.test(line) || /color\s*:/i.test(line)) return line;
    return `${line.replace(/\s+$/, "")},color:#111`;
  });
}

function shapeFill(shape) {
  const attr = shape.getAttribute("fill");
  if (attr && attr !== "none") return attr;
  const style = shape.getAttribute("style") || "";
  const m = style.match(/fill:\s*([^;]+)/i);
  if (m) return m[1].trim().replace(/\s*!important\s*$/i, "");
  const computed = getComputedStyle(shape).fill;
  return computed && computed !== "none" ? computed : "";
}

function fixMermaidSvgContrast(svg) {
  svg.querySelectorAll("g.node").forEach((node) => {
    const shape = node.querySelector("rect, polygon, path, circle, ellipse");
    if (!shape) return;
    if (isLightFill(shapeFill(shape))) setMermaidLabelDark(node);
  });
}

function fixMermaidContrast(root) {
  root.querySelectorAll(".mermaid svg").forEach(fixMermaidSvgContrast);
}

function listLineDepth(line) {
  const m = line.match(/^(\s*)[-*] (.+)$/);
  if (!m) return null;
  return { depth: m[1].length, text: m[2] };
}

function isListLine(line) {
  return /^(\s*)[-*] .+/.test(line);
}

/** 解析缩进嵌套 `-` 列表为 <ul><li>… */
function renderNestedList(lines, start, inline) {
  if (!isListLine(lines[start])) return { html: "", next: start };

  const roots = [];
  const stack = [{ depth: -1, items: roots }];
  let i = start;

  while (i < lines.length) {
    const parsed = listLineDepth(lines[i]);
    if (!parsed) break;

    while (stack.length > 1 && stack[stack.length - 1].depth >= parsed.depth) {
      stack.pop();
    }

    const node = { text: parsed.text, kids: [] };
    stack[stack.length - 1].items.push(node);

    const next = lines[i + 1];
    const nextParsed = next ? listLineDepth(next) : null;
    if (nextParsed && nextParsed.depth > parsed.depth) {
      stack.push({ depth: parsed.depth, items: node.kids });
    }
    i++;
  }

  function walk(nodes) {
    let html = "<ul>";
    for (const n of nodes) {
      html += `<li>${inline(n.text)}`;
      if (n.kids.length) html += walk(n.kids);
      html += "</li>";
    }
    return html + "</ul>";
  }

  return { html: walk(roots), next: i };
}

function renderMd(src) {
  const lines = src.split("\n");
  const out = [];
  let i = 0;
  let outlineTreeNext = false;
  const esc = (s) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  const inline = (s) =>
    esc(s)
      .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
      .replace(/`([^`]+)`/g, "<code>$1</code>");

  while (i < lines.length) {
    const line = lines[i];
    if (/^```/.test(line.trim())) {
      const lang = line.trim().slice(3).trim().toLowerCase();
      i++;
      const body = [];
      while (i < lines.length && !/^```/.test(lines[i].trim())) {
        body.push(lines[i]);
        i++;
      }
      if (i < lines.length) i++;
      const content = body.join("\n");
      if (lang === "mermaid") {
        out.push(`<pre class="mermaid">${escPre(content)}</pre>`);
      } else {
        const cls = lang ? ` class="language-${esc(lang)}"` : "";
        out.push(`<pre class="md-pre"><code${cls}>${esc(content)}</code></pre>`);
      }
      continue;
    }
    if (/^<!--\s*outline-tree\s*-->/i.test(line.trim())) {
      outlineTreeNext = true;
      i++;
      continue;
    }
    if (/^---+$/.test(line.trim())) { out.push("<hr>"); i++; continue; }
    if (/^### (.+)/.test(line)) {
      const title = line.slice(4);
      out.push(`<h3>${inline(title)}</h3>`);
      if (/思维导图/.test(title)) outlineTreeNext = true;
      i++;
      continue;
    }
    if (/^#### (.+)/.test(line)) { out.push(`<h4>${inline(line.slice(5))}</h4>`); i++; continue; }
    if (/^## (.+)/.test(line)) { out.push(`<h2>${inline(line.slice(3))}</h2>`); i++; continue; }
    if (/^# (.+)/.test(line)) { out.push(`<h1>${inline(line.slice(2))}</h1>`); i++; continue; }
    if (/^> (.+)/.test(line)) {
      const bq = [];
      while (i < lines.length && /^> ?/.test(lines[i])) {
        bq.push(inline(lines[i].replace(/^> ?/, "")));
        i++;
      }
      out.push(`<blockquote>${bq.join("<br>")}</blockquote>`);
      continue;
    }
    if (/^\|.+\|$/.test(line) && i + 1 < lines.length && /^\|[-| :]+\|$/.test(lines[i + 1])) {
      const rows = [line]; i++; rows.push(lines[i]); i++;
      while (i < lines.length && /^\|.+\|$/.test(lines[i])) { rows.push(lines[i]); i++; }
      const parseRow = (r) => r.split("|").slice(1, -1).map((c) => c.trim());
      const header = parseRow(rows[0]);
      const body = rows.slice(2).map(parseRow);
      let t = "<table><thead><tr>" + header.map((h) => `<th>${inline(h)}</th>`).join("") + "</tr></thead><tbody>";
      body.forEach((row) => { t += "<tr>" + row.map((c) => `<td>${inline(c)}</td>`).join("") + "</tr>"; });
      out.push(`<div class="table-wrap">${t}</tbody></table></div>`);
      continue;
    }
    if (isListLine(line)) {
      const { html, next } = renderNestedList(lines, i, inline);
      if (outlineTreeNext) {
        out.push(`<div class="outline-tree">${html}</div>`);
        outlineTreeNext = false;
      } else {
        out.push(html);
      }
      i = next;
      continue;
    }
    if (/^\d+\. (.+)/.test(line)) {
      const items = [];
      while (i < lines.length && /^\d+\. (.+)/.test(lines[i])) {
        items.push(`<li>${inline(lines[i].replace(/^\d+\. /, ""))}</li>`);
        i++;
      }
      out.push("<ol>" + items.join("") + "</ol>");
      continue;
    }
    if (line.trim() === "") { i++; continue; }
    out.push(`<p>${inline(line)}</p>`);
    i++;
  }
  return out.join("\n");
}

const ICONS = {
  plus: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M12 5v14M5 12h14"/></svg>',
  arrowLeft: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M15 18l-6-6 6-6"/></svg>',
  overview: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 6h16M4 12h16M4 18h10"/></svg>',
  sparkles: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3l1.5 4.5L18 9l-4.5 1.5L12 15l-1.5-4.5L6 9l4.5-1.5L12 3z"/><path d="M5 19l1 3 1-3 3-1-3-1-1-3-1 3-3 1 3 1z"/></svg>',
  sidebar: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="16" rx="2"/><path d="M15 4v16"/></svg>',
  toc: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"/></svg>',
  maximize: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M8 3H5a2 2 0 00-2 2v3M21 8V5a2 2 0 00-2-2h-3M16 21h3a2 2 0 002-2v-3M3 16v3a2 2 0 002 2h3"/></svg>',
  minimize: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 14h6v6M20 10h-6V4M14 10l7-7M3 21l7-7"/></svg>',
  fontDec: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M4 7V4h16v3"/><path d="M9 20h6"/><path d="M12 4v16"/></svg>',
  fontInc: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M4 7V4h16v3"/><path d="M9 20h6"/><path d="M12 4v16"/><path d="M17 14v6M14 17h6"/></svg>',
  sun: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>',
  moon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 14.5A8.5 8.5 0 1112.5 6 6.5 6.5 0 0021 14.5z"/></svg>',
  split: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M16 3h5v5M8 21H3v-5M21 3l-7 7M3 21l7-7"/></svg>',
  trash: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6"/><path d="M10 11v6M14 11v6"/></svg>',
  send: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 2L11 13"/><path d="M22 2l-7 20-4-9-9-4 20-7z"/></svg>',
  edit: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 013 3L7 19l-4 1 1-4 12.5-12.5z"/></svg>',
  layers: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5"/><path d="M2 12l10 5 10-5"/></svg>',
  refresh: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a9 9 0 10-2.64 6.36"/><path d="M21 3v6h-6"/></svg>',
  filePdf: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><path d="M14 2v6h6"/><path d="M10 13h4M10 17h4"/></svg>',
  settings: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 15a3 3 0 100-6 3 3 0 000 6z"/><path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-4 0v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83 0 2 2 0 010-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 010-4h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 012.83-2.83l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 014 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 2.83l-.06.06A1.65 1.65 0 0019.4 9a1.65 1.65 0 001.51 1H21a2 2 0 010 4h-.09a1.65 1.65 0 00-1.51 1z"/></svg>',
};

function iconHtml(name) {
  return ICONS[name] || "";
}

function setBtnIcon(btn, name) {
  if (!btn) return;
  btn.innerHTML = iconHtml(name);
}

function inlineIconBtn(id, icon, title) {
  return `<button type="button" class="btn-deep-inline" id="${id}" title="${escapeHtml(title)}" aria-label="${escapeHtml(title)}">${iconHtml(icon)}</button>`;
}

const $ = (s) => document.querySelector(s);
const libraryView = $("#library-view");
const readerView = $("#reader-view");
const shelf = $("#shelf");
const btnImport = $("#btn-import");
const btnSettings = $("#btn-settings");
const llmBanner = $("#llm-banner");
const llmStartupDialog = $("#llm-startup-dialog");
const llmStartupLater = $("#llm-startup-later");
const llmStartupSetup = $("#llm-startup-setup");
const llmSettingsDialog = $("#llm-settings-dialog");
const llmSettingsForm = $("#llm-settings-form");
const llmSettingsKey = $("#llm-settings-key");
const llmSettingsBase = $("#llm-settings-base");
const llmSettingsModel = $("#llm-settings-model");
const llmSettingsStatus = $("#llm-settings-status");
const llmSettingsError = $("#llm-settings-error");
const llmSettingsCancel = $("#llm-settings-cancel");
const llmSettingsClearKey = $("#llm-settings-clear-key");
const updateVersionLine = $("#update-version-line");
const updateNotes = $("#update-notes");
const updateError = $("#update-error");
const btnCheckUpdate = $("#btn-check-update");
const btnApplyUpdate = $("#btn-apply-update");
let llmStatus = { configured: false, needs_setup: true };
let pendingUpdate = null;

function llmNeedsSetup() {
  if (typeof llmStatus.needs_setup === "boolean") return llmStatus.needs_setup;
  // 兼容旧版 API：用户已在设置里保存过 Key 则不再提醒
  return llmStatus.source !== "user";
}

function updateLlmStatusUI() {
  const setup = llmNeedsSetup();
  btnSettings?.classList.toggle("needs-attention", setup);
  llmBanner?.classList.toggle("hidden", !setup);
}

async function refreshLlmStatus(options = {}) {
  try {
    llmStatus = await api("/api/settings/llm");
    updateLlmStatusUI();
    if (options.remind && llmNeedsSetup()) {
      llmStartupDialog?.showModal();
    }
  } catch {
    /* ignore */
  }
}

function openLlmSettingsFromStartup() {
  llmStartupDialog?.close();
  openLlmSettingsDialog();
}

function renderLlmSettingsStatus() {
  if (!llmSettingsStatus) return;
  llmSettingsStatus.classList.remove("ok");
  if (llmNeedsSetup()) {
    if (llmStatus.configured && llmStatus.source === "env") {
      llmSettingsStatus.textContent = "当前使用环境变量中的 Key，请保存您自己的 API Key";
    } else {
      llmSettingsStatus.textContent = "当前未配置 API Key";
    }
    return;
  }
  llmSettingsStatus.classList.add("ok");
  const hint = llmStatus.key_hint ? `（${llmStatus.key_hint}）` : "";
  const src = llmStatus.source === "user" ? "已保存" : "来自环境变量";
  llmSettingsStatus.textContent = `已配置 ${src}${hint} · ${llmStatus.model}`;
}

async function openLlmSettingsDialog() {
  llmSettingsError?.classList.add("hidden");
  updateError?.classList.add("hidden");
  updateNotes?.classList.add("hidden");
  btnApplyUpdate?.classList.add("hidden");
  pendingUpdate = null;
  if (llmSettingsKey) llmSettingsKey.value = "";
  try {
    llmStatus = await api("/api/settings/llm");
    if (llmSettingsBase) llmSettingsBase.value = llmStatus.base_url || "";
    if (llmSettingsModel) llmSettingsModel.value = llmStatus.model || "";
    renderLlmSettingsStatus();
    await refreshUpdateStatus();
    llmSettingsDialog?.showModal();
  } catch (e) {
    alert(e.message);
  }
}

function renderUpdateStatus(rt) {
  if (!updateVersionLine) return;
  if (!rt?.frozen) {
    updateVersionLine.textContent = "开发模式：直接使用源码，无需 Runtime 热更新";
    btnCheckUpdate?.classList.add("hidden");
    btnApplyUpdate?.classList.add("hidden");
    return;
  }
  btnCheckUpdate?.classList.remove("hidden");
  const src = rt.source === "runtime" ? "热更新" : "内置";
  updateVersionLine.textContent = `当前 ${rt.active_version}（${src}）· Shell ${rt.bundled_version}`;
}

async function refreshUpdateStatus() {
  try {
    const rt = await api("/api/update/status");
    renderUpdateStatus(rt);
  } catch {
    if (updateVersionLine) updateVersionLine.textContent = "无法读取版本信息";
  }
}

async function checkForUpdate() {
  updateError?.classList.add("hidden");
  updateNotes?.classList.add("hidden");
  btnApplyUpdate?.classList.add("hidden");
  pendingUpdate = null;
  if (btnCheckUpdate) {
    btnCheckUpdate.disabled = true;
    btnCheckUpdate.textContent = "检查中…";
  }
  try {
    const info = await api("/api/update/check", { method: "POST" });
    renderUpdateStatus(info);
    if (!info.ok) {
      if (updateError) {
        updateError.textContent = info.error || "检查失败";
        updateError.classList.remove("hidden");
      }
      return;
    }
    if (info.update_available) {
      pendingUpdate = info;
      if (updateNotes) {
        updateNotes.textContent = `发现新版本 ${info.latest}：${info.notes || "点击安装后需重启应用"}`;
        updateNotes.classList.remove("hidden");
      }
      btnApplyUpdate?.classList.remove("hidden");
    } else if (updateVersionLine) {
      updateVersionLine.textContent = `已是最新 ${info.current}（${info.source === "runtime" ? "热更新" : "内置"}）`;
    }
  } catch (e) {
    if (updateError) {
      updateError.textContent = e.message;
      updateError.classList.remove("hidden");
    }
  } finally {
    if (btnCheckUpdate) {
      btnCheckUpdate.disabled = false;
      btnCheckUpdate.textContent = "检查更新";
    }
  }
}

async function applyPendingUpdate() {
  if (!pendingUpdate?.url) return;
  updateError?.classList.add("hidden");
  if (btnApplyUpdate) {
    btnApplyUpdate.disabled = true;
    btnApplyUpdate.textContent = "下载中…";
  }
  try {
    const res = await api("/api/update/apply", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url: pendingUpdate.url, sha256: pendingUpdate.sha256 || "" }),
    });
    alert(res.message || "更新已安装，请重启应用");
    btnApplyUpdate?.classList.add("hidden");
    pendingUpdate = null;
    await refreshUpdateStatus();
  } catch (e) {
    if (updateError) {
      updateError.textContent = e.message;
      updateError.classList.remove("hidden");
    }
  } finally {
    if (btnApplyUpdate) {
      btnApplyUpdate.disabled = false;
      btnApplyUpdate.textContent = "下载并安装";
    }
  }
}

async function saveLlmSettings(e) {
  e?.preventDefault();
  llmSettingsError?.classList.add("hidden");
  const payload = {
    base_url: llmSettingsBase?.value.trim() || "",
    model: llmSettingsModel?.value.trim() || "",
  };
  const key = llmSettingsKey?.value.trim();
  if (key) payload.api_key = key;
  try {
    llmStatus = await api("/api/settings/llm", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (llmStatus.source === "user") llmStatus.needs_setup = false;
    updateLlmStatusUI();
    llmStartupDialog?.close();
    llmSettingsDialog?.close();
  } catch (err) {
    if (llmSettingsError) {
      llmSettingsError.textContent = err.message;
      llmSettingsError.classList.remove("hidden");
    }
  }
}

async function clearLlmKey() {
  if (!confirm("确定清除已保存的 API Key？")) return;
  llmSettingsError?.classList.add("hidden");
  try {
    llmStatus = await api("/api/settings/llm", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ api_key: "" }),
    });
    if (llmSettingsKey) llmSettingsKey.value = "";
    renderLlmSettingsStatus();
    updateLlmStatusUI();
  } catch (err) {
    if (llmSettingsError) {
      llmSettingsError.textContent = err.message;
      llmSettingsError.classList.remove("hidden");
    }
  }
}

const btnBack = $("#btn-back");
const btnDeep = $("#btn-deep");
const btnDeepPrompt = $("#btn-deep-prompt");
const deepPromptDialog = $("#deep-prompt-dialog");
const deepPromptForm = $("#deep-prompt-form");
const deepPromptText = $("#deep-prompt-text");
const deepPromptMeta = $("#deep-prompt-meta");
const deepPromptError = $("#deep-prompt-error");
const deepPromptPresets = $("#deep-prompt-presets");
const btnDeepPromptDeleteMode = $("#deep-prompt-delete-mode");
const btnDeepPromptSaveAsPreset = $("#deep-prompt-save-as-preset");
const presetSaveDialog = $("#preset-save-dialog");
const presetSaveName = $("#preset-save-name");
const presetSaveIconPreview = $("#preset-save-icon-preview");
const presetSaveEmojiGrid = $("#preset-save-emoji-grid");

const PRESET_EMOJIS = [
  "📋", "📖", "✨", "🗣️", "💬", "📝", "🎯", "💡",
  "🧠", "📚", "✏️", "🌟", "🔥", "💎", "🎓", "👶",
  "🤓", "📊", "🗺️", "🧩", "⚡", "🌿", "🎨", "🔖",
];
let _selectedPresetEmoji = "✨";

let deepPromptDeleteMode = false;
/** 'preset' = 编辑全局风格；'custom' = 本书一次性（仅 + 进入） */
let deepPromptEditMode = "preset";
/** 仅 + 选中时为 true，控制「保存新风格」按钮 */
let deepPromptPlusMode = false;

function setDeepPromptDeleteMode(on) {
  deepPromptDeleteMode = !!on;
  btnDeepPromptDeleteMode?.classList.toggle("active", deepPromptDeleteMode);
  deepPromptPresets?.classList.toggle("delete-mode", deepPromptDeleteMode);
  if (btnDeepPromptDeleteMode) {
    btnDeepPromptDeleteMode.title = deepPromptDeleteMode ? "完成" : "删除自定义风格";
    btnDeepPromptDeleteMode.setAttribute(
      "aria-label",
      deepPromptDeleteMode ? "完成删除" : "删除自定义风格"
    );
  }
}

function syncPresetDeleteModeBtn(data) {
  const hasUser = (data.presets || []).some((p) => !p.builtin);
  btnDeepPromptDeleteMode?.classList.toggle("hidden", !hasUser);
  if (!hasUser) setDeepPromptDeleteMode(false);
}
const btnPreviewInline = $("#btn-preview-inline");
const readerTitle = $("#reader-title");
const importDialog = $("#import-dialog");
const importForm = $("#import-form");
const importTitle = $("#import-title");
const importTag = $("#import-tag");
const importFile = $("#import-file");
const importSplit = $("#import-split");
const importDetect = $("#import-detect");
const importError = $("#import-error");
const importCancel = $("#import-cancel");
const nav = $("#nav");
const layout = $("#layout");
const workspace = $("#workspace");
const mainPanel = $("#main");
const sourceHeader = $("#source-header");
const sourcePanel = $("#source-body");
const summaryPanel = $("#summary-body");
const summaryHeader = $("#summary-header");
const summaryStreamStats = $("#summary-stream-stats");
const chatSection = $("#chat-section");
const toggleSide = $("#toggle-side");
const toggleNav = $("#toggle-nav");
const btnSummaryFullscreen = $("#btn-summary-fullscreen");
const sidePanel = $("#side-panel");
const handleSide = $("#handle-side");
const handleOverviewChat = $("#handle-overview-chat");
const handleSummaryChat = $("#handle-summary-chat");
const chatMessages = $("#chat-messages");
const chatForm = $("#chat-form");
const chatInput = $("#chat-input");
const chatSend = $("#chat-send");
const btnChatCross = $("#btn-chat-cross");

const LAYOUT_KEY = "book-compiler-layout";
const CHAT_KEY = "book-compiler-chats";
const CHAT_PAGEINDEX_KEY = "book-compiler-chat-pageindex";
const READER_KEY = "book-compiler-reader";

const TEXT_IMPORT_EXTS = new Set([".txt", ".md", ".markdown"]);


/** @type {Map<string, { status: string, title: string, buffer: string, force: boolean, error?: string, abort?: AbortController }>} */
const deepJobs = new Map();

function getDeepJob(ch) {
  return ch ? deepJobs.get(ch) || null : null;
}

function isChapterDeepGenerating(ch) {
  const s = getDeepJob(ch)?.status;
  return s === "streaming" || s === "finalizing";
}

function chapterHasApprovedSummary(chapterId) {
  const ch = (state.meta?.chapters || []).find((c) => c.id === chapterId);
  return ch?.status === "approved";
}

function chapterSummaryFile(chapterId) {
  return `chapters/${chapterId}.md`;
}

function releaseDeepJob(ch, job) {
  if (job && deepJobs.get(ch) === job) deepJobs.delete(ch);
  syncDeepGeneratingState();
}

function syncDeepGeneratingState() {
  state.deepGenerating = state.currentChapter
    ? isChapterDeepGenerating(state.currentChapter)
    : false;
  syncGenerateButtons();
}

function attachDeepStreamView(ch) {
  const job = getDeepJob(ch);
  if (!job) return false;
  if (job.status === "streaming" || job.status === "finalizing") {
    setSummaryStreamingHtml(job.title, job.buffer, {
      showCursor: job.status === "streaming",
      streaming: job.status === "streaming",
    });
    applySummaryStatsFromJob(job, job.status === "finalizing" ? "saving" : "streaming");
    startSummaryStatsTicker(ch, job);
    return true;
  }
  if (job.status === "error") {
    setSummaryMessage(`<p class="loading">生成失败：${escapeHtml(job.error || "未知错误")}</p>`);
    summaryPanel.innerHTML += `<div class="content-toolbar">${inlineIconBtn("deep-retry", "refresh", "重试")}</div>`;
    $("#deep-retry")?.addEventListener("click", () => runDeepSummary(job.force));
    return true;
  }
  return false;
}

let state = {
  slug: null,
  meta: null,
  currentChapter: null,
  currentFile: "overview.md",
  sideOpen: true,
  navOpen: true,
  summaryFullscreen: false,
  chatHistory: {},
  chatSending: false,
  usePageIndex: false,
  summaryExists: false,
  overviewExists: false,
  deepGenerating: false,
  previewGenerating: false,
  pdfPage: null,
  pdfPageMode: false,
};

function uid() {
  return "m" + Date.now().toString(36) + Math.random().toString(36).slice(2, 6);
}

function escapeHtml(s) {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

async function api(path, opts) {
  const r = await fetch(path, opts);
  const text = await r.text();
  let data;
  try { data = JSON.parse(text); } catch { throw new Error(text || `HTTP ${r.status}`); }
  if (!r.ok) {
    const msg = data.error || text;
    if (r.status === 404 && (path === "/api/books" || path.endsWith("/api/books")) && opts?.method === "POST") {
      throw new Error("导入 API 不可用：请重启 ./run-ui.sh（旧进程可能仍在运行）");
    }
    if (r.status === 404 && path.includes("/deep-prompt")) {
      throw new Error("Prompt API 不可用：请重启 ./run-ui.sh 后重试");
    }
    throw new Error(msg);
  }
  return data;
}

function applyLayout() {
  const saved = JSON.parse(localStorage.getItem(LAYOUT_KEY) || "{}");
  document.documentElement.style.setProperty("--nav-w", `${saved.navW || 240}px`);
  document.documentElement.style.setProperty("--side-w", `${saved.sideW || 420}px`);
  document.documentElement.style.setProperty("--summary-ratio", saved.summaryRatio ?? saved.sourceRatio ?? 0.55);
  if (saved.overviewChatW) {
    document.documentElement.style.setProperty("--overview-chat-w", `${saved.overviewChatW}px`);
  }
  if (saved.navOpen === false) state.navOpen = false;
}

function applyReaderPrefs() {
  const saved = JSON.parse(localStorage.getItem(READER_KEY) || "{}");
  const size = saved.fontSize || 17;
  const theme = saved.theme || "paper";
  document.documentElement.style.setProperty("--reader-size", `${size}px`);
  document.documentElement.dataset.readerTheme = theme;
  const btnTheme = $("#btn-theme");
  if (btnTheme) {
    setBtnIcon(btnTheme, theme === "night" ? "sun" : "moon");
    btnTheme.title = theme === "night" ? "切换纸书主题" : "切换夜间主题";
  }
}

function saveReaderPrefs(patch) {
  const saved = JSON.parse(localStorage.getItem(READER_KEY) || "{}");
  Object.assign(saved, patch);
  localStorage.setItem(READER_KEY, JSON.stringify(saved));
  applyReaderPrefs();
}

const SUMMARY_STATS_KEY = "beanread-summary-stats";
let summaryStatsTicker = null;

function estimateTokensClient(text) {
  if (!text) return 0;
  let cjk = 0;
  for (const c of text) {
    if (c >= "\u4e00" && c <= "\u9fff") cjk += 1;
  }
  return Math.max(0, Math.round(cjk * 0.85 + (text.length - cjk) / 4));
}

function summaryStatsStorageKey(slug, ch) {
  return `${slug || state.slug}:${ch}`;
}

function loadPersistedSummaryStats(slug, ch) {
  if (!slug || !ch) return null;
  try {
    const all = JSON.parse(localStorage.getItem(SUMMARY_STATS_KEY) || "{}");
    return all[summaryStatsStorageKey(slug, ch)] || null;
  } catch {
    return null;
  }
}

function persistSummaryStats(slug, ch, stats) {
  if (!slug || !ch || !stats) return;
  try {
    const all = JSON.parse(localStorage.getItem(SUMMARY_STATS_KEY) || "{}");
    all[summaryStatsStorageKey(slug, ch)] = { ...stats, at: Date.now() };
    localStorage.setItem(SUMMARY_STATS_KEY, JSON.stringify(all));
  } catch {
    /* ignore quota */
  }
}

function streamElapsedSec(job, endMs = Date.now()) {
  const start = job.startedAt || job.firstTokenAt;
  if (!start) return 0;
  return Math.max(0, (endMs - start) / 1000);
}

function computeStreamTps(job, endMs = Date.now()) {
  const tokens = Number(job.streamTokens) || estimateTokensClient(job.buffer) || 0;
  if (!tokens) return 0;
  const elapsed = streamElapsedSec(job, endMs);
  if (elapsed < 0.05) return 0;
  return Math.round((tokens / elapsed) * 10) / 10;
}

function lockStreamStats(job, serverTps) {
  job.streamEndedAt = Date.now();
  job.streamTokens = job.streamTokens ?? estimateTokensClient(job.buffer);
  const local = computeStreamTps(job, job.streamEndedAt);
  const remote = Number(serverTps);
  job.streamTps =
    local > 0 ? local
    : Number.isFinite(remote) && remote > 0 ? remote
    : job.streamTps || 0;
}

function formatSummaryStatsLabel({ tokens, tps, exact = false, truncated = false, phase = "" } = {}) {
  const prefix = exact ? "" : "≈";
  const tok = Number(tokens) || 0;
  const rate = Number(tps) || 0;
  let label = `${prefix}${tok.toLocaleString()} tok · ${rate.toFixed(1)} t/s`;
  if (truncated) label += " · 已达 8192 上限";
  else if (phase === "saving") label += " · 保存中…";
  else if (phase === "streaming") label += " · 生成中…";
  else if (phase === "done") label += " · 完成";
  return label;
}

function setSummaryStreamStats(tokens, tps, opts = {}) {
  if (!summaryStreamStats) return;
  const label = formatSummaryStatsLabel({ tokens, tps, ...opts });
  const show = tokens != null || tps != null || opts.phase;
  const truncated = !!opts.truncated;

  if (!show) {
    summaryStreamStats.classList.add("hidden");
    summaryStreamStats.textContent = "";
    return;
  }
  summaryStreamStats.textContent = label;
  summaryStreamStats.classList.remove("hidden");
  summaryStreamStats.classList.toggle("summary-stream-stats-truncated", truncated);
  summaryStreamStats.classList.toggle("is-finalizing", opts.phase === "saving");
}

function clearSummaryStreamStats() {
  setSummaryStreamStats(null, null);
}

function stopSummaryStatsTicker() {
  if (summaryStatsTicker) {
    clearInterval(summaryStatsTicker);
    summaryStatsTicker = null;
  }
}

function startSummaryStatsTicker(ch, job) {
  stopSummaryStatsTicker();
  summaryStatsTicker = setInterval(() => {
    if (getDeepJob(ch) !== job) {
      stopSummaryStatsTicker();
      return;
    }
    if (job.status === "done" || job.status === "error") {
      stopSummaryStatsTicker();
      return;
    }
    const tokens = job.streamTokens ?? estimateTokensClient(job.buffer);
    job.streamTps = computeStreamTps(job);
    const sinceStart = Date.now() - (job.startedAt || Date.now());
    const idleMs = job.lastDeltaAt ? Date.now() - job.lastDeltaAt : sinceStart;
    if (job.status === "streaming" && idleMs > 120000) {
      job.status = "error";
      job.error = "生成超时（长时间无响应）";
      job.abort?.abort();
      stopSummaryStatsTicker();
      if (state.currentChapter === ch) {
        setSummaryMessage(`<p class="loading">生成超时：${escapeHtml(job.error)}</p>`);
        summaryPanel.innerHTML += `<div class="content-toolbar">${inlineIconBtn("deep-retry", "refresh", "重试")}</div>`;
        $("#deep-retry")?.addEventListener("click", () => runDeepSummary(job.force));
      }
      releaseDeepJob(ch, job);
      return;
    }
    if (job.status === "streaming" && job.buffer && idleMs > 1500) {
      job.status = "finalizing";
      lockStreamStats(job);
      if (state.currentChapter === ch) {
        setSummaryStreamingHtml(job.title, job.buffer, { showCursor: false, streaming: false });
        setSummaryStreamStats(job.streamTokens, job.streamTps, {
          exact: job.streamExact,
          truncated: job.streamTruncated,
          phase: "saving",
        });
      }
      syncDeepGeneratingState();
      return;
    }
    const phase = job.status === "finalizing" ? "saving" : "streaming";
    setSummaryStreamStats(job.streamTokens, job.streamTps, {
      exact: job.streamExact,
      truncated: job.streamTruncated,
      phase,
    });
  }, 350);
}

function removeSummaryStreamCursors() {
  summaryPanel?.classList.remove("summary-streaming");
  summaryPanel?.querySelectorAll(".stream-cursor").forEach((el) => el.remove());
}

function applySummaryStatsFromJob(job, phase = "done") {
  if (!job || job.streamTokens == null) return;
  lockStreamStats(job);
  setSummaryStreamStats(job.streamTokens, job.streamTps, {
    exact: job.streamExact,
    truncated: job.streamTruncated,
    phase,
  });
  if (state.slug && state.currentChapter) {
    persistSummaryStats(state.slug, state.currentChapter, {
      tokens: job.streamTokens,
      tps: job.streamTps,
      exact: job.streamExact,
      truncated: job.streamTruncated,
    });
  }
}

function restorePersistedSummaryStats(slug, ch) {
  const saved = loadPersistedSummaryStats(slug, ch);
  if (!saved) {
    clearSummaryStreamStats();
    return;
  }
  setSummaryStreamStats(saved.tokens, saved.tps, {
    exact: saved.exact,
    truncated: saved.truncated,
    phase: "done",
  });
}

function setSummaryHtml(html) {
  summaryPanel.className = "side-body summary-body article md-body reader";
  summaryPanel.innerHTML = html;
  renderMermaidIn(summaryPanel);
}

function isSummaryNearBottom(el, threshold = 96) {
  if (!el) return true;
  return el.scrollHeight - el.scrollTop - el.clientHeight <= threshold;
}

function setSummaryStreamingHtml(title, bodyMd, { showCursor = true, streaming = true } = {}) {
  const el = summaryPanel;
  const prevTop = el.scrollTop;
  const stickToBottom = isSummaryNearBottom(el);

  el.className = streaming
    ? "side-body summary-body article md-body reader summary-streaming"
    : "side-body summary-body article md-body reader";
  const header = title ? `<h1>${escapeHtml(title)} · 深度 Summary</h1>` : "";
  const body = bodyMd
    ? renderMd(bodyMd)
    : `<p class="summary-stream-placeholder">正在生成…${showCursor ? '<span class="stream-cursor">▍</span>' : ""}</p>`;
  el.innerHTML = header + body + (bodyMd && showCursor ? `<span class="stream-cursor stream-cursor-inline">▍</span>` : "");

  if (stickToBottom) el.scrollTop = el.scrollHeight;
  else el.scrollTop = prevTop;
}

function drainSseFrames(sseBuf, onEvent) {
  let buf = sseBuf;
  let idx;
  while ((idx = buf.indexOf("\n\n")) >= 0) {
    const frame = buf.slice(0, idx);
    buf = buf.slice(idx + 2);
    const evt = parseSseFrame(frame);
    if (evt) onEvent(evt);
  }
  return buf;
}

function finalizeDeepStreamUi(ch, job, { phase = "done" } = {}) {
  if (state.currentChapter !== ch) return;
  removeSummaryStreamCursors();
  if (!job.buffer?.trim()) return;
  const fullMd = `# ${job.title} · 深度 Summary\n\n${job.buffer}`;
  setSummaryHtml(renderMd(fullMd));
  linkifyAnchors(summaryPanel, ch);
  state.summaryExists = true;
  applySummaryStatsFromJob(job, phase);
}
function parseSseFrame(block) {
  let event = "message";
  const dataLines = [];
  for (const line of block.split("\n")) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
  }
  if (!dataLines.length) return null;
  try {
    return { event, data: JSON.parse(dataLines.join("\n")) };
  } catch {
    return null;
  }
}

async function consumeDeepSummaryStream(ch, force) {
  const ac = new AbortController();
  const job = {
    status: "streaming",
    title: chapterTitle(ch),
    buffer: "",
    force,
    abort: ac,
    streamTokens: 0,
    streamTps: 0,
    streamExact: false,
    streamTruncated: false,
    startedAt: Date.now(),
    firstTokenAt: null,
    lastDeltaAt: null,
    streamEndedAt: null,
  };
  deepJobs.set(ch, job);
  syncDeepGeneratingState();

  if (state.currentChapter === ch) {
    setSummaryStreamingHtml(job.title, "");
    setSummaryStreamStats(0, 0, { phase: "streaming" });
    startSummaryStatsTicker(ch, job);
  }

  let renderTimer = null;
  let doneReceived = false;

  const clearRenderTimer = () => {
    if (renderTimer) {
      clearTimeout(renderTimer);
      renderTimer = null;
    }
  };

  const scheduleRender = () => {
    if (renderTimer) return;
    renderTimer = setTimeout(() => {
      renderTimer = null;
      if (state.currentChapter !== ch || job.status !== "streaming") return;
      setSummaryStreamingHtml(job.title, job.buffer, { showCursor: true, streaming: true });
    }, 220);
  };

  const handleSseEvent = (evt) => {
    if (evt.event === "meta" && evt.data.title) {
      job.title = evt.data.title;
      return;
    }
    if (evt.event === "delta") {
      job.buffer += evt.data.text || "";
      job.lastDeltaAt = Date.now();
      if (job.firstTokenAt == null) job.firstTokenAt = Date.now();
      if (evt.data.tokens != null) {
        job.streamTokens = evt.data.tokens;
        job.streamExact = !!evt.data.tokens_exact;
      } else {
        job.streamTokens = estimateTokensClient(job.buffer);
      }
      job.streamTps = computeStreamTps(job);
      scheduleRender();
      if (state.currentChapter === ch) {
        setSummaryStreamStats(job.streamTokens, job.streamTps, {
          exact: job.streamExact,
          truncated: job.streamTruncated,
          phase: "streaming",
        });
      }
      return;
    }
    if (evt.event === "stream_end") {
      job.status = "finalizing";
      if (evt.data.tokens != null) {
        job.streamTokens = evt.data.tokens;
        job.streamExact = !!evt.data.tokens_exact;
        job.streamTruncated = !!evt.data.truncated;
      }
      lockStreamStats(job, evt.data.tps);
      clearRenderTimer();
      if (state.currentChapter === ch) {
        setSummaryStreamingHtml(job.title, job.buffer, { showCursor: false, streaming: false });
        setSummaryStreamStats(job.streamTokens, job.streamTps, {
          exact: job.streamExact,
          truncated: job.streamTruncated,
          phase: "saving",
        });
      }
      syncDeepGeneratingState();
      return;
    }
    if (evt.event === "error") {
      throw new Error(evt.data.error || "生成失败");
    }
    if (evt.event === "done") {
      doneReceived = true;
      job.status = "done";
      if (evt.data.tokens != null) {
        job.streamTokens = evt.data.tokens;
        job.streamExact = !!evt.data.tokens_exact;
        job.streamTruncated = !!evt.data.truncated;
      }
      lockStreamStats(job, evt.data.tps);
      stopSummaryStatsTicker();
      clearRenderTimer();
      if (state.currentChapter === ch) {
        if (job.buffer.trim()) {
          finalizeDeepStreamUi(ch, job, { phase: "done" });
        } else {
          void reloadChapterSummaryFromDisk(ch).catch((err) => {
            if (state.currentChapter === ch) {
              setSummaryMessage(`<p class="loading">Summary 保存后加载失败：${escapeHtml(err.message)}</p>`);
            }
          });
        }
      }
      syncDeepGeneratingState();
    }
  };

  try {
    const r = await fetch(
      `/api/books/${encodeURIComponent(state.slug)}/deep/${encodeURIComponent(ch)}`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ force, stream: true }),
        signal: ac.signal,
      }
    );

    if (!r.ok) {
      const text = await r.text();
      let msg = text;
      try { msg = JSON.parse(text).error || text; } catch { /* keep text */ }
      throw new Error(msg || `HTTP ${r.status}`);
    }

    const reader = r.body.getReader();
    const dec = new TextDecoder();
    let sseBuf = "";

    while (true) {
      const { done, value } = await reader.read();
      if (value) sseBuf += dec.decode(value, { stream: true });
      sseBuf = drainSseFrames(sseBuf, handleSseEvent);
      if (done) break;
    }
    sseBuf += dec.decode();
    drainSseFrames(sseBuf, handleSseEvent);

    stopSummaryStatsTicker();
    clearRenderTimer();

    if (doneReceived) {
      releaseDeepJob(ch, job);
      try {
        state.meta = await api(`/api/books/${encodeURIComponent(state.slug)}/meta`);
      } catch { /* meta refresh is best-effort */ }
      if (state.currentChapter === ch) summaryPanel.scrollTop = 0;
      syncDeepGeneratingState();
      return;
    }

    throw new Error("生成未完成（连接中断）");
  } catch (err) {
    if (err.name === "AbortError") {
      stopSummaryStatsTicker();
      releaseDeepJob(ch, job);
      return;
    }
    stopSummaryStatsTicker();
    job.status = "error";
    job.error = err.message;
    removeSummaryStreamCursors();
    if (state.currentChapter === ch) {
      setSummaryMessage(`<p class="loading">生成失败：${escapeHtml(err.message)}</p>`);
      summaryPanel.innerHTML += `<div class="content-toolbar">${inlineIconBtn("deep-retry", "refresh", "重试")}</div>`;
      $("#deep-retry")?.addEventListener("click", () => runDeepSummary(force));
    }
    releaseDeepJob(ch, job);
    syncDeepGeneratingState();
  } finally {
    clearRenderTimer();
  }
}

function setSummaryMessage(html) {
  summaryPanel.className = "side-body summary-body";
  summaryPanel.innerHTML = html;
}

function isPageMarker(text) {
  return /^---\s*第\s*\d+\s*页\s*---$/.test(text.trim());
}

function renderSourceLines(lines, full, garbageCount = 0) {
  const blocks = [];
  let para = [];

  const flushPara = () => {
    if (para.length) blocks.push({ type: "para", lines: para.splice(0) });
  };

  for (const l of lines) {
    if (l.corrupt || isPageMarker(l.text)) {
      flushPara();
      continue;
    }
    if (!l.text.trim()) {
      flushPara();
      continue;
    }
    para.push({ ...l, cls: !full ? "highlight" : "" });
    if (/[。！？；」』"']$/.test(l.text.trim())) flushPara();
  }
  flushPara();

  const html = blocks.map((b) => {
    const inner = b.lines.map((l, i) => {
      const hl = l.cls === "highlight" ? " highlight" : "";
      const cont = i > 0 ? " continued" : "";
      return `<span class="source-line${hl}${cont}" data-line="${l.n}">` +
        (i === 0 ? `<span class="num">${l.n}</span>` : "") +
        `<span class="text">${escapeHtml(l.text)}</span></span>`;
    }).join("");
    return `<p class="source-para">${inner}</p>`;
  }).join("");

  const pageMarkers = lines.filter((l) => isPageMarker(l.text)).length;
  const skipped = garbageCount + pageMarkers;
  const hidden = skipped > 0
    ? `<div class="source-warn">已略去 ${skipped} 行 PDF 页码/乱码，正文连续阅读；行号与锚点仍按原文件计。</div>`
    : "";
  const meta = full
    ? `<div class="source-meta">${lines.length} 行</div>`
    : `<div class="source-meta">锚点范围 · ${lines.length} 行</div>`;
  return `<div class="source-reader article reader">${hidden}${meta}<div class="source-flow">${html}</div></div>`;
}

function destroyEpubViewer() {}

function pdfBaseUrl() {
  return `/api/books/${encodeURIComponent(state.slug)}/pdf`;
}

const pdfJsState = {
  doc: null,
  loadPromise: null,
  slug: null,
  renderSeq: 0,
  scale: null,
  autoFit: true,
  totalPages: 0,
  layoutReady: false,
  renderedPages: new Set(),
  observer: null,
  scrollRaf: 0,
};

function destroyPdfViewer() {
  pdfJsState.renderSeq++;
  if (pdfJsState.observer) {
    pdfJsState.observer.disconnect();
    pdfJsState.observer = null;
  }
  if (pdfJsState.doc) {
    try { pdfJsState.doc.destroy(); } catch (_) {}
  }
  pdfJsState.doc = null;
  pdfJsState.loadPromise = null;
  pdfJsState.slug = null;
  pdfJsState.scale = null;
  pdfJsState.autoFit = true;
  pdfJsState.totalPages = 0;
  pdfJsState.layoutReady = false;
  pdfJsState.renderedPages = new Set();
}

function ensurePdfJsWorker() {
  if (typeof pdfjsLib === "undefined") return false;
  if (!pdfjsLib.GlobalWorkerOptions.workerSrc) {
    pdfjsLib.GlobalWorkerOptions.workerSrc = "/vendor/pdf.worker.min.js";
  }
  return true;
}

function ensurePdfJsShell() {
  sourcePanel.classList.add("native-mode");
  let wrap = sourcePanel.querySelector(".pdf-viewer-wrap");
  if (!wrap) {
    sourcePanel.innerHTML = "";
    wrap = document.createElement("div");
    wrap.className = "pdf-viewer-wrap";
    wrap.innerHTML = `
      <div class="pdf-toolbar">
        <button type="button" class="btn-icon pdf-prev" title="上一页" aria-label="上一页">‹</button>
        <div class="pdf-page-input-wrap">
          <input type="number" class="pdf-page-input" min="1" value="1" aria-label="页码" />
          <span class="pdf-page-total">/ —</span>
        </div>
        <button type="button" class="btn-icon pdf-next" title="下一页" aria-label="下一页">›</button>
        <span class="pdf-toolbar-spacer"></span>
        <button type="button" class="btn-icon pdf-zoom-out" title="缩小" aria-label="缩小">−</button>
        <button type="button" class="btn-icon pdf-zoom-in" title="放大" aria-label="放大">+</button>
      </div>
      <div class="pdf-js-viewer">
        <p class="loading pdf-loading">正在加载 PDF…</p>
        <div class="pdf-pages-stack"></div>
      </div>`;
    sourcePanel.appendChild(wrap);
    bindPdfToolbar(wrap);
  }
  return {
    wrap,
    viewer: wrap.querySelector(".pdf-js-viewer"),
    stack: wrap.querySelector(".pdf-pages-stack"),
    loading: wrap.querySelector(".pdf-loading"),
    pageInput: wrap.querySelector(".pdf-page-input"),
    pageTotal: wrap.querySelector(".pdf-page-total"),
  };
}

function bindPdfToolbar(wrap) {
  if (wrap.dataset.bound) return;
  wrap.dataset.bound = "1";
  wrap.addEventListener("click", (e) => {
    if (!sourcePanel.classList.contains("native-mode")) return;
    if (e.target.closest(".pdf-prev")) stepPdfPage(-1);
    else if (e.target.closest(".pdf-next")) stepPdfPage(1);
    else if (e.target.closest(".pdf-zoom-in")) adjustPdfZoom(1.15);
    else if (e.target.closest(".pdf-zoom-out")) adjustPdfZoom(1 / 1.15);
  });
  wrap.querySelector(".pdf-page-input")?.addEventListener("change", (e) => {
    const p = parseInt(e.target.value, 10);
    if (p >= 1) goToPdfPage(p);
  });
  wrap.querySelector(".pdf-page-input")?.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      const p = parseInt(e.target.value, 10);
      if (p >= 1) goToPdfPage(p);
    }
  });
}

function updatePdfToolbar(page, total) {
  const shell = sourcePanel.querySelector(".pdf-viewer-wrap");
  if (!shell) return;
  const input = shell.querySelector(".pdf-page-input");
  const totalEl = shell.querySelector(".pdf-page-total");
  if (input) {
    input.max = String(total);
    input.value = String(page);
  }
  if (totalEl) totalEl.textContent = `/ ${total}`;
}

function prefetchPdf() {
  if (!state.slug || !hasPdfAsset() || !ensurePdfJsWorker()) return;
  if (pdfJsState.slug === state.slug && (pdfJsState.doc || pdfJsState.loadPromise)) return;
  loadPdfDocument().catch(() => {});
}

async function loadPdfDocument(onProgress) {
  if (!ensurePdfJsWorker()) throw new Error("PDF.js 未加载");
  if (pdfJsState.slug !== state.slug) destroyPdfViewer();
  if (pdfJsState.doc) return pdfJsState.doc;
  if (!pdfJsState.loadPromise) {
    pdfJsState.slug = state.slug;
    const task = pdfjsLib.getDocument({
      url: pdfBaseUrl(),
      disableRange: false,
      disableStream: false,
      rangeChunkSize: 65536 * 8,
      isEvalSupported: false,
    });
    task.onProgress = ({ loaded, total }) => {
      if (onProgress && total > 0) onProgress(loaded, total);
    };
    pdfJsState.loadPromise = task.promise;
  }
  pdfJsState.doc = await pdfJsState.loadPromise;
  return pdfJsState.doc;
}

function getPdfScale(viewer, pdfPage) {
  let scale = pdfJsState.scale;
  if (pdfJsState.autoFit || !scale) {
    const base = pdfPage.getViewport({ scale: 1 });
    const w = Math.max(320, (viewer.clientWidth || sourcePanel.clientWidth || 720) - 24);
    scale = w / base.width;
    scale = Math.min(2.5, Math.max(0.35, scale));
    if (pdfJsState.autoFit) pdfJsState.scale = scale;
  }
  return scale;
}

function ensurePdfLoading(shell) {
  let loading = shell.viewer?.querySelector(".pdf-loading");
  if (!loading && shell.viewer) {
    loading = document.createElement("p");
    loading.className = "loading pdf-loading";
    shell.viewer.insertBefore(loading, shell.stack);
  }
  return loading;
}

function bindPdfScroll(shell) {
  if (shell.viewer.dataset.scrollBound) return;
  shell.viewer.dataset.scrollBound = "1";
  shell.viewer.addEventListener("scroll", () => {
    if (pdfJsState.scrollRaf) return;
    pdfJsState.scrollRaf = requestAnimationFrame(() => {
      pdfJsState.scrollRaf = 0;
      syncPdfPageFromScroll(shell);
    });
  }, { passive: true });
}

function syncPdfPageFromScroll(shell) {
  if (!shell.stack || !pdfJsState.totalPages) return;
  const top = shell.viewer.scrollTop + 48;
  let current = 1;
  for (const slot of shell.stack.querySelectorAll(".pdf-page-slot")) {
    if (slot.offsetTop <= top) current = parseInt(slot.dataset.page, 10);
    else break;
  }
  if (current === state.pdfPage) return;
  state.pdfPage = current;
  updatePdfToolbar(current, pdfJsState.totalPages);
  const ch = state.currentChapter;
  if (ch) {
    const label = chapterTitle(ch);
    sourceHeader.textContent = `${label} · PDF · P${current}`;
  }
}

function bindPdfLazyRender(shell) {
  if (pdfJsState.observer) pdfJsState.observer.disconnect();
  pdfJsState.observer = new IntersectionObserver(
    (entries) => {
      entries.forEach((e) => {
        if (!e.isIntersecting) return;
        const p = parseInt(e.target.dataset.page, 10);
        if (p) renderPdfPageSlot(p);
      });
    },
    { root: shell.viewer, rootMargin: "600px 0px", threshold: 0.01 }
  );
  shell.stack.querySelectorAll(".pdf-page-slot").forEach((slot) => {
    pdfJsState.observer.observe(slot);
  });
}

async function initPdfScrollLayout(doc, shell) {
  const page1 = await doc.getPage(1);
  const scale = getPdfScale(shell.viewer, page1);
  const vp = page1.getViewport({ scale });
  const slotH = Math.floor(vp.height) + 12;

  shell.stack.innerHTML = "";
  const frag = document.createDocumentFragment();
  for (let i = 1; i <= doc.numPages; i++) {
    const slot = document.createElement("div");
    slot.className = "pdf-page-slot";
    slot.dataset.page = String(i);
    slot.style.minHeight = `${slotH}px`;
    const canvas = document.createElement("canvas");
    canvas.className = "pdf-canvas";
    slot.appendChild(canvas);
    frag.appendChild(slot);
  }
  shell.stack.appendChild(frag);

  pdfJsState.totalPages = doc.numPages;
  pdfJsState.layoutReady = true;
  pdfJsState.renderedPages = new Set();
  updatePdfToolbar(1, doc.numPages);
  bindPdfScroll(shell);
  bindPdfLazyRender(shell);
}

async function ensurePdfLayout(shell, onProgress) {
  const doc = await loadPdfDocument(onProgress);
  if (!pdfJsState.layoutReady || !shell.stack?.childElementCount) {
    await initPdfScrollLayout(doc, shell);
  }
  return doc;
}

async function renderPdfPageSlot(pageNum) {
  if (!pageNum || pdfJsState.renderedPages.has(pageNum)) return;
  const seq = pdfJsState.renderSeq;
  const shell = ensurePdfJsShell();
  const slot = shell.stack?.querySelector(`.pdf-page-slot[data-page="${pageNum}"]`);
  if (!slot || !pdfJsState.doc) return;

  const canvas = slot.querySelector("canvas");
  const page = await pdfJsState.doc.getPage(pageNum);
  if (seq !== pdfJsState.renderSeq) return;

  const scale = getPdfScale(shell.viewer, page);
  const viewport = page.getViewport({ scale });
  canvas.width = Math.floor(viewport.width);
  canvas.height = Math.floor(viewport.height);
  slot.style.minHeight = `${Math.floor(viewport.height) + 12}px`;

  await page.render({ canvasContext: canvas.getContext("2d"), viewport, canvas }).promise;
  if (seq !== pdfJsState.renderSeq) return;

  pdfJsState.renderedPages.add(pageNum);
  slot.classList.add("pdf-page-rendered");
}

async function renderPdfPagesAround(pageNum) {
  const total = pdfJsState.totalPages;
  const pages = [pageNum];
  for (let d = 1; d <= 2; d++) {
    if (pageNum - d >= 1) pages.push(pageNum - d);
    if (pageNum + d <= total) pages.push(pageNum + d);
  }
  await Promise.all(pages.map((p) => renderPdfPageSlot(p)));
}

async function relayoutPdfPages() {
  pdfJsState.renderSeq++;
  pdfJsState.renderedPages = new Set();
  const shell = ensurePdfJsShell();
  if (!pdfJsState.doc || !shell.stack) return;

  const page1 = await pdfJsState.doc.getPage(1);
  const vp = page1.getViewport({ scale: getPdfScale(shell.viewer, page1) });
  const slotH = Math.floor(vp.height) + 12;

  shell.stack.querySelectorAll(".pdf-page-slot").forEach((slot) => {
    slot.style.minHeight = `${slotH}px`;
    slot.classList.remove("pdf-page-rendered");
    const c = slot.querySelector("canvas");
    if (c) { c.width = 0; c.height = 0; }
  });

  const center = state.pdfPage || 1;
  await renderPdfPagesAround(center);
}

async function renderPdfPage(pageNum) {
  const seq = ++pdfJsState.renderSeq;
  const shell = ensurePdfJsShell();
  const loading = ensurePdfLoading(shell);

  const reportProgress = (loaded, total) => {
    if (seq !== pdfJsState.renderSeq) return;
    const pct = total > 0 ? Math.round((loaded / total) * 100) : 0;
    loading.textContent = pct > 0 ? `正在加载 PDF… ${pct}%` : "正在加载 PDF…";
  };

  loading.style.display = "flex";

  try {
    await ensurePdfLayout(shell, reportProgress);
    if (seq !== pdfJsState.renderSeq) return;

    const page = Math.max(1, Math.min(pdfJsState.totalPages, pageNum));
    await renderPdfPagesAround(page);
    if (seq !== pdfJsState.renderSeq) return;

    const slot = shell.stack.querySelector(`.pdf-page-slot[data-page="${page}"]`);
    if (slot) slot.scrollIntoView({ block: "start", behavior: "auto" });

    state.pdfPage = page;
    loading.style.display = "none";
    updatePdfToolbar(page, pdfJsState.totalPages);
  } catch (e) {
    if (seq !== pdfJsState.renderSeq) return;
    loading.style.display = "flex";
    loading.textContent = `PDF 加载失败：${e.message || e}`;
    throw e;
  }
}

async function goToPdfPage(pageNum, chapterId = null) {
  if (chapterId) sourcePanel.dataset.viewChapter = chapterId;
  await renderPdfPage(pageNum);
}

function stepPdfPage(delta) {
  if (!state.pdfPage || !pdfJsState.doc) return;
  const next = state.pdfPage + delta;
  if (next < 1 || next > pdfJsState.doc.numPages) return;
  const label = chapterTitle(state.currentChapter);
  sourceHeader.textContent = `${label} · PDF · P${next}`;
  goToPdfPage(next);
}

function adjustPdfZoom(factor) {
  pdfJsState.autoFit = false;
  pdfJsState.scale = Math.min(3, Math.max(0.35, (pdfJsState.scale || 1) * factor));
  relayoutPdfPages();
}

async function resolvePdfPage(chapterId, lineNo = null) {
  const q = lineNo ? `?line=${lineNo}` : "";
  const loc = await api(
    `/api/books/${encodeURIComponent(state.slug)}/pdf-location/${encodeURIComponent(chapterId)}${q}`
  );
  return loc.page || 1;
}

async function loadPdfSource(chapterId, lineNo = null) {
  const label = chapterTitle(chapterId);
  state.pdfPageMode = true;

  if (!hasPdfAsset()) {
    sourcePanel.classList.remove("native-mode");
    state.pdfPage = null;
    sourcePanel.innerHTML =
      '<p class="source-hint">此书由 PDF 导入但未保留原文件，请重新导入以使用 PDF 阅读。<br>当前显示文字层预览。</p>';
    const start = lineNo || 1;
    return loadSource(chapterId, start, lineNo ? lineNo : 0);
  }

  let page = 1;
  try {
    page = await resolvePdfPage(chapterId, lineNo);
  } catch (e) {
    sourcePanel.classList.remove("native-mode");
    state.pdfPage = null;
    sourcePanel.innerHTML = `<p class="loading">${escapeHtml(e.message)}</p>`;
    return;
  }

  const shell = ensurePdfJsShell();
  sourceHeader.textContent = `${label} · PDF · P${page}`;
  sourcePanel.dataset.viewChapter = chapterId;

  const same =
    state.pdfPage === page &&
    sourcePanel.dataset.viewChapter === chapterId &&
    pdfJsState.layoutReady;
  if (same) {
    const slot = shell.stack?.querySelector(`.pdf-page-slot[data-page="${page}"]`);
    if (slot) slot.scrollIntoView({ block: "start", behavior: "auto" });
    return;
  }

  try {
    await goToPdfPage(page, chapterId);
  } catch (e) {
    sourcePanel.classList.remove("native-mode");
    sourcePanel.innerHTML =
      `<p class="source-hint">PDF 渲染失败：${escapeHtml(e.message)}</p>`;
  }
}

function hasPdfAsset() {
  return !!(state.meta?.ingest?.pdf_file);
}

function hasEpubAsset() {
  return !!(state.meta?.ingest?.epub_file);
}

function nativeViewerKind() {
  const fmt = state.meta?.ingest?.source_format || "";
  if (hasPdfAsset() || fmt.startsWith("pdf")) return "pdf";
  if (hasEpubAsset() || fmt === "epub") return "epub";
  return null;
}

async function loadEpubSource(chapterId, lineNo = null) {
  const label = chapterTitle(chapterId);
  sourceHeader.textContent = lineNo == null
    ? `${label} · EPUB`
    : `${label} · EPUB · L${lineNo}`;

  destroyEpubViewer();
  sourcePanel.classList.remove("native-mode");
  state.pdfPage = null;
  sourcePanel.innerHTML = '<p class="loading">加载 EPUB…</p>';

  if (!hasEpubAsset()) {
    sourcePanel.innerHTML =
      '<p class="source-hint">此书由 EPUB 导入但未保留原文件，请重新导入以使用 EPUB 阅读。<br>当前显示文字层预览。</p>';
    const start = lineNo || 1;
    return loadSource(chapterId, start, lineNo ? lineNo : 0);
  }

  try {
    const data = await api(
      `/api/books/${encodeURIComponent(state.slug)}/epub-chapter/${encodeURIComponent(chapterId)}`
    );
    sourcePanel.innerHTML = `<div class="epub-html-reader article reader">${data.html}</div>`;
    sourcePanel.dataset.viewChapter = chapterId;
    sourcePanel.scrollTop = 0;
  } catch (e) {
    sourcePanel.innerHTML =
      `<p class="source-hint">EPUB 渲染失败：${escapeHtml(e.message)}<br>已切换为文字层预览。</p>`;
    const start = lineNo || 1;
    return loadSource(chapterId, start, lineNo ? lineNo : 0);
  }
}

async function loadNativeSource(chapterId, lineNo = null) {
  const kind = nativeViewerKind();
  if (kind === "pdf") return loadPdfSource(chapterId, lineNo);
  if (kind === "epub") return loadEpubSource(chapterId, lineNo);
  return loadSource(chapterId, lineNo || 1, lineNo ? lineNo : 0);
}

async function loadSource(chapterId, start, end) {
  destroyEpubViewer();
  state.pdfPageMode = false;
  const full = !end || end === 0;
  const label = chapterTitle(chapterId);
  sourceHeader.textContent = full
    ? `${label} · 原文`
    : `${label} · L${start}${end !== start ? `–L${end}` : ""}`;
  sourcePanel.dataset.viewChapter = chapterId;
  sourcePanel.classList.remove("native-mode");
  state.pdfPage = null;
  sourcePanel.innerHTML = '<p class="loading">加载原文…</p>';

  try {
    const data = await api(
      `/api/books/${encodeURIComponent(state.slug)}/source/${encodeURIComponent(chapterId)}?start=${start}&end=${full ? 0 : end}`
    );
    if (!data.lines.length) {
      sourcePanel.innerHTML = '<p class="source-hint">该章节暂无 OCR 原文。</p>';
      return;
    }
    sourcePanel.innerHTML = renderSourceLines(data.lines, full, data.garbage_lines || 0);
    sourcePanel.scrollTop = 0;
    if (!full) {
      sourcePanel.querySelector(".source-line.highlight")?.scrollIntoView({ block: "center", behavior: "smooth" });
    }
  } catch (e) {
    sourcePanel.innerHTML = `<p class="loading">${escapeHtml(e.message)}</p>`;
  }
}

function normalizeForSearch(text) {
  return String(text || "")
    .replace(/[\s\u00a0\u3000]+/g, "")
    .replace(/[「」『』""''（）()：:，,。．.!?！？；;—\-…]/g, "");
}

function buildAnchorNeedles(lines) {
  const needles = [];
  for (const l of lines) {
    const t = (l.text || "").trim();
    if (t.length < 10 || isPageMarker(t)) continue;
    const norm = normalizeForSearch(t);
    if (norm.length < 8) continue;
    needles.push({ norm, len: norm.length });
  }
  needles.sort((a, b) => b.len - a.len);
  return needles.slice(0, 5);
}

function clearEpubHighlights() {
  sourcePanel.querySelectorAll(".anchor-highlight").forEach((el) => {
    el.classList.remove("anchor-highlight");
  });
}

function findInEpub(reader, needles) {
  if (!reader || !needles.length) return null;
  const blocks = [...reader.querySelectorAll("p, blockquote, li, h1, h2, h3, h4, div.epub-section")];
  for (const { norm } of needles) {
    for (let n = Math.min(norm.length, 28); n >= 8; n -= 2) {
      const probe = norm.slice(0, n);
      for (const el of blocks) {
        if (el.closest(".anchor-highlight")) continue;
        if (el.querySelector("p, blockquote, li")) continue;
        const hay = normalizeForSearch(el.textContent);
        if (hay.includes(probe)) return el;
      }
    }
  }
  return null;
}

async function fetchExtractLines(chapterId, start, end) {
  const data = await api(
    `/api/books/${encodeURIComponent(state.slug)}/source/${encodeURIComponent(chapterId)}?start=${start}&end=${end}`
  );
  return data.lines || [];
}

async function jumpToAnchorInEpub(chapterId, start, end) {
  const label = chapterTitle(chapterId);
  let reader = sourcePanel.querySelector(".epub-html-reader");
  if (!reader || sourcePanel.dataset.viewChapter !== chapterId) {
    await loadEpubSource(chapterId);
    reader = sourcePanel.querySelector(".epub-html-reader");
    sourcePanel.dataset.viewChapter = chapterId;
  }
  if (!reader) {
    await loadSource(chapterId, start, end);
    return;
  }
  clearEpubHighlights();
  try {
    const lines = await fetchExtractLines(chapterId, start, end);
    const hit = findInEpub(reader, buildAnchorNeedles(lines));
    sourceHeader.textContent = `${label} · EPUB · 定位 L${start}${end !== start ? `–L${end}` : ""}`;
    if (hit) {
      hit.classList.add("anchor-highlight");
      hit.scrollIntoView({ block: "center", behavior: "smooth" });
      return;
    }
    sourceHeader.textContent = `${label} · EPUB · 未精确匹配 L${start}${end !== start ? `–L${end}` : ""}`;
  } catch (e) {
    sourceHeader.textContent = `${label} · EPUB`;
  }
}

async function jumpToAnchorInPdf(chapterId, start, end) {
  const label = chapterTitle(chapterId);
  sourceHeader.textContent = `${label} · PDF · L${start}${end !== start ? `–L${end}` : ""}`;
  await loadPdfSource(chapterId, start);
}

async function jumpToAnchor(chapterId, start, end) {
  if (!chapterId || !start) return;
  const kind = nativeViewerKind();
  if (kind === "epub") {
    await jumpToAnchorInEpub(chapterId, start, end);
    return;
  }
  if (kind === "pdf") {
    await jumpToAnchorInPdf(chapterId, start, end);
    return;
  }
  await loadSource(chapterId, start, end);
}

function isOverviewLayout() {
  return state.currentFile === "overview.md" && !state.currentChapter;
}

function syncChatPlaceholder() {
  if (!chatInput) return;
  if (isOverviewLayout()) {
    chatInput.placeholder = "基于全书概览提问…";
  } else if (state.currentChapter) {
    chatInput.placeholder = state.usePageIndex
      ? "本章原文 + 跨章检索…"
      : "基于当前章节提问…";
  } else {
    chatInput.placeholder = "提问…";
  }
  syncChatCrossButton();
}

function loadChatPageIndexPref() {
  if (!state.slug) return;
  const saved = JSON.parse(localStorage.getItem(CHAT_PAGEINDEX_KEY) || "{}");
  state.usePageIndex = !!saved[state.slug];
}

function persistChatPageIndexPref() {
  if (!state.slug) return;
  const saved = JSON.parse(localStorage.getItem(CHAT_PAGEINDEX_KEY) || "{}");
  saved[state.slug] = state.usePageIndex;
  localStorage.setItem(CHAT_PAGEINDEX_KEY, JSON.stringify(saved));
}

function syncChatCrossButton() {
  if (!btnChatCross) return;
  const show = !!state.currentChapter && !isOverviewLayout();
  btnChatCross.classList.toggle("hidden", !show);
  btnChatCross.classList.toggle("active", !!state.usePageIndex);
  const label = state.usePageIndex
    ? "跨章检索：已开启"
    : "跨章检索：关闭（仅本章原文）";
  btnChatCross.title = label;
  btnChatCross.setAttribute("aria-label", label);
  btnChatCross.setAttribute("aria-pressed", state.usePageIndex ? "true" : "false");
}

function syncNavLayout() {
  toggleNav?.classList.toggle("active", state.navOpen);
  workspace?.classList.toggle("nav-collapsed", !state.navOpen);
}

function exitSummaryFullscreen() {
  if (!state.summaryFullscreen) return;
  state.summaryFullscreen = false;
  syncReaderLayout();
  initSourceView();
}

function syncSummaryFullscreen() {
  const on = state.summaryFullscreen;
  layout?.classList.toggle("summary-fullscreen", on);
  if (btnSummaryFullscreen) {
    setBtnIcon(btnSummaryFullscreen, on ? "minimize" : "maximize");
    btnSummaryFullscreen.classList.toggle("active", on);
    btnSummaryFullscreen.title = on ? "退出专注模式" : "Summary + 对话专注模式";
    btnSummaryFullscreen.setAttribute("aria-label", btnSummaryFullscreen.title);
  }
}

function syncReaderLayout() {
  const overview = isOverviewLayout();
  workspace?.classList.toggle("overview-layout", overview);
  syncNavLayout();
  syncSideLayout();
  syncSummaryFullscreen();
  syncChatPlaceholder();
}

function initSourceView() {
  if (isOverviewLayout()) return;
  if (state.currentChapter) {
    const kind = nativeViewerKind();
    if (kind === "pdf" || kind === "epub") loadNativeSource(state.currentChapter);
    else loadSource(state.currentChapter, 1, 0);
  } else {
    destroyEpubViewer();
    sourceHeader.textContent = "原文";
    sourcePanel.classList.remove("native-mode");
    sourcePanel.innerHTML =
      '<p class="source-hint">请从左侧「正文章节」选择一章。<br>PDF / EPUB 直接阅读原文件，TXT 排版阅读；点击 Summary 锚点可在原文中定位段落。</p>';
  }
}

function syncSummaryHeader(file) {
  if (!summaryHeader) return;
  if (file === "overview.md") summaryHeader.textContent = "全书概览";
  else if (file === "qa.md") summaryHeader.textContent = "Q&A";
  else if (file === "synthesis.md") summaryHeader.textContent = "融会贯通";
  else if (file?.startsWith("chapters/")) summaryHeader.textContent = "深度 Summary";
  else summaryHeader.textContent = "Summary";
}

$("#btn-font-dec")?.addEventListener("click", () => {
  const cur = parseInt(getComputedStyle(document.documentElement).getPropertyValue("--reader-size"), 10) || 17;
  saveReaderPrefs({ fontSize: Math.max(14, cur - 1) });
});
$("#btn-font-inc")?.addEventListener("click", () => {
  const cur = parseInt(getComputedStyle(document.documentElement).getPropertyValue("--reader-size"), 10) || 17;
  saveReaderPrefs({ fontSize: Math.min(22, cur + 1) });
});
$("#btn-theme")?.addEventListener("click", () => {
  const saved = JSON.parse(localStorage.getItem(READER_KEY) || "{}");
  const next = saved.theme === "night" ? "paper" : "night";
  saveReaderPrefs({ theme: next });
});

function initToolbarIcons() {
  setBtnIcon(btnSettings, "settings");
  setBtnIcon(btnImport, "plus");
  setBtnIcon(btnBack, "arrowLeft");
  if (btnPreviewInline) setBtnIcon(btnPreviewInline, "overview");
  setBtnIcon(btnDeep, "sparkles");
  setBtnIcon(btnDeepPrompt, "edit");
  if (btnDeepPromptDeleteMode) setBtnIcon(btnDeepPromptDeleteMode, "trash");
  setBtnIcon(toggleSide, "sidebar");
  if (toggleNav) setBtnIcon(toggleNav, "toc");
  if (btnSummaryFullscreen) setBtnIcon(btnSummaryFullscreen, "maximize");
  setBtnIcon($("#btn-font-dec"), "fontDec");
  setBtnIcon($("#btn-font-inc"), "fontInc");
  setBtnIcon($("#chat-send"), "send");
  setBtnIcon(btnChatCross, "layers");
  applyReaderPrefs();
}

function saveLayout() {
  const navW = parseInt(getComputedStyle(document.documentElement).getPropertyValue("--nav-w"), 10);
  const sideW = parseInt(getComputedStyle(document.documentElement).getPropertyValue("--side-w"), 10);
  const summaryRatio = parseFloat(getComputedStyle(document.documentElement).getPropertyValue("--summary-ratio"));
  const overviewChatW = parseInt(
    getComputedStyle(document.documentElement).getPropertyValue("--overview-chat-w"),
    10
  );
  localStorage.setItem(
    LAYOUT_KEY,
    JSON.stringify({ navW, sideW, summaryRatio, navOpen: state.navOpen, overviewChatW: overviewChatW || 380 })
  );
}

function sideWidthLimits() {
  const navW = parseInt(getComputedStyle(document.documentElement).getPropertyValue("--nav-w"), 10) || 240;
  const mainMin = 180;
  const max = Math.max(320, window.innerWidth - navW - mainMin - 12);
  return { min: 220, max };
}

function overviewChatResizeLimits() {
  const panelW = sidePanel?.getBoundingClientRect().width || window.innerWidth;
  const wide = state.summaryFullscreen || isOverviewLayout();
  const minChat = wide ? 200 : 280;
  const minSummary = wide ? 200 : 320;
  const maxChat = Math.max(minChat + 60, panelW - minSummary);
  return { minChat, maxChat };
}

function initResizers() {
  setupResize($("#handle-nav"), (dx) => {
    const cur = parseInt(getComputedStyle(document.documentElement).getPropertyValue("--nav-w"), 10);
    document.documentElement.style.setProperty("--nav-w", `${Math.min(480, Math.max(140, cur + dx))}px`);
  });
  setupResize(handleSide, (dx) => {
    const { min, max } = sideWidthLimits();
    const cur = parseInt(getComputedStyle(document.documentElement).getPropertyValue("--side-w"), 10);
    document.documentElement.style.setProperty("--side-w", `${Math.min(max, Math.max(min, cur - dx))}px`);
  });
  setupResizeV(handleSummaryChat, (dy) => {
    const panel = sidePanel.getBoundingClientRect().height - 48;
    const cur = parseFloat(getComputedStyle(document.documentElement).getPropertyValue("--summary-ratio"));
    const delta = dy / panel;
    document.documentElement.style.setProperty("--summary-ratio", `${Math.min(0.92, Math.max(0.08, cur + delta))}`);
  });
  if (handleOverviewChat) {
    setupResize(handleOverviewChat, (dx) => {
      const { minChat, maxChat } = overviewChatResizeLimits();
      const cur = parseInt(getComputedStyle(document.documentElement).getPropertyValue("--overview-chat-w"), 10) || 380;
      document.documentElement.style.setProperty(
        "--overview-chat-w",
        `${Math.min(maxChat, Math.max(minChat, cur - dx))}px`
      );
    });
  }
}

function setupResize(handle, onMove) {
  let startX = 0;
  const onMouseMove = (e) => { onMove(e.clientX - startX); startX = e.clientX; };
  const onMouseUp = () => {
    document.body.classList.remove("resizing");
    handle.classList.remove("dragging");
    document.removeEventListener("mousemove", onMouseMove);
    document.removeEventListener("mouseup", onMouseUp);
    saveLayout();
  };
  handle.addEventListener("mousedown", (e) => {
    e.preventDefault();
    startX = e.clientX;
    document.body.classList.add("resizing");
    handle.classList.add("dragging");
    document.addEventListener("mousemove", onMouseMove);
    document.addEventListener("mouseup", onMouseUp);
  });
}

function setupResizeV(handle, onMove) {
  let startY = 0;
  const onMouseMove = (e) => { onMove(e.clientY - startY); startY = e.clientY; };
  const onMouseUp = () => {
    document.body.classList.remove("resizing-v");
    handle.classList.remove("dragging");
    document.removeEventListener("mousemove", onMouseMove);
    document.removeEventListener("mouseup", onMouseUp);
    saveLayout();
  };
  handle.addEventListener("mousedown", (e) => {
    e.preventDefault();
    startY = e.clientY;
    document.body.classList.add("resizing-v");
    handle.classList.add("dragging");
    document.addEventListener("mousemove", onMouseMove);
    document.addEventListener("mouseup", onMouseUp);
  });
}

function syncSideLayout() {
  const overview = isOverviewLayout();
  const focus = state.summaryFullscreen;
  toggleSide?.classList.toggle("active", state.sideOpen);

  if (overview || focus) {
    sidePanel?.classList.remove("hidden");
    chatSection?.classList.toggle("hidden", overview && !state.sideOpen && !focus);
    handleOverviewChat?.classList.toggle("hidden", overview && !state.sideOpen && !focus);
    handleSide?.classList.add("hidden");
  } else {
    sidePanel?.classList.toggle("hidden", !state.sideOpen);
    handleSide?.classList.toggle("hidden", !state.sideOpen);
    chatSection?.classList.remove("hidden");
    handleOverviewChat?.classList.add("hidden");
  }
}

toggleSide.addEventListener("click", () => {
  state.sideOpen = !state.sideOpen;
  syncReaderLayout();
});

toggleNav?.addEventListener("click", () => {
  state.navOpen = !state.navOpen;
  syncNavLayout();
  saveLayout();
});

btnSummaryFullscreen?.addEventListener("click", () => {
  if (state.summaryFullscreen) {
    exitSummaryFullscreen();
    return;
  }
  state.sideOpen = true;
  state.summaryFullscreen = true;
  syncReaderLayout();
});

document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && state.summaryFullscreen) {
    exitSummaryFullscreen();
  }
});

function loadChatsFromStorage() {
  try {
    state.chatHistory = JSON.parse(localStorage.getItem(CHAT_KEY) || "{}");
  } catch {
    state.chatHistory = {};
  }
}

function persistChats() {
  localStorage.setItem(CHAT_KEY, JSON.stringify(state.chatHistory));
}

function chatKey() {
  return `${state.slug}:${state.currentChapter || "overview"}`;
}

function getChatMessages() {
  const key = chatKey();
  if (!state.chatHistory[key]) state.chatHistory[key] = [];
  return state.chatHistory[key];
}

function chapterTitle(chId) {
  const ch = (state.meta?.chapters || []).find((c) => c.id === chId);
  return ch ? `${ch.index}. ${ch.title}` : chId;
}

function currentChapterTemplate() {
  const ch = (state.meta?.chapters || []).find((c) => c.id === state.currentChapter);
  const t = ch?.template || state.meta?.book_type || "M";
  return t === "N" ? "N" : "M";
}

function isCoarsePointer() {
  return window.matchMedia("(pointer: coarse)").matches || window.innerWidth <= 900;
}

function resetDialogPosition(dialog) {
  if (!dialog) return;
  dialog.style.left = "";
  dialog.style.top = "";
  dialog.style.margin = "";
  dialog.style.transform = "";
  dialog.style.width = "";
  dialog.style.height = "";
}

function pinDialogBox(dialog) {
  const rect = dialog.getBoundingClientRect();
  dialog.style.margin = "0";
  dialog.style.transform = "none";
  dialog.style.left = `${rect.left}px`;
  dialog.style.top = `${rect.top}px`;
  dialog.style.width = `${rect.width}px`;
  dialog.style.height = `${rect.height}px`;
}

function initDraggableDialog(dialog, handle) {
  if (!dialog || !handle || isCoarsePointer()) return;
  let drag = null;

  const onMove = (e) => {
    if (!drag) return;
    const pad = 8;
    let left = drag.startLeft + e.clientX - drag.startX;
    let top = drag.startTop + e.clientY - drag.startY;
    left = Math.max(pad, Math.min(left, window.innerWidth - dialog.offsetWidth - pad));
    top = Math.max(pad, Math.min(top, window.innerHeight - dialog.offsetHeight - pad));
    dialog.style.left = `${left}px`;
    dialog.style.top = `${top}px`;
  };

  const endDrag = () => {
    if (!drag) return;
    drag = null;
    document.body.classList.remove("dialog-dragging");
    window.removeEventListener("pointermove", onMove);
    window.removeEventListener("pointerup", endDrag);
    window.removeEventListener("pointercancel", endDrag);
  };

  handle.addEventListener("pointerdown", (e) => {
    if (e.button !== 0) return;
    pinDialogBox(dialog);
    const rect = dialog.getBoundingClientRect();
    drag = { startX: e.clientX, startY: e.clientY, startLeft: rect.left, startTop: rect.top };
    document.body.classList.add("dialog-dragging");
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", endDrag);
    window.addEventListener("pointercancel", endDrag);
    e.preventDefault();
  });

  dialog.addEventListener("close", () => resetDialogPosition(dialog));
}

function initResizableDialog(dialog, handle) {
  if (!dialog || !handle || isCoarsePointer()) return;
  const MIN_W = Math.min(420, window.innerWidth - 32);
  const MIN_H = 300;
  let resize = null;

  const onMove = (e) => {
    if (!resize) return;
    const pad = 8;
    let w = resize.startW + e.clientX - resize.startX;
    let h = resize.startH + e.clientY - resize.startY;
    w = Math.max(MIN_W, Math.min(w, window.innerWidth - resize.startLeft - pad));
    h = Math.max(MIN_H, Math.min(h, window.innerHeight - resize.startTop - pad));
    dialog.style.width = `${w}px`;
    dialog.style.height = `${h}px`;
  };

  const endResize = () => {
    if (!resize) return;
    resize = null;
    document.body.classList.remove("dialog-resizing");
    window.removeEventListener("pointermove", onMove);
    window.removeEventListener("pointerup", endResize);
    window.removeEventListener("pointercancel", endResize);
  };

  handle.addEventListener("pointerdown", (e) => {
    if (e.button !== 0) return;
    pinDialogBox(dialog);
    const rect = dialog.getBoundingClientRect();
    resize = {
      startX: e.clientX,
      startY: e.clientY,
      startW: rect.width,
      startH: rect.height,
      startLeft: rect.left,
      startTop: rect.top,
    };
    document.body.classList.add("dialog-resizing");
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", endResize);
    window.addEventListener("pointercancel", endResize);
    e.preventDefault();
    e.stopPropagation();
  });
}

function syncDeepPromptCustomActions() {
  btnDeepPromptSaveAsPreset?.classList.toggle("hidden", !deepPromptPlusMode);
}

function initPresetEmojiPicker() {
  if (!presetSaveEmojiGrid || presetSaveEmojiGrid.dataset.ready) return;
  presetSaveEmojiGrid.dataset.ready = "1";
  for (const emoji of PRESET_EMOJIS) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "emoji-picker-btn";
    btn.textContent = emoji;
    btn.title = emoji;
    btn.setAttribute("role", "option");
    btn.addEventListener("click", () => selectPresetEmoji(emoji));
    presetSaveEmojiGrid.appendChild(btn);
  }
}

function selectPresetEmoji(emoji) {
  _selectedPresetEmoji = emoji;
  if (presetSaveIconPreview) presetSaveIconPreview.textContent = emoji;
  presetSaveEmojiGrid?.querySelectorAll(".emoji-picker-btn").forEach((btn) => {
    btn.classList.toggle("active", btn.textContent === emoji);
    btn.setAttribute("aria-selected", btn.textContent === emoji ? "true" : "false");
  });
}

function openPresetSaveDialog(defaultName = "我的风格") {
  initPresetEmojiPicker();
  return new Promise((resolve) => {
    if (!presetSaveDialog) {
      resolve(null);
      return;
    }
    selectPresetEmoji("✨");
    if (presetSaveName) {
      presetSaveName.value = defaultName;
      presetSaveName.focus();
      presetSaveName.select();
    }
    const onConfirm = () => {
      cleanup();
      resolve({
        name: presetSaveName?.value?.trim() || "我的风格",
        icon: _selectedPresetEmoji,
      });
    };
    const onCancel = () => {
      cleanup();
      resolve(null);
    };
    const cleanup = () => {
      presetSaveDialog.close();
      $("#preset-save-confirm")?.removeEventListener("click", onConfirm);
      $("#preset-save-cancel")?.removeEventListener("click", onCancel);
      presetSaveDialog.removeEventListener("cancel", onCancel);
      presetSaveName?.removeEventListener("keydown", onKeydown);
    };
    const onKeydown = (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        onConfirm();
      }
    };
    $("#preset-save-confirm")?.addEventListener("click", onConfirm);
    $("#preset-save-cancel")?.addEventListener("click", onCancel);
    presetSaveDialog.addEventListener("cancel", onCancel);
    presetSaveName?.addEventListener("keydown", onKeydown);
    presetSaveDialog.showModal();
  });
}

function syncDeepPromptMeta() {
  if (!deepPromptMeta) return;
  const template = currentChapterTemplate();
  const label = template === "N" ? "N · 叙事型" : "M · 方法论型";
  if (deepPromptPlusMode) {
    deepPromptMeta.textContent =
      `${label} · 本书一次性自定义 · 仅本书生效 · 保存后点 ✨ 重新生成`;
    return;
  }
  const ap = state._deepPromptData?.active_preset;
  if (ap?.builtin) {
    deepPromptMeta.textContent =
      `${label} · ${ap.icon} ${ap.name}（内置）· 不可修改 · 点 + 创建本书自定义`;
    return;
  }
  if (ap) {
    deepPromptMeta.textContent =
      `${label} · ${ap.icon} ${ap.name} · 保存将更新此全局风格 · ✨ 重新生成后生效`;
    return;
  }
  deepPromptMeta.textContent = `${label} · 默认风格 · ✨ 重新生成后生效`;
}

function enterCustomPromptMode(blank = true) {
  deepPromptEditMode = "custom";
  deepPromptPlusMode = true;
  if (blank) deepPromptText.value = "";
  syncDeepPromptMeta();
  syncDeepPromptCustomActions();
  if (state._deepPromptData) renderDeepPromptPresets(state._deepPromptData);
}

function applyDeepPromptData(data) {
  state._deepPromptData = data;
  if (data.mode === "custom") {
    deepPromptEditMode = "custom";
    deepPromptPlusMode = true;
  } else {
    deepPromptEditMode = "preset";
    deepPromptPlusMode = false;
  }
  deepPromptText.value = data.prompt || "";
  state._deepPromptDefault = data.default_prompt || "";
  syncDeepPromptMeta();
  syncDeepPromptCustomActions();
  renderDeepPromptPresets(data);
  syncPresetDeleteModeBtn(data);
}

function renderDeepPromptPresets(data) {
  if (!deepPromptPresets) return;
  const isPlus = deepPromptPlusMode;
  deepPromptPresets.innerHTML = "";
  for (const p of data.presets || []) {
    const wrap = document.createElement("div");
    wrap.className = "prompt-preset-wrap";
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "prompt-preset-btn";
    btn.title = p.name;
    btn.dataset.presetId = p.id;
    if (!isPlus && data.mode !== "custom" && data.preset_id === p.id) {
      btn.classList.add("active");
    }
    btn.innerHTML = `<span class="prompt-preset-icon">${escapeHtml(p.icon)}</span>`;
    btn.addEventListener("click", () => {
      if (deepPromptDeleteMode) return;
      deepPromptPlusMode = false;
      deepPromptEditMode = "preset";
      syncDeepPromptCustomActions();
      bindDeepPromptPreset(p.id);
    });
    wrap.appendChild(btn);
    if (!p.builtin) {
      const del = document.createElement("button");
      del.type = "button";
      del.className = "prompt-preset-del";
      del.title = `删除「${p.name}」`;
      del.setAttribute("aria-label", `删除风格 ${p.name}`);
      del.textContent = "×";
      del.addEventListener("click", (e) => {
        e.stopPropagation();
        deleteDeepPromptPreset(p.id, p.name);
      });
      wrap.appendChild(del);
    }
    deepPromptPresets.appendChild(wrap);
  }
  const addBtn = document.createElement("button");
  addBtn.type = "button";
  addBtn.className = "prompt-preset-btn prompt-preset-add";
  addBtn.title = "本书一次性自定义（仅本书生效）";
  addBtn.textContent = "+";
  if (isPlus) addBtn.classList.add("active");
  addBtn.addEventListener("click", () => {
    if (deepPromptDeleteMode) return;
    enterCustomPromptMode(true);
  });
  deepPromptPresets.appendChild(addBtn);
}

async function deleteDeepPromptPreset(presetId, name) {
  if (!state.slug) return;
  if (!confirm(`确定删除风格「${name}」？\n删除后无法恢复；若本书正在使用该风格，将自动切回内置默认。`)) return;
  deepPromptError.classList.add("hidden");
  deepPromptError.textContent = "";
  try {
    await api(`/api/prompt-presets/${encodeURIComponent(presetId)}`, { method: "DELETE" });
    const template = currentChapterTemplate();
    const data = await api(
      `/api/books/${encodeURIComponent(state.slug)}/deep-prompt?template=${encodeURIComponent(template)}`
    );
    applyDeepPromptData(data);
  } catch (err) {
    deepPromptError.textContent = err.message;
    deepPromptError.classList.remove("hidden");
  }
}

async function bindDeepPromptPreset(presetId) {
  if (!state.slug || state._deepPromptBinding) return;
  deepPromptError.classList.add("hidden");
  deepPromptError.textContent = "";
  state._deepPromptBinding = true;
  try {
    const template = currentChapterTemplate();
    const data = await api(`/api/books/${encodeURIComponent(state.slug)}/deep-prompt`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ template, preset_id: presetId }),
    });
    applyDeepPromptData(data);
  } catch (err) {
    deepPromptError.textContent = err.message;
    deepPromptError.classList.remove("hidden");
  } finally {
    state._deepPromptBinding = false;
  }
}

async function saveDeepPromptAsNewPreset() {
  if (!state.slug) return;
  const text = deepPromptText.value.trim();
  if (!text) {
    deepPromptError.textContent = "prompt 不能为空";
    deepPromptError.classList.remove("hidden");
    return;
  }
  const result = await openPresetSaveDialog("我的风格");
  if (!result) return;
  deepPromptError.classList.add("hidden");
  deepPromptError.textContent = "";
  const template = currentChapterTemplate();
  const btn = $("#deep-prompt-save-as-preset");
  if (btn) btn.disabled = true;
  try {
    const data = await api(`/api/books/${encodeURIComponent(state.slug)}/deep-prompt`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        template,
        prompt: text,
        save_as_preset: { name: result.name, icon: result.icon },
      }),
    });
    applyDeepPromptData(data);
  } catch (err) {
    deepPromptError.textContent = err.message;
    deepPromptError.classList.remove("hidden");
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function saveDeepPrompt() {
  if (!state.slug) return;
  deepPromptError.classList.add("hidden");
  deepPromptError.textContent = "";
  const template = currentChapterTemplate();
  const saveBtn = $("#deep-prompt-save");
  if (saveBtn) saveBtn.disabled = true;
  try {
    const text = deepPromptText.value.trim();
    if (!text) {
      deepPromptError.textContent = "prompt 不能为空";
      deepPromptError.classList.remove("hidden");
      return;
    }

    if (deepPromptEditMode === "custom") {
      const data = await api(`/api/books/${encodeURIComponent(state.slug)}/deep-prompt`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ template, prompt: text }),
      });
      applyDeepPromptData(data);
      deepPromptDialog.close();
      return;
    }

    const ap = state._deepPromptData?.active_preset;
    if (!ap || ap.builtin) {
      deepPromptError.textContent = "内置风格不可修改。点 + 可创建本书一次性自定义 prompt。";
      deepPromptError.classList.remove("hidden");
      return;
    }

    await api(`/api/prompt-presets/${encodeURIComponent(ap.id)}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ prompt: text }),
    });
    const data = await api(
      `/api/books/${encodeURIComponent(state.slug)}/deep-prompt?template=${encodeURIComponent(template)}`
    );
    applyDeepPromptData(data);
    deepPromptDialog.close();
  } catch (err) {
    deepPromptError.textContent = err.message;
    deepPromptError.classList.remove("hidden");
  } finally {
    if (saveBtn) saveBtn.disabled = false;
  }
}

async function openDeepPromptDialog() {
  if (!state.slug || !state.currentChapter) return;
  setDeepPromptDeleteMode(false);
  deepPromptError.classList.add("hidden");
  deepPromptError.textContent = "";
  deepPromptMeta.textContent = "加载中…";
  deepPromptText.value = "";
  if (deepPromptPresets) deepPromptPresets.innerHTML = "";
  resetDialogPosition(deepPromptDialog);
  deepPromptDialog.showModal();
  // iOS Safari：等 dialog 布局完成后再拉数据，避免 flex 高度为 0
  await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
  try {
    const template = currentChapterTemplate();
    const data = await api(
      `/api/books/${encodeURIComponent(state.slug)}/deep-prompt?template=${encodeURIComponent(template)}`
    );
    applyDeepPromptData(data);
  } catch (err) {
    deepPromptMeta.textContent = "加载失败";
    deepPromptError.textContent = err.message;
    deepPromptError.classList.remove("hidden");
  }
}

function syncGenerateButtons() {
  if (btnDeepPrompt) {
    const ch = state.currentChapter;
    const show = ch && state.currentFile?.startsWith("chapters/");
    btnDeepPrompt.classList.toggle("hidden", !show);
    if (show) {
      btnDeepPrompt.title = "编辑 Summary Prompt";
      btnDeepPrompt.disabled = state.deepGenerating || state.previewGenerating;
    }
  }
  if (btnDeep) {
    const ch = state.currentChapter;
    const showDeep = ch && state.currentFile?.startsWith("chapters/");
    btnDeep.classList.toggle("hidden", !showDeep);
    if (showDeep) {
      btnDeep.classList.toggle("regen", state.summaryExists && !state.deepGenerating);
      btnDeep.classList.toggle("loading-spin", state.deepGenerating);
      setBtnIcon(btnDeep, state.deepGenerating ? "refresh" : "sparkles");
      btnDeep.title = state.deepGenerating
        ? "生成中…"
        : state.summaryExists
          ? "重新生成深度 Summary"
          : "生成深度 Summary";
      btnDeep.disabled = state.deepGenerating || state.previewGenerating;
    }
  }
  if (btnPreviewInline) {
    const showPreview = isOverviewLayout();
    btnPreviewInline.classList.toggle("hidden", !showPreview);
    if (showPreview) {
      btnPreviewInline.classList.toggle("regen", state.overviewExists && !state.previewGenerating);
      btnPreviewInline.classList.toggle("loading-spin", state.previewGenerating);
      setBtnIcon(btnPreviewInline, state.previewGenerating ? "refresh" : "overview");
      btnPreviewInline.title = state.previewGenerating
        ? "生成中…"
        : state.overviewExists
          ? "重新生成全书概览"
          : "生成全书概览";
      btnPreviewInline.disabled = state.previewGenerating || state.deepGenerating;
    }
  }
}

async function runPreview() {
  if (state.previewGenerating || state.currentFile !== "overview.md") return;
  const n = state.meta?.chapters?.length || 0;
  state.previewGenerating = true;
  syncGenerateButtons();
  setSummaryMessage(
    `<p class="loading">正在生成全书概览…<br>共 ${n} 章，LLM 处理中（章节多时可能需数分钟），请勿关闭页面。</p>`
  );

  try {
    await api(`/api/books/${encodeURIComponent(state.slug)}/preview`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "{}",
    });
    state.meta = await api(`/api/books/${encodeURIComponent(state.slug)}/meta`);
    await showInsight("overview.md");
  } catch (err) {
    setSummaryMessage(
      `<p class="loading">生成失败：${escapeHtml(err.message)}</p>` +
      `<div class="content-toolbar">${inlineIconBtn("preview-retry", "refresh", "重试")}</div>`
    );
    $("#preview-retry")?.addEventListener("click", runPreview);
  } finally {
    state.previewGenerating = false;
    syncGenerateButtons();
  }
}

btnPreviewInline?.addEventListener("click", runPreview);

function syncDeepButton() {
  syncGenerateButtons();
}

async function runDeepSummary(force = false) {
  const ch = state.currentChapter;
  if (!ch) return;

  const existing = getDeepJob(ch);
  if (existing?.status === "streaming" || existing?.status === "finalizing") {
    if (!force) {
      attachDeepStreamView(ch);
      syncDeepGeneratingState();
      return;
    }
    existing.abort?.abort();
    deepJobs.delete(ch);
  }

  const regen = force || state.summaryExists;
  consumeDeepSummaryStream(ch, regen);
  syncDeepGeneratingState();
}

btnDeep?.addEventListener("click", () => runDeepSummary(state.summaryExists));

btnDeepPrompt?.addEventListener("click", () => openDeepPromptDialog());

btnDeepPromptDeleteMode?.addEventListener("pointerdown", (e) => e.stopPropagation());
btnDeepPromptDeleteMode?.addEventListener("click", (e) => {
  e.stopPropagation();
  setDeepPromptDeleteMode(!deepPromptDeleteMode);
});

deepPromptDialog?.addEventListener("close", () => setDeepPromptDeleteMode(false));

deepPromptForm?.addEventListener("submit", (e) => e.preventDefault());

$("#deep-prompt-save")?.addEventListener("click", () => saveDeepPrompt());

$("#deep-prompt-save-as-preset")?.addEventListener("click", () => saveDeepPromptAsNewPreset());

$("#deep-prompt-cancel")?.addEventListener("click", () => deepPromptDialog.close());

initDraggableDialog(deepPromptDialog, $("#deep-prompt-drag-handle"));
initResizableDialog(deepPromptDialog, $("#deep-prompt-resize"));

function renderRetrievalPanel(retrieval) {
  if (!retrieval) return null;
  const nodes = retrieval.nodes || [];
  if (!nodes.length) return null;
  const label = `检索 · ${nodes.length} 个节点（${nodes.join("、")}）`;
  const details = document.createElement("details");
  details.className = "chat-retrieval";
  const summary = document.createElement("summary");
  summary.textContent = label;
  details.appendChild(summary);
  return details;
}

function renderChat() {
  const msgs = getChatMessages();
  chatMessages.innerHTML = "";
  if (!msgs.length) {
    const ctx = state.currentChapter
      ? `当前章节：${chapterTitle(state.currentChapter)}`
      : "当前：全书概览";
    const el = document.createElement("div");
    el.className = "chat-row system";
    el.innerHTML = `<div class="chat-bubble system">基于《${escapeHtml(state.meta?.title || "")}》${escapeHtml(ctx)} 提问。对话自动写入概览 · Q&A。</div>`;
    chatMessages.appendChild(el);
    return;
  }

  msgs.forEach((m, idx) => {
    const row = document.createElement("div");
    row.className = `chat-row ${m.role}`;
    row.dataset.idx = String(idx);

    const bubble = document.createElement("div");
    bubble.className = `chat-bubble ${m.role}`;

    if (m.role === "assistant" && m.retrieval) {
      const panel = renderRetrievalPanel(m.retrieval);
      if (panel) bubble.appendChild(panel);
    }

    const body = document.createElement("div");
    body.className = m.role === "assistant" ? "chat-content md-body" : "chat-content";
    if (m.role === "assistant") {
      body.innerHTML = renderMd(m.content);
      linkifyAnchors(body, state.currentChapter);
    } else {
      body.textContent = m.content;
    }
    bubble.appendChild(body);

    row.appendChild(bubble);

    if (m.role !== "system") {
      const actions = document.createElement("div");
      actions.className = "chat-actions";
      if (m.role === "user") {
        actions.innerHTML = `<button type="button" data-action="edit">编辑</button><button type="button" data-action="delete">删除</button>`;
      } else {
        actions.innerHTML = `<button type="button" data-action="retry">重试</button><button type="button" data-action="delete">删除</button>`;
      }
      actions.querySelectorAll("button").forEach((btn) => {
        btn.addEventListener("click", () => handleChatAction(btn.dataset.action, idx));
      });
      row.appendChild(actions);
    }

    chatMessages.appendChild(row);
  });
  chatMessages.scrollTop = chatMessages.scrollHeight;
  renderMermaidIn(chatMessages);
}

function handleChatAction(action, idx) {
  const msgs = getChatMessages();
  if (action === "delete") {
    msgs.splice(idx, 1);
    persistChats();
    renderChat();
    return;
  }
  if (action === "edit") {
    startEditMessage(idx);
    return;
  }
  if (action === "retry") {
    let userIdx = idx - 1;
    while (userIdx >= 0 && msgs[userIdx].role !== "user") userIdx--;
    if (userIdx < 0) return;
    msgs.splice(idx);
    persistChats();
    renderChat();
    sendToApi(userIdx);
  }
}

function startEditMessage(idx) {
  const msgs = getChatMessages();
  const m = msgs[idx];
  if (!m || m.role !== "user") return;
  const row = chatMessages.querySelector(`[data-idx="${idx}"]`);
  if (!row) return;

  row.innerHTML = "";
  const wrap = document.createElement("div");
  wrap.className = "chat-bubble user editing";
  const ta = document.createElement("textarea");
  ta.className = "chat-edit-area";
  ta.value = m.content;
  const acts = document.createElement("div");
  acts.className = "chat-edit-actions";
  acts.innerHTML = `<button type="button" class="save">保存并发送</button><button type="button" class="cancel">取消</button>`;
  acts.querySelector(".save").addEventListener("click", () => {
    const text = ta.value.trim();
    if (!text) return;
    m.content = text;
    msgs.splice(idx + 1);
    persistChats();
    renderChat();
    sendToApi(idx);
  });
  acts.querySelector(".cancel").addEventListener("click", renderChat);
  wrap.appendChild(ta);
  wrap.appendChild(acts);
  row.appendChild(wrap);
  ta.focus();
}

async function sendToApi(upToIdx) {
  const msgs = getChatMessages();
  if (state.chatSending) return;
  state.chatSending = true;
  chatSend.disabled = true;

  const pending = document.createElement("div");
  pending.className = "chat-row assistant";
  pending.id = "chat-pending";
  pending.innerHTML = '<div class="chat-bubble assistant"><div class="chat-content">检索中…</div></div>';
  chatMessages.appendChild(pending);
  chatMessages.scrollTop = chatMessages.scrollHeight;

  try {
    const payload = msgs.slice(0, upToIdx + 1).map(({ role, content: c }) => ({ role, content: c }));
    const data = await api("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        slug: state.slug,
        chapter_id: state.currentChapter,
        current_file: state.currentFile,
        use_page_index: !!(state.usePageIndex && state.currentChapter),
        messages: payload,
      }),
    });
    pending.remove();
    msgs.push({
      id: uid(),
      role: "assistant",
      content: data.reply,
      nodes: data.nodes || [],
      retrieval: data.context
        ? { nodes: data.nodes || [], context: data.context }
        : null,
    });
    persistChats();
    renderChat();
    if (state.currentFile === "qa.md") await showInsight("qa.md");
  } catch (err) {
    pending.remove();
    msgs.push({ id: uid(), role: "assistant", content: `出错了：${err.message}` });
    persistChats();
    renderChat();
  } finally {
    state.chatSending = false;
    chatSend.disabled = false;
    chatInput.focus();
  }
}

btnChatCross?.addEventListener("click", () => {
  state.usePageIndex = !state.usePageIndex;
  persistChatPageIndexPref();
  syncChatCrossButton();
  syncChatPlaceholder();
});

chatForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const text = chatInput.value.trim();
  if (!text || state.chatSending) return;
  const msgs = getChatMessages();
  msgs.push({ id: uid(), role: "user", content: text });
  chatInput.value = "";
  persistChats();
  renderChat();
  await sendToApi(msgs.length - 1);
});

let chatImeComposing = false;

chatInput.addEventListener("compositionstart", () => {
  chatImeComposing = true;
});
chatInput.addEventListener("compositionend", () => {
  chatImeComposing = false;
});

chatInput.addEventListener("keydown", (e) => {
  if (e.key !== "Enter" || e.shiftKey) return;
  // IME 选字确认时的 Enter 不应触发发送
  if (e.isComposing || chatImeComposing || e.keyCode === 229) return;
  e.preventDefault();
  chatForm.requestSubmit();
});

async function loadShelf() {
  try {
    const books = await api("/api/books");
    if (!books.length) {
      shelf.className = "shelf shelf--flat";
      shelf.innerHTML = `
        <div class="shelf-empty">
          <p>书架是空的</p>
          <button type="button" class="btn-icon btn-icon-primary" id="shelf-empty-import" title="导入第一本书" aria-label="导入第一本书"></button>
        </div>`;
      const emptyImport = $("#shelf-empty-import");
      setBtnIcon(emptyImport, "plus");
      emptyImport?.addEventListener("click", openImportDialog);
      return;
    }
    const anyTagged = books.some((b) => (b.tag || "").trim());
    shelf.className = anyTagged ? "shelf" : "shelf shelf--flat";
    shelf.innerHTML = anyTagged ? renderShelfCollections(books) : books.map((b) => renderBookCard(b)).join("");
    shelf.querySelectorAll(".book-card[data-slug]").forEach((card) => {
      card.addEventListener("click", (e) => {
        if (e.target.closest("button")) return;
        openReader(card.dataset.slug);
      });
    });
    shelf.querySelectorAll("[data-action=split]").forEach((btn) => {
      btn.addEventListener("click", async (e) => {
        e.stopPropagation();
        const slug = btn.closest(".book-card").dataset.slug;
        btn.disabled = true;
        btn.classList.add("loading-spin");
        btn.title = "分章中…";
        try {
          await api(`/api/books/${encodeURIComponent(slug)}/split`, { method: "POST" });
          await loadShelf();
        } catch (err) {
          btn.classList.remove("loading-spin");
          btn.title = "自动分章";
          btn.disabled = false;
          alert(err.message);
        }
      });
    });
    shelf.querySelectorAll("[data-action=delete]").forEach((btn) => {
      btn.addEventListener("click", async (e) => {
        e.stopPropagation();
        const card = btn.closest(".book-card");
        const slug = card.dataset.slug;
        const title = card.querySelector(".book-card-title")?.textContent || slug;
        if (!confirm(`确定删除《${title}》？\n\n将永久删除 NOTE 目录及所有 Summary、Q&A，不可恢复。`)) return;
        btn.disabled = true;
        try {
          await api(`/api/books/${encodeURIComponent(slug)}`, { method: "DELETE" });
          if (state.slug === slug) showLibrary();
          pruneChatForSlug(slug);
          await loadShelf();
        } catch (err) {
          btn.disabled = false;
          alert(err.message);
        }
      });
    });
  } catch (e) {
    shelf.innerHTML = `<p class="loading">加载失败：${escapeHtml(e.message)}</p>`;
  }
}

function renderShelfCollections(books) {
  const groups = new Map();
  for (const b of books) {
    const key = (b.tag || "").trim() || "未分类";
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(b);
  }
  const keys = [...groups.keys()].sort((a, b) => {
    if (a === "未分类") return 1;
    if (b === "未分类") return -1;
    return a.localeCompare(b, "zh");
  });
  return keys
    .map(
      (key) => `
    <section class="shelf-collection">
      <h3 class="shelf-collection-title">${escapeHtml(key)}</h3>
      <div class="shelf-collection-grid">
        ${groups.get(key).map((b) => renderBookCard(b)).join("")}
      </div>
    </section>`
    )
    .join("");
}

function renderBookCard(b) {
  const s = b.stats || {};
  const badges = [];
  if (s.split_done) badges.push(`<span class="badge done">${s.chapters_total} 章</span>`);
  else badges.push('<span class="badge warn">未分章</span>');
  if (s.preview_done) badges.push('<span class="badge done">概览</span>');
  if (s.deep_files > 0) {
    const label = s.deep_done ? "Summary ✓" : `Summary ${s.deep_files}/${s.chapters_total || "?"}`;
    badges.push(`<span class="badge ${s.deep_done ? "done" : ""}">${label}</span>`);
  }
  if (s.has_qa) badges.push('<span class="badge done">Q&A</span>');
  if (s.has_synthesis) badges.push('<span class="badge done">Insight</span>');

  const splitBtn = !s.split_done
    ? `<button type="button" class="btn-icon btn-icon-sm" data-action="split" title="自动分章" aria-label="自动分章">${iconHtml("split")}</button>`
    : "";
  const deleteBtn = b.deletable
    ? `<button type="button" class="btn-icon btn-icon-sm btn-icon-danger" data-action="delete" title="删除" aria-label="删除">${iconHtml("trash")}</button>`
    : "";

  const metaLine = (b.tag || "").trim()
    ? `<span class="book-card-tag">${escapeHtml(b.tag)}</span>`
    : `<span class="book-card-id">ID · ${escapeHtml(b.id || b.slug)}</span>`;

  return `
    <article class="book-card" data-slug="${escapeHtml(b.slug)}">
      <div class="book-card-header">
        <div class="book-card-title">${escapeHtml(b.title)}</div>
        <div class="book-card-tools">${deleteBtn}</div>
      </div>
      <div class="book-card-meta">${metaLine}</div>
      <div class="book-card-badges">${badges.join("")}</div>
      ${splitBtn ? `<div class="book-card-actions">${splitBtn}</div>` : ""}
    </article>`;
}

function pruneChatForSlug(slug) {
  const prefix = `${slug}:`;
  Object.keys(state.chatHistory).forEach((k) => {
    if (k.startsWith(prefix)) delete state.chatHistory[k];
  });
  persistChats();
}

function showLibrary() {
  libraryView.classList.remove("hidden");
  readerView.classList.add("hidden");
  if (location.hash.startsWith("#/read/")) {
    history.replaceState(null, "", "#/");
  }
}

async function openReader(slug) {
  libraryView.classList.add("hidden");
  readerView.classList.remove("hidden");
  location.hash = `#/read/${slug}`;
  await loadBook(slug);
  readerTitle.textContent = state.meta?.title || slug;
}

function parseHash() {
  const m = location.hash.match(/^#\/read\/([^/?#]+)/);
  if (m) openReader(m[1]);
  else showLibrary();
}

function openImportDialog() {
  importError.classList.add("hidden");
  importError.textContent = "";
  importDetect.classList.add("hidden");
  importDetect.textContent = "";
  importForm.reset();
  importSplit.checked = true;
  importDialog.showModal();
}

async function runDetectPreview(file) {
  if (!file || !importSplit.checked) {
    importDetect.classList.add("hidden");
    return;
  }
  importDetect.classList.remove("hidden", "warn", "err");
  importDetect.classList.add("loading");
  importDetect.textContent = "正在标准化并分析章节格式…";
  try {
    let d;
    const ext = fileExt(file.name);
    if (TEXT_IMPORT_EXTS.has(ext)) {
      const source_text = await file.text();
      d = await api("/api/split/detect", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ source_text, use_llm: true }),
      });
    } else {
      const fd = new FormData();
      fd.append("file", file);
      fd.append("use_llm", "true");
      const r = await fetch("/api/split/detect", { method: "POST", body: fd });
      const text = await r.text();
      let parsed;
      try { parsed = JSON.parse(text); } catch { throw new Error(text || `HTTP ${r.status}`); }
      if (!r.ok) throw new Error(parsed.error || text);
      d = parsed;
    }
    const p = d.profile;
    const ingest = d.ingest ? ` · 已转为 ${d.ingest.source_format}` : "";
    const preview = (d.preview || []).slice(0, 3).map((c) => `第${c.index}${p.unit}·L${c.line}`).join("，");
    importDetect.classList.remove("loading");
    importDetect.innerHTML =
      `检测到 <strong>${d.chapters_found}</strong> ${p.unit} · ${p.label.replace("{n}", "X")}${ingest}<br>` +
      `正文约 L${p.body_start_line} · 置信 ${p.confidence}${preview ? `<br>示例：${escapeHtml(preview)}…` : ""}`;
  } catch (err) {
    importDetect.classList.remove("loading");
    importDetect.classList.add("warn");
    importDetect.textContent = `暂未识别章节格式：${err.message}（仍可导入，稍后再分章）`;
  }
}

importFile?.addEventListener("change", () => {
  clearTimeout(detectTimer);
  const file = importFile.files?.[0];
  if (!file) return;
  detectTimer = setTimeout(() => runDetectPreview(file), 400);
});

importSplit?.addEventListener("change", () => {
  const file = importFile.files?.[0];
  if (file) runDetectPreview(file);
  else importDetect.classList.add("hidden");
});

btnImport?.addEventListener("click", openImportDialog);
btnSettings?.addEventListener("click", openLlmSettingsDialog);
$("#llm-banner-settings")?.addEventListener("click", openLlmSettingsDialog);
llmStartupLater?.addEventListener("click", () => llmStartupDialog?.close());
llmStartupSetup?.addEventListener("click", openLlmSettingsFromStartup);
llmSettingsCancel?.addEventListener("click", () => llmSettingsDialog?.close());
llmSettingsClearKey?.addEventListener("click", clearLlmKey);
llmSettingsForm?.addEventListener("submit", saveLlmSettings);
btnCheckUpdate?.addEventListener("click", checkForUpdate);
btnApplyUpdate?.addEventListener("click", applyPendingUpdate);
importCancel?.addEventListener("click", () => importDialog.close());

importForm?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const title = importTitle.value.trim();
  const file = importFile.files?.[0];
  if (!title || !file) return;

  importError.classList.add("hidden");
  const submitBtn = $("#import-submit");
  submitBtn.disabled = true;
  submitBtn.textContent = "导入中…";

  try {
    const fd = new FormData();
    fd.append("title", title);
    fd.append("file", file);
    fd.append("auto_split", importSplit.checked ? "true" : "false");
    const tag = importTag.value.trim();
    if (tag) fd.append("tag", tag);
    const data = await api("/api/books", { method: "POST", body: fd });
    importDialog.close();
    await loadShelf();
    if (data.split_error) {
      alert(`书已导入，但自动分章失败：\n${data.split_error}\n\n可在书架卡片上点「自动分章」重试。`);
    } else if (data.split_chapters) {
      openReader(data.slug);
    } else {
      openReader(data.slug);
    }
  } catch (err) {
    importError.textContent = err.message;
    importError.classList.remove("hidden");
  } finally {
    submitBtn.disabled = false;
    submitBtn.textContent = "导入";
  }
});

btnBack?.addEventListener("click", () => {
  showLibrary();
  loadShelf();
});

async function loadBook(slug) {
  destroyEpubViewer();
  destroyPdfViewer();
  state.slug = slug;
  loadChatPageIndexPref();
  syncChatCrossButton();
  setSummaryMessage('<p class="loading">加载中…</p>');
  sourcePanel.innerHTML = '<p class="loading">加载中…</p>';
  try {
    state.meta = await api(`/api/books/${encodeURIComponent(slug)}/meta`);
    readerTitle.textContent = state.meta?.title || slug;
    buildNav();
    prefetchPdf();
    await showInsight("overview.md");
  } catch (e) {
    setSummaryMessage(`<p class="loading">无法打开此书：${escapeHtml(e.message)}</p>`);
    sourcePanel.innerHTML = "";
    nav.innerHTML = "";
  }
  renderChat();
}

function buildNav() {
  const chapters = state.meta.chapters || [];
  nav.innerHTML = `
    <div class="nav-group">
      <div class="nav-label">全文预览</div>
      <a href="#" data-file="overview.md">全书概览</a>
    </div>
    <div class="nav-group">
      <div class="nav-label">正文章节 · ${chapters.length} 章</div>
      ${chapters.map((c) =>
        `<a href="#" data-file="chapters/${c.id}.md" data-ch="${c.id}">
          ${String(c.index || c.id.replace("ch", ""))}. ${c.title || ""}
        </a>`
      ).join("")}
    </div>
    <div class="nav-group">
      <div class="nav-label">交互与讨论</div>
      <a href="#" data-file="qa.md">Q&A（阅读对话）</a>
      <a href="#" data-file="synthesis.md">融会贯通</a>
    </div>`;
  nav.querySelectorAll("a").forEach((a) => {
    a.addEventListener("click", (e) => {
      e.preventDefault();
      showInsight(a.dataset.file, a.dataset.ch);
    });
  });
}

function setActiveNav(file) {
  nav.querySelectorAll("a").forEach((a) => {
    a.classList.toggle("active", a.dataset.file === file);
  });
}

async function reloadChapterSummaryFromDisk(chapterId) {
  return tryLoadChapterSummary(chapterId, chapterSummaryFile(chapterId));
}

async function tryLoadChapterSummary(chapterId, file) {
  const { content: md } = await api(
    `/api/books/${encodeURIComponent(state.slug)}/insight/${encodeURIComponent(file)}`
  );
  const body = md.replace(/^---[\s\S]*?---\n/, "");
  setSummaryHtml(renderMd(body));
  linkifyAnchors(summaryPanel, chapterId);
  if (chapterId) {
    state.summaryExists = true;
    if (!isChapterDeepGenerating(chapterId)) {
      deepJobs.delete(chapterId);
    }
    syncDeepGeneratingState();
    restorePersistedSummaryStats(state.slug, chapterId);
  }
  return true;
}

async function showInsight(file, chapterId = null, opts = {}) {
  const { skipAutoGenerate = false } = opts;
  const focus = state.summaryFullscreen;
  state.currentChapter = chapterId;
  state.currentFile = file;
  state.summaryExists = false;
  state.overviewExists = false;
  setActiveNav(file);
  syncSummaryHeader(file);
  syncReaderLayout();
  syncDeepGeneratingState();

  if (chapterId) {
    renderChat();
    if (!focus) initSourceView();
  }

  if (chapterId && isChapterDeepGenerating(chapterId)) {
    attachDeepStreamView(chapterId);
    syncDeepGeneratingState();
    return;
  }

  setSummaryMessage('<p class="loading">加载中…</p>');
  try {
    await tryLoadChapterSummary(chapterId, file);
    if (file === "overview.md") state.overviewExists = true;
    if (focus) summaryPanel.scrollTop = 0;
  } catch (e) {
    if (chapterId && !skipAutoGenerate) {
      if (isChapterDeepGenerating(chapterId)) {
        attachDeepStreamView(chapterId);
        syncDeepGeneratingState();
      } else if (chapterHasApprovedSummary(chapterId)) {
        setSummaryMessage(
          `<div class="content-toolbar">${inlineIconBtn("deep-inline", "sparkles", "重新生成 Summary")}</div>` +
          `<p class="loading">Summary 加载失败。<br>${escapeHtml(e.message)}</p>`
        );
        $("#deep-inline")?.addEventListener("click", () => runDeepSummary(true));
      } else {
        void runDeepSummary(false);
      }
      return;
    }
    if (chapterId && getDeepJob(chapterId)?.status === "error") {
      attachDeepStreamView(chapterId);
      syncDeepGeneratingState();
      return;
    }
    if (chapterId) {
      setSummaryMessage(
        `<div class="content-toolbar">${inlineIconBtn("deep-inline", "sparkles", "重新生成 Summary")}</div>` +
        `<p class="loading">本章 Summary 加载失败。<br>${escapeHtml(e.message)}</p>`
      );
      $("#deep-inline")?.addEventListener("click", () => runDeepSummary(true));
    } else if (file === "qa.md") {
      setSummaryMessage('<p class="loading">尚无 Q&A。<br>阅读时在下方 chatbot 提问，对话会自动追加到此处。</p>');
    } else if (file === "synthesis.md") {
      setSummaryMessage('<p class="loading">Insight 尚未生成。<br>请先阅读并用 chatbot 积累 Q&A，再运行 synthesis。</p>');
    } else if (file === "overview.md") {
      setSummaryMessage(
        '<p class="loading">全书概览尚未生成。<br>点击标题栏右侧按钮调用 LLM 生成。</p>'
      );
    } else {
      setSummaryMessage(`<p class="loading">无法加载：${file}<br>${escapeHtml(e.message)}</p>`);
    }
  }
  if (!chapterId) {
    if (!isOverviewLayout() && !focus) initSourceView();
    renderChat();
  }
  syncDeepGeneratingState();
  syncReaderLayout();
}

function normalizeChapterId(raw) {
  const m = String(raw || "").match(/ch(\d+)/i);
  if (!m) return null;
  return `ch${String(parseInt(m[1], 10)).padStart(2, "0")}`;
}

function chapterFromAnchorContext(fullText, matchIndex, fallback) {
  const window = fullText.slice(Math.max(0, matchIndex - 72), matchIndex);
  const nodeRef = window.match(/\b(ch\d+)(?:-c\d+)?\s*[,，]?\s*$/i);
  if (nodeRef) return normalizeChapterId(nodeRef[1]);
  const refs = window.match(/\bch\d+\b/gi);
  if (refs?.length) return normalizeChapterId(refs[refs.length - 1]);
  return normalizeChapterId(fallback) || normalizeChapterId(state.currentChapter);
}

function parseLineRange(text) {
  const nums = text.match(/L(\d+)/gi);
  if (!nums?.length) return null;
  const start = parseInt(nums[0].slice(1), 10);
  const end = nums.length > 1 ? parseInt(nums[nums.length - 1].slice(1), 10) : start;
  return { start, end: Math.max(start, end) };
}

function jumpToAnchorFromClick(el) {
  const ch = el.dataset.chapter;
  const start = parseInt(el.dataset.start, 10);
  const end = parseInt(el.dataset.end, 10);
  jumpToAnchor(ch, start, end);
}

function handleAnchorActivate(e) {
  const el = e.target.closest(".anchor-link[data-start]");
  if (!el) return;
  e.preventDefault();
  e.stopPropagation();
  jumpToAnchorFromClick(el);
}

function linkifyAnchors(root, defaultChapter) {
  const citeRe =
    /\(\s*(ch\d+(?:-c\d+)?)\s*[,，]\s*(L\d+(?:\s*[-–—~至]\s*L?\d+)?)\s*\)|（\s*(ch\d+(?:-c\d+)?)\s*[,，]\s*(L\d+(?:\s*[-–—~至]\s*L?\d+)?)\s*）|锚点[：:]?\s*(L\d+(?:\s*[-–—~至]\s*L?\d+)?)|(L\d+(?:\s*[-–—~至]\s*L?\d+)?)/gi;
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  const nodes = [];
  while (walker.nextNode()) nodes.push(walker.currentNode);
  nodes.forEach((node) => {
    const text = node.textContent;
    if (!/L\d+|第\d+页/.test(text)) return;
    const frag = document.createDocumentFragment();
    let last = 0;
    let linked = false;
    citeRe.lastIndex = 0;
    let m;
    while ((m = citeRe.exec(text))) {
      let ch;
      let linePart;
      let label;
      if (m[1] && m[2]) {
        ch = normalizeChapterId(m[1]);
        linePart = m[2];
        label = `(${m[1]}, ${m[2]})`;
      } else if (m[3] && m[4]) {
        ch = normalizeChapterId(m[3]);
        linePart = m[4];
        label = `（${m[3]}，${m[4]}）`;
      } else if (m[5]) {
        linePart = m[5];
        ch = chapterFromAnchorContext(text, m.index, defaultChapter);
        label = `锚点 ${m[5]}`;
      } else if (m[6]) {
        linePart = m[6];
        ch = chapterFromAnchorContext(text, m.index, defaultChapter);
        label = m[6];
      } else {
        continue;
      }
      const range = parseLineRange(linePart);
      if (!ch || !range) continue;
      if (m.index > last) frag.appendChild(document.createTextNode(text.slice(last, m.index)));
      const span = document.createElement("span");
      span.className = "anchor-link";
      span.dataset.chapter = ch;
      span.dataset.start = String(range.start);
      span.dataset.end = String(range.end);
      span.textContent = label;
      span.title = "跳转到原文对应段落";
      span.setAttribute("role", "button");
      span.tabIndex = 0;
      frag.appendChild(span);
      linked = true;
      last = m.index + m[0].length;
    }
    if (!linked) return;
    if (last < text.length) frag.appendChild(document.createTextNode(text.slice(last)));
    node.parentNode?.replaceChild(frag, node);
  });
}

initToolbarIcons();
applyLayout();
loadChatsFromStorage();
initResizers();
syncReaderLayout();
refreshLlmStatus({ remind: true });
document.getElementById("reader-view")?.addEventListener("click", handleAnchorActivate);
document.getElementById("reader-view")?.addEventListener("keydown", (e) => {
  if (e.key !== "Enter" && e.key !== " ") return;
  handleAnchorActivate(e);
});
loadShelf().catch((e) => {
  shelf.innerHTML = `<p class="loading">启动失败：${escapeHtml(e.message)}</p>`;
});
window.addEventListener("hashchange", parseHash);
parseHash();
