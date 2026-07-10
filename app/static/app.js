// ── DOM 引用 ──────────────────────────────────────────────────

const sessionList = document.querySelector("#sessionList");
const newSessionBtn = document.querySelector("#newSessionBtn");
const sessionStatus = document.querySelector("#sessionStatus");
const userIdInput = document.querySelector("#userId");
const userIdStatus = document.querySelector("#userIdStatus");
const messages = document.querySelector("#messages");
const runSteps = document.querySelector("#runSteps");
const form = document.querySelector("#chatForm");
const messageInput = document.querySelector("#messageInput");
const sendBtn = document.querySelector("#sendBtn");
const stopBtn = document.querySelector("#stopBtn");
const confirmBtn = document.querySelector("#confirmBtn");
const connectionBadge = document.querySelector("#connectionBadge");
const memoryBadge = document.querySelector("#memoryBadge");
const latestSql = document.querySelector("#latestSql");
const copySqlBtn = document.querySelector("#copySqlBtn");
const copySqlStatus = document.querySelector("#copySqlStatus");

const storageKey = "sdkdbagent.sessionId";
const userIdStorageKey = "vkdbagent.userId";

// 当前活跃会话 ID（内存中）
let activeSessionId = null;

// ── 用户标识管理 ──────────────────────────────────────────────

/**
 * 获取当前用户标识。
 * 优先从 localStorage 恢复，否则使用默认值 ""。
 */
function getUserId() {
  return localStorage.getItem(userIdStorageKey) || "";
}

/**
 * 初始化用户标识输入框。
 * 页面加载时从 localStorage 恢复，用户修改后同步写入。
 */
function initUserId() {
  const existing = getUserId();
  userIdInput.value = existing;
  if (existing) {
    userIdStatus.textContent = "已加载";
  }
}

/**
 * 设置用户标识并同步到 localStorage。
 * 返回 true 表示值发生了变化。
 */
function setUserId(value) {
  const trimmed = String(value || "").trim();
  const previous = getUserId();
  localStorage.setItem(userIdStorageKey, trimmed);
  userIdInput.value = trimmed;
  userIdStatus.textContent = trimmed ? "已保存" : "未设置";
  return trimmed !== previous;
}

// ── 通用复制工具 ──────────────────────────────────────────────

/** 将文本复制到剪贴板，始终返回 Promise */
function copyToClipboard(text) {
  // 优先使用 Clipboard API（需要 HTTPS 或 localhost）
  if (navigator.clipboard && window.isSecureContext) {
    return navigator.clipboard.writeText(text);
  }
  // 降级：execCommand 方式（兼容 HTTP 环境）
  return new Promise((resolve, reject) => {
    const textarea = document.createElement("textarea");
    textarea.value = text;
    textarea.style.position = "fixed";
    textarea.style.opacity = "0";
    document.body.appendChild(textarea);
    textarea.select();
    try {
      const ok = document.execCommand("copy");
      document.body.removeChild(textarea);
      ok ? resolve() : reject(new Error("execCommand returned false"));
    } catch (err) {
      document.body.removeChild(textarea);
      reject(err);
    }
  });
}

/** 创建复制按钮 DOM 元素 */
function createCopyButton(onCopy) {
  const btn = document.createElement("button");
  btn.className = "copy-btn";
  btn.type = "button";
  btn.title = "复制";
  btn.innerHTML = `<svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="5.5" y="5.5" width="9" height="9" rx="1.5"/><path d="M2.5 10.5H2a1.5 1.5 0 0 1-1.5-1.5V2.5A1.5 1.5 0 0 1 2 1h7.5a1.5 1.5 0 0 1 1.5 1.5V3"/></svg>`;
  btn.addEventListener("click", (e) => {
    e.stopPropagation();
    e.preventDefault();
    const text = onCopy();
    if (!text) return;
    copyToClipboard(text)
      .then(() => {
        btn.classList.add("copied");
        btn.title = "已复制";
      })
      .catch(() => {
        btn.title = "复制失败";
      })
      .finally(() => {
        setTimeout(() => {
          btn.classList.remove("copied");
          btn.title = "复制";
        }, 1800);
      });
  });
  return btn;
}

// ── 会话管理 ──────────────────────────────────────────────────

/**
 * 列出当前用户的所有会话，渲染到侧边栏。
 */
async function listSessions() {
  const userId = getUserId();
  if (!userId) {
    sessionList.innerHTML = '<div class="session-list-empty">请先设置用户标识</div>';
    sessionStatus.textContent = "未加载";
    return;
  }

  try {
    const response = await fetch(`/api/sessions?user_id=${encodeURIComponent(userId)}`);
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    const data = await response.json();
    const sessions = data.sessions || [];
    renderSessionList(sessions);
  } catch (err) {
    sessionList.innerHTML = '<div class="session-list-empty">加载失败，请重试</div>';
    sessionStatus.textContent = "会话列表加载失败";
  }
}

/**
 * 渲染会话列表，高亮当前活跃会话。
 */
