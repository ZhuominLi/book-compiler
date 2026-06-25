/** Minimal Markdown → HTML (no CDN). */

function renderMd(src) {
  const lines = src.split("\n");
  const out = [];
  let i = 0;
  const esc = (s) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  const inline = (s) =>
    esc(s)
      .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
      .replace(/`([^`]+)`/g, "<code>$1</code>");

  while (i < lines.length) {
    const line = lines[i];
    if (/^---+$/.test(line.trim())) { out.push("<hr>"); i++; continue; }
    if (/^### (.+)/.test(line)) { out.push(`<h3>${inline(line.slice(4))}</h3>`); i++; continue; }
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
      out.push(t + "</tbody></table>");
      continue;
    }
    if (/^[-*] (.+)/.test(line)) {
      const items = [];
      while (i < lines.length && /^[-*] (.+)/.test(lines[i])) {
        items.push(`<li>${inline(lines[i].replace(/^[-*] /, ""))}</li>`);
        i++;
      }
      out.push("<ul>" + items.join("") + "</ul>");
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

const $ = (s) => document.querySelector(s);
const bookSelect = $("#book-select");
const nav = $("#nav");
const content = $("#content");
const sourcePanel = $("#source-body");
const sourceHeader = $("#source-header");
const toggleSide = $("#toggle-side");
const sidePanel = $("#side-panel");
const handleSide = $("#handle-side");
const handleSourceChat = $("#handle-source-chat");
const chatMessages = $("#chat-messages");
const chatForm = $("#chat-form");
const chatInput = $("#chat-input");
const chatSend = $("#chat-send");

const LAYOUT_KEY = "book-compiler-layout";
const CHAT_KEY = "book-compiler-chats";

let state = {
  slug: null,
  meta: null,
  currentChapter: null,
  currentFile: "overview.md",
  sideOpen: true,
  chatHistory: {},
  chatSending: false,
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
  try { data = JSON.parse(text); } catch { throw new Error(text); }
  if (!r.ok) throw new Error(data.error || text);
  return data;
}

function applyLayout() {
  const saved = JSON.parse(localStorage.getItem(LAYOUT_KEY) || "{}");
  document.documentElement.style.setProperty("--nav-w", `${saved.navW || 240}px`);
  document.documentElement.style.setProperty("--side-w", `${saved.sideW || 420}px`);
  document.documentElement.style.setProperty("--source-ratio", saved.sourceRatio ?? 0.42);
}

function saveLayout() {
  const navW = parseInt(getComputedStyle(document.documentElement).getPropertyValue("--nav-w"), 10);
  const sideW = parseInt(getComputedStyle(document.documentElement).getPropertyValue("--side-w"), 10);
  const sourceRatio = parseFloat(getComputedStyle(document.documentElement).getPropertyValue("--source-ratio"));
  localStorage.setItem(LAYOUT_KEY, JSON.stringify({ navW, sideW, sourceRatio }));
}

function initResizers() {
  setupResize($("#handle-nav"), (dx) => {
    const cur = parseInt(getComputedStyle(document.documentElement).getPropertyValue("--nav-w"), 10);
    document.documentElement.style.setProperty("--nav-w", `${Math.min(420, Math.max(160, cur + dx))}px`);
  });
  setupResize(handleSide, (dx) => {
    const cur = parseInt(getComputedStyle(document.documentElement).getPropertyValue("--side-w"), 10);
    document.documentElement.style.setProperty("--side-w", `${Math.min(720, Math.max(300, cur - dx))}px`);
  });
  setupResizeV(handleSourceChat, (dy) => {
    const panel = sidePanel.getBoundingClientRect().height - 48;
    const cur = parseFloat(getComputedStyle(document.documentElement).getPropertyValue("--source-ratio"));
    const delta = dy / panel;
    document.documentElement.style.setProperty("--source-ratio", `${Math.min(0.75, Math.max(0.2, cur + delta))}`);
  });
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
  sidePanel.classList.toggle("hidden", !state.sideOpen);
  handleSide.classList.toggle("hidden", !state.sideOpen);
  toggleSide.classList.toggle("active", state.sideOpen);
}

toggleSide.addEventListener("click", () => {
  state.sideOpen = !state.sideOpen;
  syncSideLayout();
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

function renderChat() {
  const msgs = getChatMessages();
  chatMessages.innerHTML = "";
  if (!msgs.length) {
    const ctx = state.currentChapter
      ? `当前章节：${chapterTitle(state.currentChapter)}`
      : "当前：全书概览";
    const el = document.createElement("div");
    el.className = "chat-row system";
    el.innerHTML = `<div class="chat-bubble system">基于《${escapeHtml(state.meta?.title || "")}》${escapeHtml(ctx)} 提问</div>`;
    chatMessages.appendChild(el);
    return;
  }

  msgs.forEach((m, idx) => {
    const row = document.createElement("div");
    row.className = `chat-row ${m.role}`;
    row.dataset.idx = String(idx);

    const bubble = document.createElement("div");
    bubble.className = `chat-bubble ${m.role}`;

    const body = document.createElement("div");
    body.className = m.role === "assistant" ? "chat-content md-body" : "chat-content";
    if (m.role === "assistant") {
      body.innerHTML = renderMd(m.content);
      linkifyAnchors(body, state.currentChapter);
    } else {
      body.textContent = m.content;
    }
    bubble.appendChild(body);

    if (m.nodes?.length) {
      const meta = document.createElement("div");
      meta.className = "chat-meta";
      meta.textContent = `命中：${m.nodes.join(", ")}`;
      bubble.appendChild(meta);
    }
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
  wrap.className = "chat-bubble user";
  wrap.style.width = "100%";
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
        messages: payload,
      }),
    });
    pending.remove();
    msgs.push({ id: uid(), role: "assistant", content: data.reply, nodes: data.nodes || [] });
    persistChats();
    renderChat();
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

chatInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    chatForm.requestSubmit();
  }
});

function initSourceView() {
  if (state.currentChapter) {
    loadSource(state.currentChapter, 1, 0);
  } else {
    sourceHeader.textContent = "原文";
    sourcePanel.innerHTML =
      '<p class="source-hint">请从左侧选择章节，或点击正文/对话中的「锚点 Lxxx」查看对应原文。</p>';
  }
}

async function loadBooks() {
  const books = await api("/api/books");
  if (!books.length) {
    content.innerHTML = '<p class="loading">未找到书籍。请先运行 pipeline 生成 insight/</p>';
    return;
  }
  bookSelect.innerHTML = books.map((b) => `<option value="${b.slug}">${b.title}</option>`).join("");
  state.slug = books[0].slug;
  await loadBook(state.slug);
}

bookSelect.addEventListener("change", () => loadBook(bookSelect.value));

async function loadBook(slug) {
  state.slug = slug;
  state.meta = await api(`/api/books/${slug}/meta`);
  buildNav();
  await showInsight("overview.md");
  renderChat();
}

function buildNav() {
  const chapters = state.meta.chapters || [];
  nav.innerHTML = `
    <div class="nav-group">
      <div class="nav-label">预览</div>
      <a href="#" data-file="overview.md">全书概览</a>
    </div>
    <div class="nav-group">
      <div class="nav-label">深度 · ${chapters.length} 章</div>
      ${chapters.map((c) =>
        `<a href="#" data-file="chapters/${c.id}.md" data-ch="${c.id}">
          ${String(c.index || c.id.replace("ch", ""))}. ${c.title || ""}
        </a>`
      ).join("")}
    </div>
    <div class="nav-group">
      <div class="nav-label">融会贯通</div>
      <a href="#" data-file="synthesis.md">深度 Insight</a>
      <a href="#" data-file="qa.md">Q&A</a>
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