function renderSessionList(sessions) {
  if (!sessions.length) {
    sessionList.innerHTML = '<div class="session-list-empty">暂无会话</div>';
    sessionStatus.textContent = "0 个会话";
    return;
  }

  sessionList.innerHTML = "";
  const fragment = document.createDocumentFragment();

  sessions.forEach((s) => {
    const item = document.createElement("div");
    item.className = `session-item${s.session_id === activeSessionId ? " active" : ""}`;

    const info = document.createElement("div");
    info.className = "session-item-info";

    const idSpan = document.createElement("span");
    idSpan.className = "session-item-id";
    idSpan.textContent = s.summary || s.session_id;
    idSpan.title = s.session_id;

    const meta = document.createElement("span");
    meta.className = "session-item-meta";
    const lastActive = formatRelativeTime(s.last_active_at);
    const created = s.created_at ? s.created_at.slice(0, 10) : "";
    meta.textContent = `${lastActive}${s.message_count ? ` · ${s.message_count} 条消息` : ""}${created ? ` · ${created}` : ""}`;

    info.appendChild(idSpan);
    info.appendChild(meta);

    const delBtn = document.createElement("button");
    delBtn.className = "delete-btn";
    delBtn.type = "button";
    delBtn.title = "删除会话";
    delBtn.innerHTML = '<svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2"><path d="M2 4h12M5.33 4V2.67a1.33 1.33 0 0 1 1.34-1.34h2.66a1.33 1.33 0 0 1 1.34 1.34V4m2 0v9.33a1.33 1.33 0 0 1-1.34 1.34H4.67a1.33 1.33 0 0 1-1.34-1.34V4h9.34z"/></svg>';
    delBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      deleteSession(s.session_id);
    });

    item.appendChild(info);
    item.appendChild(delBtn);

    item.addEventListener("click", () => {
      switchSession(s.session_id);
    });

    fragment.appendChild(item);
  });

  sessionList.appendChild(fragment);
  sessionStatus.textContent = `${sessions.length} 个会话`;
}

/**
 * 创建新会话并通过 POST /api/sessions 注册。
 */
async function createSession() {
  const userId = getUserId();
  if (!userId) {
    sessionStatus.textContent = "请先设置用户标识";
    return;
  }

  setBadge("创建中", "busy");
  try {
    const response = await fetch("/api/sessions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_id: userId }),
    });
    if (!response.ok) {
      const errData = await response.json().catch(() => ({}));
      throw new Error(errData.detail || `HTTP ${response.status}`);
    }
    const data = await response.json();
    switchSession(data.session_id);
  } catch (err) {
    sessionStatus.textContent = `创建失败: ${err.message}`;
    setBadge("创建失败", "error");
  }
}

/**
 * 切换到指定会话：持久化到 localStorage，清空界面，重新加载上下文。
 */
function switchSession(sessionId) {
  if (!sessionId) return;

  // 清理当前流式消息的所有动画并重置渲染器状态
  cleanupAnimations();
  typewriter.reset();
  stepRenderer.clearSteps();

  activeSessionId = sessionId;
  localStorage.setItem(storageKey, sessionId);

  // 清空消息区域（保留欢迎消息）
  messages.querySelectorAll(".message:not(:first-child)").forEach((node) => node.remove());
  runSteps.innerHTML = "";
  latestSql.value = "";
  copySqlBtn.disabled = true;
  copySqlStatus.textContent = "";
  setConfirmationMode(false);

  refreshSession(true);
  listSessions();
}

/**
 * 删除会话：弹出确认对话框，确认后调用 DELETE 并刷新列表。
 */
function deleteSession(sessionId) {
  showConfirmDialog(
    "删除会话",
    `确定要删除会话 "${sessionId}" 吗？此操作不可撤销。`,
    async () => {
      const userId = getUserId();
      if (!userId) return;

      try {
        const response = await fetch(`/api/sessions/${encodeURIComponent(sessionId)}?user_id=${encodeURIComponent(userId)}`, {
          method: "DELETE",
        });
        if (!response.ok) {
          const errData = await response.json().catch(() => ({}));
          throw new Error(errData.detail || `HTTP ${response.status}`);
        }

        // 如果删除的是当前活跃会话，清除活跃状态
        if (activeSessionId === sessionId) {
          activeSessionId = null;
          localStorage.removeItem(storageKey);
          messages.querySelectorAll(".message:not(:first-child)").forEach((node) => node.remove());
          runSteps.innerHTML = "";
          latestSql.value = "";
          copySqlBtn.disabled = true;
          copySqlStatus.textContent = "";
          setConfirmationMode(false);
          sessionStatus.textContent = "未加载";
        }

        listSessions();
      } catch (err) {
        sessionStatus.textContent = `删除失败: ${err.message}`;
      }
    }
  );
}

/**
 * 确认对话框组件。
 */
function showConfirmDialog(title, message, onConfirm) {
  const overlay = document.createElement("div");
  overlay.className = "confirm-overlay";

  const dialog = document.createElement("div");
  dialog.className = "confirm-dialog";

  dialog.innerHTML = `
    <h3>${escapeHtml(title)}</h3>
    <p>${escapeHtml(message)}</p>
    <div class="confirm-dialog-actions">
      <button class="cancel-btn" type="button">取消</button>
      <button class="danger-btn" type="button">确认删除</button>
    </div>
  `;

  overlay.appendChild(dialog);
  document.body.appendChild(overlay);

  const close = () => {
    document.body.removeChild(overlay);
  };

  dialog.querySelector(".cancel-btn").addEventListener("click", close);
  dialog.querySelector(".danger-btn").addEventListener("click", () => {
    close();
    onConfirm();
  });
  overlay.addEventListener("click", (e) => {
    if (e.target === overlay) close();
  });
}

/**
 * 格式化相对时间（简易版）。
 */
function formatRelativeTime(isoStr) {
  if (!isoStr) return "";
  const now = Date.now();
  const then = new Date(isoStr).getTime();
  if (isNaN(then)) return "";
  const diffMs = now - then;
  const diffSec = Math.floor(diffMs / 1000);
  if (diffSec < 60) return "刚刚";
  const diffMin = Math.floor(diffSec / 60);
  if (diffMin < 60) return `${diffMin} 分钟前`;
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return `${diffHr} 小时前`;
  const diffDay = Math.floor(diffHr / 24);
  if (diffDay < 30) return `${diffDay} 天前`;
  return new Date(isoStr).toLocaleDateString("zh-CN");
}

/**
 * 刷新当前会话信息（从服务端获取最新状态）。
 */
async function refreshSession(renderHistory = false) {
  const id = activeSessionId;
  if (!id) return;
  try {
    const userId = getUserId();
    const params = new URLSearchParams();
    if (userId) params.set("user_id", userId);
    const qs = params.toString();
    const url = `/api/sessions/${encodeURIComponent(id)}${qs ? "?" + qs : ""}`;
    const response = await fetch(url);
    const data = await response.json();
    const db = data.selected_database || {};
    const selected = data.selected_schema_id
      ? `${db.schemaName || "schema"} @ ${db.instanceName || data.selected_schema_id}`
      : "";
    sessionStatus.textContent = `${selected}${data.needs_confirmation ? "，等待确认" : ""}`;
    updateLatestSql(data.latest_sql);
    updateMemoryBadge(data.memory_count || 0);
    setConfirmationMode(Boolean(data.needs_confirmation));

    if (renderHistory && data.chat_history && data.chat_history.length) {
      renderChatHistory(data.chat_history);
    }
  } catch {
    sessionStatus.textContent = "会话状态读取失败";
  }
}

/**
 * 将会话历史渲染到消息区域。
 */
function renderChatHistory(chatHistory) {
  chatHistory.forEach((entry) => {
    const role = entry.role;
    const content = entry.content || "";
    appendMessage(role, content);
  });
}

/**
 * 初始化会话：从 localStorage 恢复活跃会话，按用户列出会话列表。
 */
function initSession() {
  const saved = localStorage.getItem(storageKey);
  if (saved) {
    activeSessionId = saved;
  }
  listSessions();
  if (activeSessionId) {
    refreshSession(true);
  }
}

function setBadge(text, mode = "") {
  connectionBadge.textContent = text;
  connectionBadge.className = `badge ${mode}`.trim();
}

function updateMemoryBadge(count) {
  if (memoryBadge) {
    memoryBadge.textContent = count > 0 ? `🧠 ${count}` : "🧠 --";
    memoryBadge.title = count > 0 ? `已加载 ${count} 条长期记忆` : "无长期记忆";
  }
}

function setConfirmationMode(needsConfirmation) {
  confirmBtn.hidden = !needsConfirmation;
  confirmBtn.disabled = !needsConfirmation;
  sendBtn.hidden = needsConfirmation;
  sendBtn.disabled = needsConfirmation;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function inlineMarkdown(text) {
  return escapeHtml(text)
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
}

function renderTable(lines) {
  const rows = lines
    .filter((line) => line.trim().startsWith("|"))
    .map((line) => line.trim().slice(1, -1).split("|").map((cell) => inlineMarkdown(cell.trim())));
  if (rows.length < 2) return `<p>${inlineMarkdown(lines.join("\n"))}</p>`;
  const header = rows[0];
  const body = rows.slice(2);
  return `<table><thead><tr>${header.map((cell) => `<th>${cell}</th>`).join("")}</tr></thead><tbody>${body
    .map((row) => `<tr>${row.map((cell) => `<td>${cell}</td>`).join("")}</tr>`)
    .join("")}</tbody></table>`;
}

function renderMarkdown(markdown) {
  const lines = String(markdown || "").split(/\r?\n/);
  const blocks = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];
    if (!line.trim()) {
      i += 1;
      continue;
    }
    if (line.startsWith("```")) {
      const code = [];
      i += 1;
      while (i < lines.length && !lines[i].startsWith("```")) {
        code.push(lines[i]);
        i += 1;
      }
      i += 1;
      blocks.push(`<pre><code>${escapeHtml(code.join("\n"))}</code></pre>`);
      continue;
    }
    if (line.trim().startsWith("|")) {
      const table = [];
      while (i < lines.length && lines[i].trim().startsWith("|")) {
        table.push(lines[i]);
        i += 1;
      }
      blocks.push(renderTable(table));
      continue;
    }
    if (/^#{1,3}\s+/.test(line)) {
      blocks.push(`<h3>${inlineMarkdown(line.replace(/^#{1,3}\s+/, ""))}</h3>`);
      i += 1;
      continue;
    }
    if (/^\s*[-*]\s+/.test(line)) {
      const items = [];
      while (i < lines.length && /^\s*[-*]\s+/.test(lines[i])) {
        items.push(`<li>${inlineMarkdown(lines[i].replace(/^\s*[-*]\s+/, ""))}</li>`);
        i += 1;
      }
      blocks.push(`<ul>${items.join("")}</ul>`);
      continue;
    }
    const paragraph = [];
    while (i < lines.length && lines[i].trim() && !lines[i].trim().startsWith("|") && !lines[i].startsWith("```")) {
      paragraph.push(lines[i]);
      i += 1;
    }
    blocks.push(`<p>${inlineMarkdown(paragraph.join(" "))}</p>`);
  }

  return blocks.join("");
}