async function showInsight(file, chapterId = null) {
  state.currentChapter = chapterId;
  state.currentFile = file;
  setActiveNav(file);
  content.innerHTML = '<p class="loading">加载中…</p>';
  try {
    const { content: md } = await api(`/api/books/${state.slug}/insight/${file}`);
    const body = md.replace(/^---[\s\S]*?---\n/, "");
    content.innerHTML = renderMd(body);
    linkifyAnchors(content, chapterId);
  } catch (e) {
    if (chapterId) {
      content.innerHTML = '<p class="loading">本章深度笔记尚未生成。<br>右侧「原文」可阅读 OCR 原文。</p>';
    } else {
      content.innerHTML = `<p class="loading">无法加载：${file}<br>${escapeHtml(e.message)}</p>`;
    }
  }
  if (state.sideOpen) initSourceView();
  renderChat();
}

function linkifyAnchors(root, defaultChapter) {
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  const nodes = [];
  while (walker.nextNode()) nodes.push(walker.currentNode);
  nodes.forEach((node) => {
    const text = node.textContent;
    if (!/L\d+|第\d+页/.test(text)) return;
    const frag = document.createDocumentFragment();
    let last = 0;
    const localRe = /(?:锚点[：:]?\s*)?(L\d+(?:\s*[-–—]\s*L?\d+)?|第\d+页[^，。]*)/g;
    let m;
    while ((m = localRe.exec(text))) {
      if (m.index > last) frag.appendChild(document.createTextNode(text.slice(last, m.index)));
      const full = m[1];
      const a = document.createElement("a");
      a.className = "anchor-link";
      a.textContent = full.replace(/^锚点[：:]?\s*/, "锚点 ");
      a.href = "#";
      a.addEventListener("click", (e) => {
        e.preventDefault();
        const ch = defaultChapter || state.currentChapter;
        const nums = full.match(/L(\d+)/g);
        if (ch && nums) {
          const start = parseInt(nums[0].slice(1), 10);
          const end = nums[1] ? parseInt(nums[1].slice(1), 10) : start;
          loadSource(ch, start, end);
        }
      });
      frag.appendChild(a);
      last = m.index + m[0].length;
    }
    if (last < text.length) frag.appendChild(document.createTextNode(text.slice(last)));
    if (frag.childNodes.length) node.parentNode.replaceChild(frag, node);
  });
}

async function loadSource(chapterId, start, end) {
  if (!state.sideOpen) { state.sideOpen = true; syncSideLayout(); }
  const full = !end || end === 0;
  sourceHeader.textContent = full
    ? `${chapterId} · 全文`
    : `${chapterId} · L${start}${end !== start ? `–L${end}` : ""}`;
  sourcePanel.innerHTML = '<p class="loading">加载原文…</p>';
  try {
    const data = await api(
      `/api/books/${state.slug}/source/${chapterId}?start=${start}&end=${full ? 0 : end}`
    );
    if (!data.lines.length) {
      sourcePanel.innerHTML = '<p class="source-hint">该章节暂无 OCR 原文。</p>';
      return;
    }
    sourcePanel.innerHTML = data.lines
      .map((l) =>
        `<div class="source-line${full ? "" : " highlight"}"><span class="num">${l.n}</span><span class="text">${escapeHtml(l.text)}</span></div>`
      ).join("");
  } catch (e) {
    sourcePanel.innerHTML = `<p class="loading">${escapeHtml(e.message)}</p>`;
  }
}

applyLayout();
loadChatsFromStorage();
initResizers();
syncSideLayout();
loadBooks().catch((e) => {
  content.innerHTML = `<p class="loading">启动失败：${escapeHtml(e.message)}</p>`;
});