function appendMessage(role, content) {
  const article = document.createElement("article");
  article.className = `message ${role}`;
  const avatar = document.createElement("div");
  avatar.className = "avatar";
  avatar.textContent = role === "user" ? "U" : "A";
  const bubble = document.createElement("div");
  bubble.className = "bubble";
  const meta = document.createElement("div");
  meta.className = "meta";
  meta.textContent = role === "user" ? "你" : "DBAgent";
  const body = document.createElement("div");
  body.className = "content";
  body.innerHTML = role === "assistant" ? renderMarkdown(content) : escapeHtml(content);
  bubble.append(meta, body);

  // 复制按钮
  const copyBtn = createCopyButton(() => body.innerText);
  bubble.appendChild(copyBtn);

  article.append(avatar, bubble);
  messages.appendChild(article);
  messages.scrollTop = messages.scrollHeight;
}

function sqlFromReply(reply) {
  const match = String(reply || "").match(/```sql\s*([\s\S]*?)```/i);
  return match ? match[1].trim() : "";
}

function latestSqlFromToolCalls(toolCalls) {
  for (const call of [...(toolCalls || [])].reverse()) {
    const sql = call?.nl2sql?.sql;
    if (sql) return sql;
  }
  return "";
}

function updateLatestSql(sql) {
  const value = String(sql || "").trim();
  if (!value) return;
  latestSql.value = value;
  copySqlBtn.disabled = false;
  copySqlStatus.textContent = "";
}

async function copyLatestSql() {
  const sql = latestSql.value.trim();
  if (!sql) return;
  try {
    await copyToClipboard(sql);
    copySqlStatus.textContent = "已复制";
  } catch {
    copySqlStatus.textContent = "复制失败";
  }
  window.setTimeout(() => {
    copySqlStatus.textContent = "";
  }, 1800);
}

function addStep(step, state) {
  const status = state?.status || "running";
  const stepId = `step-${step}`;
  let item = document.getElementById(stepId);

  if (!item) {
    item = document.createElement("div");
    item.id = stepId;
    item.className = "step";
    runSteps.appendChild(item);
  }

  const label = status === "running" ? `${escapeHtml(step)}` : `${escapeHtml(step)}`;
  item.innerHTML = `<strong>${label}</strong><span>${escapeHtml(status)}</span>`;
  item.className = `step ${status}`;

  // 动态渲染到聊天区域
  updateStreamingMessage(step, state);
}

// ── TypewriterRenderer ──────────────────────────────────────────
// 打字机状态机：管理思考文本的逐字渲染

function createTypewriterRenderer() {
  let fullText = "";
  let displayedLength = 0;
  let charDelay = 30;
  let isRunning = false;
  let rafId = null;
  let lastTickTime = 0;
  let targetElement = null;
  let onRenderCallback = null;
  let onCompleteCallback = null;
  let startTime = 0;
  let useTruncation = true;       // 思考模式：截断；回复模式：完整渲染
  const MAX_PREVIEW = 30;         // 思考预览最多显示前 30 个字符

  // 将文本截断为前 MAX_PREVIEW 个字符，超出部分用 "..." 省略
  function truncatePreview(text) {
    if (!useTruncation || text.length <= MAX_PREVIEW) return text;
    return text.substring(0, MAX_PREVIEW) + "...";
  }

  function tick(timestamp) {
    if (!isRunning) return;
    if (!lastTickTime) lastTickTime = timestamp;

    const elapsed = timestamp - lastTickTime;
    const queueElapsed = timestamp - startTime;

    // 加速模式：队列超过 3 秒 → 字符间隔降至 5ms
    const effectiveDelay = queueElapsed > 3000 ? 5 : charDelay;

    // 后台标签页恢复：时间差超过 100ms → 批量渲染 5 个字符
    const batchSize = elapsed > 100 ? 5 : 1;

    if (elapsed >= effectiveDelay) {
      let charsRendered = 0;
      while (charsRendered < batchSize && displayedLength < fullText.length) {
        displayedLength++;
        charsRendered++;
      }
      if (targetElement) {
        const preview = fullText.substring(0, displayedLength);
        targetElement.textContent = truncatePreview(preview);
      }
      if (onRenderCallback) onRenderCallback();
      lastTickTime = timestamp;
    }

    if (displayedLength < fullText.length) {
      rafId = requestAnimationFrame(tick);
    } else {
      // 全部渲染完成 → 移除光标
      if (targetElement) {
        targetElement.classList.remove("streaming-cursor");
      }
      isRunning = false;
      rafId = null;
      // 触发完成回调
      if (onCompleteCallback) {
        const cb = onCompleteCallback;
        onCompleteCallback = null;
        cb();
      }
    }
  }

  function appendText(text) {
    try {
      if (typeof text !== "string") {
        text = String(text ?? "");
      }
      fullText += text;
      // 同步渲染截断预览：立即更新 DOM，不等待 rAF
      // rAF 不会在繁忙的 SSE 事件处理循环中调用
      if (targetElement) {
        if (!isRunning) {
          targetElement.classList.add("streaming-cursor");
        }
        targetElement.textContent = truncatePreview(fullText);
        if (onRenderCallback) onRenderCallback();
      }
      if (!isRunning) {
        startTime = performance.now();
        isRunning = true;
        lastTickTime = 0;
        rafId = requestAnimationFrame(tick);
      }
    } catch (e) {
      // 异常降级：立即显示全部缓冲文本
      flush();
    }
  }

  function flush() {
    if (rafId !== null) {
      cancelAnimationFrame(rafId);
      rafId = null;
    }
    try {
      displayedLength = fullText.length;
      if (targetElement) {
        targetElement.textContent = fullText;
        targetElement.classList.remove("streaming-cursor");
      }
    } catch (e) {
      // DOM 操作失败，静默降级
    }
    isRunning = false;
  }

  function stop() {
    if (rafId !== null) {
      cancelAnimationFrame(rafId);
      rafId = null;
    }
    isRunning = false;
    if (targetElement) {
      targetElement.classList.remove("streaming-cursor");
    }
  }

  function reset() {
    stop();
    fullText = "";
    displayedLength = 0;
    charDelay = 30;
    lastTickTime = 0;
    startTime = 0;
  }

  function setTarget(el) {
    targetElement = el;
  }

  function setOnRender(cb) {
    onRenderCallback = cb;
  }

  function setOnComplete(cb) {
    onCompleteCallback = cb;
  }

  function setCharDelay(delay) {
    charDelay = delay;
  }

  function setUseTruncation(truncate) {
    useTruncation = truncate;
  }

  function getIsComplete() {
    return !isRunning && displayedLength >= fullText.length && fullText.length > 0;
  }

  return {
    appendText,
    flush,
    stop,
    reset,
    setTarget,
    setOnRender,
    setOnComplete,
    setCharDelay,
    setUseTruncation,
    getIsComplete,
  };
}

// 全局单例
const typewriter = createTypewriterRenderer();

// ── StepRenderer ─────────────────────────────────────────────────
// 工具步骤增量 DOM 渲染：维护 stepId → StepEntry 的 Map 映射，
// 仅更新变更步骤的类名和图标，不重建整个容器。

function createStepRenderer() {
  const steps = new Map();           // stepId → { stepId, status, label, element }
  let container = null;

  /**
   * 根据状态创建对应的图标元素。
   * running：CSS pulse-dot 动画指示器
   * completed：✅ 静态图标
   * error：❌ 静态图标
   */
  function _createIcon(status) {
    if (status === "running") {
      const dot = document.createElement("span");
      dot.className = "pulse-dot";
      return dot;
    }
    if (status === "completed") {
      return document.createTextNode("✅");
    }
    if (status === "error") {
      return document.createTextNode("❌");
    }
    return document.createTextNode("");
  }

  /**
   * 创建新的工具步骤 DOM 元素并追加到容器。
   * 若 stepId 已存在，先移除旧元素再创建新元素。
   */
  function createStep(stepId, label) {
    if (!container) return null;

    // 移除已存在的同名步骤
    if (steps.has(stepId)) {
      const old = steps.get(stepId);
      if (old.element && old.element.parentNode) {
        old.element.parentNode.removeChild(old.element);
      }
      steps.delete(stepId);
    }

    const element = document.createElement("div");
    element.className = "streaming-step running";

    const iconSpan = document.createElement("span");
    iconSpan.className = "step-icon";
    iconSpan.appendChild(_createIcon("running"));

    const textSpan = document.createElement("span");
    textSpan.className = "step-text";
    textSpan.textContent = label;

    element.appendChild(iconSpan);
    element.appendChild(textSpan);
    container.appendChild(element);

    const entry = { stepId, status: "running", label, element };
    steps.set(stepId, entry);
    return entry;
  }

  /**
   * 更新步骤状态。
   * 状态过渡：先移除旧类名 → rAF 延迟一帧 → 添加新类名，触发 CSS transition。
   * 仅对 running 状态的步骤保留动画类名。
   */
  function updateStep(stepId, status) {
    const entry = steps.get(stepId);
    if (!entry || !entry.element) return;

    const validStatuses = ["running", "completed", "error"];
    if (!validStatuses.includes(status)) return;

    const oldStatus = entry.status;
    if (oldStatus === status) return;

    const element = entry.element;
    const iconSpan = element.querySelector(".step-icon");
    if (!iconSpan) return;

    // 先移除旧状态类名
    element.classList.remove(oldStatus);

    // 延迟一帧后添加新状态类名，触发 CSS transition
    requestAnimationFrame(() => {
      element.classList.add(status);

      // 更新图标
      iconSpan.innerHTML = "";
      iconSpan.appendChild(_createIcon(status));
    });

    entry.status = status;
  }

  /**
   * 清除所有步骤 DOM 元素和内部状态。
   */
  function clearSteps() {
    for (const [, entry] of steps) {
      if (entry.element && entry.element.parentNode) {
        entry.element.parentNode.removeChild(entry.element);
      }
    }
    steps.clear();
  }

  function setContainer(el) {
    container = el;
  }

  function getContainer() {
    return container;
  }

  function getStep(stepId) {
    return steps.get(stepId) || null;
  }

  function getStepCount() {
    return steps.size;
  }

  function hasStep(stepId) {
    return steps.has(stepId);
  }

  return {
    createStep,
    updateStep,
    clearSteps,
    setContainer,
    getContainer,
    getStep,
    getStepCount,
    hasStep,
  };
}

// 全局单例
const stepRenderer = createStepRenderer();

// ── PhaseLabel & AnimationCleanup ────────────────────────────────
// 阶段标签更新与动画清理（集成任务 2.3）

/**
 * 根据当前 step 更新流式气泡 `.meta` 元素文本。
 * - thinking: "DBAgent · 思考中..."
 * - tool:*: "DBAgent · 正在查询数据库..."
 * - 其他: "DBAgent"
 */
function updatePhaseLabel(step) {
  const streamingEl = document.querySelector("article.message.assistant.streaming");
  if (!streamingEl) return;
  const meta = streamingEl.querySelector(".meta");
  if (!meta) return;

  if (step === "thinking") {
    meta.textContent = "DBAgent · 思考中...";
  } else if (step && step.startsWith("tool:")) {
    meta.textContent = "DBAgent · 正在查询数据库...";
  } else {
    meta.textContent = "DBAgent";
  }
}

/**
 * 清理所有动画效果：停止 TypewriterRenderer、清除步骤动画类名和 will-change 属性、
 * 恢复 .meta 标签为 "DBAgent"。
 * 调用点：finalizeStreamingMessage（正常/取消）、switchSession、sendMessage。
 */
function cleanupAnimations() {
  // 停止打字机（不 flush，保留当前渲染内容）
  typewriter.stop();

  const streamingEl = document.querySelector("article.message.assistant.streaming");
  if (streamingEl) {
    // 清除所有步骤动画类名
    const steps = streamingEl.querySelectorAll(".streaming-step");
    steps.forEach((step) => {
      step.classList.remove("running");
      step.style.willChange = "";
    });

    // 移除所有 will-change 属性
    streamingEl.querySelectorAll("[style*=\"will-change\"]").forEach((el) => {
      el.style.willChange = "";
    });

    // 恢复 .meta 标签
    const meta = streamingEl.querySelector(".meta");
    if (meta) {
      meta.textContent = "DBAgent";
    }
  }
}

// ── 流式消息渲染 ──────────────────────────────────────────────

let streamingMessage = null;   // 当前流式消息的 DOM 元素
let streamingText = "";        // 累积的思考文本
let streamingSteps = [];       // 累积的步骤信息
let abortController = null;    // 当前请求的 AbortController
let finalHandled = false;      // 防止双重 final 事件
let lastPhase = null;          // 上一阶段类型（thinking/tool），用于跨轮次状态管理

function updateStreamingMessage(step, state) {
  const status = state?.status || "running";
  const text = state?.text || "";

  // Create streaming bubble if not yet created
  if (!streamingMessage) {
    streamingMessage = createStreamingBubble();
  }

  // Phase label: update .meta to reflect current stage
  updatePhaseLabel(step);

  if (step === "thinking") {
    // 如果上一阶段是工具调用，说明进入了新一轮思考，重置打字机状态
    if (lastPhase === "tool" && text) {
      typewriter.reset();
      // 重新设置 target（reset 不清除 target，但确保光标恢复）
      const thinkingEl = streamingMessage?.querySelector(".thinking-text");
      if (thinkingEl) {
        typewriter.setTarget(thinkingEl);
        thinkingEl.classList.add("streaming-cursor");
      }
    }
    if (text) {
      typewriter.appendText(text);
    }
    lastPhase = "thinking";
  } else if (step && step.startsWith("tool:")) {
    lastPhase = "tool";
  }
  // 注意：不在这里调用 typewriter.flush()，让打字机在后台持续运行
  // 即使工具步骤同时到达，思考文本也会逐字渲染
  // flush 仅在 final 事件时通过 finalizeStreamingMessage 触发

  // Tool steps → StepRenderer (incremental DOM, no innerHTML rebuild)
  if (step && step.startsWith("tool:")) {
    // 进入工具阶段时清除思考文本预览，避免与工具步骤视觉混淆
    const thinkingEl = streamingMessage?.querySelector(".thinking-text");
    if (thinkingEl) {
      thinkingEl.textContent = "";
      thinkingEl.classList.remove("streaming-cursor");
    }

    const label = step.replace(/^tool:/, "");

    if (stepRenderer.hasStep(step)) {
      stepRenderer.updateStep(step, status);
    } else {
      stepRenderer.createStep(step, label);
    }
  }

  // 每次 SSE 事件后滚动到最新位置
  messages.scrollTop = messages.scrollHeight;
}

function createStreamingBubble() {
  const article = document.createElement("article");
  article.className = "message assistant streaming";

  const avatar = document.createElement("div");
  avatar.className = "avatar";
  avatar.textContent = "A";

  const bubble = document.createElement("div");
  bubble.className = "bubble";

  const meta = document.createElement("div");
  meta.className = "meta";
  meta.textContent = "DBAgent";

  const body = document.createElement("div");
  body.className = "content";

  // Persistent DOM elements for incremental rendering
  // thinkingEl: TypewriterRenderer target, operates on textContent
  const thinkingEl = document.createElement("div");
  thinkingEl.className = "thinking-text streaming-cursor";

  // stepsContainer: StepRenderer manages child elements here
  const stepsContainer = document.createElement("div");
  stepsContainer.className = "streaming-steps";

  body.appendChild(thinkingEl);
  body.appendChild(stepsContainer);

  // Wire renderers to persistent DOM elements
  typewriter.setTarget(thinkingEl);
  typewriter.setOnRender(() => {
    messages.scrollTop = messages.scrollHeight;
  });
  stepRenderer.setContainer(stepsContainer);

  bubble.append(meta, body);
  article.append(avatar, bubble);
  messages.appendChild(article);
  return article;
}

function finalizeStreamingMessage(cancelled = false) {
  // 清理工具步骤动画
  stepRenderer.clearSteps();

  if (streamingMessage) {
    if (cancelled) {
      // 取消：停止打字机，移除动画类，追加标记
      typewriter.stop();
      streamingMessage.classList.remove("streaming");
      streamingMessage.classList.add("cancelled");
      const body = streamingMessage.querySelector(".content");
      if (body) {
        const stopMark = document.createElement("div");
        stopMark.className = "cancelled-mark";
        stopMark.textContent = "[已停止生成]";
        stopMark.style.cssText = "color:#b45309;font-size:13px;margin-top:8px;font-style:italic;";
        body.appendChild(stopMark);
      }
      // 恢复 .meta
      const meta = streamingMessage.querySelector(".meta");
      if (meta) meta.textContent = "DBAgent";
      streamingMessage = null;
    }
    // 正常完成：不删除气泡，由 finalizeReply 用打字机渲染最终回答
  }
  streamingText = "";
  streamingSteps = [];
}

/**
 * 剥离 Markdown 格式符号，返回纯文本用于打字机渲染预览。
 * 保留表格结构、代码块标记、标题和列表的视觉线索。
 */
function stripMarkdownForTypewriter(text) {
  return String(text ?? "")
    // 标题符号 → 保留文字
    .replace(/^#{1,3}\s+/gm, "")
    // 粗体/斜体
    .replace(/\*\*([^*]+)\*\*/g, "$1")
    .replace(/\*([^*]+)\*/g, "$1")
    // 行内代码
    .replace(/`([^`]+)`/g, "$1")
    // 列表标记 → 保留文字
    .replace(/^\s*[-*]\s+/gm, "")
    // 代码块标记 → 用空白行分隔
    .replace(/```[\s\S]*?```/g, "[代码块]")
    .replace(/```\w*/g, "")
    // 链接
    .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1");
}

/**
 * 用快速打字机效果渲染最终回答到流式气泡中。
 * 打字机期间显示剥离 Markdown 的纯文本，完成后一次性替换为完整 Markdown 渲染。
 */
function finalizeReply(replyText) {
  if (!streamingMessage || !replyText) {
    if (replyText) appendMessage("assistant", replyText);
    return;
  }

  const body = streamingMessage.querySelector(".content");
  if (!body) {
    appendMessage("assistant", replyText);
    return;
  }
  body.innerHTML = "";

  // 创建回复渲染目标元素（使用独立类，允许多行换行）
  const replyEl = document.createElement("div");
  replyEl.className = "reply-text streaming-cursor";
  body.appendChild(replyEl);

  // 剥离 Markdown 的纯文本版本（打字机渲染用）
  const plainText = stripMarkdownForTypewriter(replyText);

  typewriter.reset();
  typewriter.setTarget(replyEl);
  typewriter.setCharDelay(10);
  typewriter.setUseTruncation(false);
  typewriter.setOnRender(() => {
    messages.scrollTop = messages.scrollHeight;
  });
  typewriter.setOnComplete(() => {
    // 打字机完成 → 替换为完整 Markdown 渲染
    body.innerHTML = renderMarkdown(replyText);
    typewriter.setCharDelay(30);
    typewriter.setUseTruncation(true);
    streamingMessage.classList.remove("streaming");
    const meta = streamingMessage.querySelector(".meta");
    if (meta) meta.textContent = "DBAgent";
    const copyBtn = createCopyButton(() => body.innerText);
    streamingMessage.querySelector(".bubble").appendChild(copyBtn);
    streamingMessage = null;
    messages.scrollTop = messages.scrollHeight;
  });

  // 渲染剥离 Markdown 后的纯文本
  typewriter.appendText(plainText);
}

function parseSseChunk(buffer, onEvent) {
  const parts = buffer.split("\n\n");
  const rest = parts.pop() || "";
  for (const part of parts) {
    const dataLine = part.split("\n").find((line) => line.startsWith("data: "));
    if (!dataLine) continue;
    try {
      onEvent(JSON.parse(dataLine.slice(6)));
    } catch {
      onEvent({ type: "error", message: "SSE 数据解析失败" });
    }
  }
  return rest;
}

async function sendMessage(message) {
  const sessionId = activeSessionId;
  if (!message || !sessionId) return;

  // 清理上一轮流式消息的动画并重置渲染器状态
  cleanupAnimations();
  typewriter.reset();
  stepRenderer.clearSteps();

  appendMessage("user", message);
  messageInput.value = "";
  runSteps.innerHTML = "";
  sendBtn.hidden = true;
  stopBtn.hidden = false;
  stopBtn.disabled = false;
  confirmBtn.disabled = true;
  setBadge("运行中", "busy");

  // 重置取消相关状态
  abortController = new AbortController();
  finalHandled = false;

  let finalPayload = null;
  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sessionId, user_id: getUserId(), message }),
      signal: abortController.signal,
    });
    if (!response.ok || !response.body) throw new Error(`HTTP ${response.status}`);

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      buffer = parseSseChunk(buffer, (event) => {
        if (event.type === "step") {
          addStep(event.step, {status: event.status, text: event.text || ""});
        }
        if (event.type === "sql") {
          console.log('[SQL Event]', event.sql);
          updateLatestSql(event.sql);
        }
        if (event.type === "final") {
          // 双重 final 事件防抖
          if (finalHandled) return;
          finalPayload = event;
        }
      });
    }
    if (finalPayload) {
      const cancelled = finalPayload.cancelled === true;

      if (cancelled) {
        // 取消场景：原地保留流式气泡，追加标记
        finalHandled = true;
        finalizeStreamingMessage(true);

        runSteps.innerHTML = `<div class="step completed"><strong>已取消</strong><span>已停止生成</span></div>`;
        setBadge("已取消", "cancelled");
        setConfirmationMode(false);
      } else {
        // 正常完成
        finalHandled = true;
        finalizeStreamingMessage(false);

        const stats = finalPayload.stats || {};
        const toolCount = (finalPayload.tool_calls || []).length;
        const durationMs = stats.duration_ms || 0;
        const durationSec = durationMs ? (durationMs / 1000).toFixed(1) + "s" : "N/A";
        const tokens = stats.tokens ? stats.tokens + " tokens" : "";
        runSteps.innerHTML = `<div class="step completed"><strong>${toolCount} tools</strong><span>${tokens} | ${durationSec}</span></div>`;

        // 用打字机效果渲染最终回答（不再 appendMessage 一次性输出）
        finalizeReply(finalPayload.reply || "没有返回内容。");
        updateLatestSql(
          finalPayload.latest_sql || latestSqlFromToolCalls(finalPayload.tool_calls) || sqlFromReply(finalPayload.reply)
        );
        setBadge(finalPayload.needs_confirmation ? "等待确认" : "就绪", finalPayload.needs_confirmation ? "busy" : "");
        updateMemoryBadge(finalPayload.memory_count || 0);
        setConfirmationMode(Boolean(finalPayload.needs_confirmation));
      }
    } else {
      throw new Error("没有收到 final 事件");
    }
  } catch (error) {
    if (error.name === "AbortError") {
      // 用户取消导致的 AbortError，静默处理
      if (!finalHandled) {
        finalizeStreamingMessage(true);
        runSteps.innerHTML = `<div class="step completed"><strong>已取消</strong><span>连接已断开</span></div>`;
        setBadge("已取消", "cancelled");
        setConfirmationMode(false);
      }
    } else {
      runSteps.innerHTML = `<div class="step error"><strong>请求失败</strong><span>${escapeHtml(error.message)}</span></div>`;
      appendMessage("assistant", `请求失败：${error.message}`);
      setBadge("请求失败", "error");
      setConfirmationMode(false);
    }
  } finally {
    // 恢复 UI 状态
    sendBtn.hidden = false;
    stopBtn.hidden = true;
    abortController = null;
    refreshSession();
  }
}

async function stopGeneration() {
  if (!abortController) return;

  const sessionId = activeSessionId;
  if (!sessionId) return;

  stopBtn.disabled = true;
  setBadge("取消中", "busy");

  try {
    // 先发送优雅取消请求
    const cancelResponse = await fetch(`/api/chat/${encodeURIComponent(sessionId)}/cancel`, {
      method: "POST",
    });
    const cancelData = await cancelResponse.json();

    if (cancelData.cancelled) {
      // 取消信号已发送，等待 SSE 返回 cancelled 事件
      // 给 500ms 窗口，若超时则强制 abort
      setTimeout(() => {
        if (!finalHandled && abortController) {
          abortController.abort();
        }
      }, 500);
    } else {
      // 没有活跃的 Agent，直接强制断开
      abortController.abort();
    }
  } catch {
    // 取消请求失败，直接强制断开
    if (abortController) {
      abortController.abort();
    }
  }
}

// 停止按钮事件
stopBtn.addEventListener("click", (event) => {
  event.preventDefault();
  stopGeneration();
});

form.addEventListener("submit", (event) => {
  event.preventDefault();
  sendMessage(messageInput.value.trim());
});

messageInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
    event.preventDefault();
    sendMessage(messageInput.value.trim());
  }
});

confirmBtn.addEventListener("click", () => sendMessage("确认执行"));

copySqlBtn.addEventListener("click", copyLatestSql);

newSessionBtn.addEventListener("click", createSession);

userIdInput.addEventListener("change", () => {
  const changed = setUserId(userIdInput.value);
  userIdStatus.textContent = getUserId() ? "已保存" : "未设置";
  if (changed) {
    // 切换用户后清空当前会话，刷新列表
    activeSessionId = null;
    localStorage.removeItem(storageKey);
    messages.querySelectorAll(".message:not(:first-child)").forEach((node) => node.remove());
    runSteps.innerHTML = "";
    latestSql.value = "";
    copySqlBtn.disabled = true;
    copySqlStatus.textContent = "";
    setConfirmationMode(false);
    setBadge("就绪", "");
    listSessions();
  }
});

document.querySelectorAll("[data-prompt]").forEach((button) => {
  button.addEventListener("click", () => {
    messageInput.value = button.dataset.prompt || "";
    messageInput.focus();
  });
});

initUserId();
initSession();
