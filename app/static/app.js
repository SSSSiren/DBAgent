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
const confirmBtn = document.querySelector("#confirmBtn");
const connectionBadge = document.querySelector("#connectionBadge");
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

  activeSessionId = sessionId;
  localStorage.setItem(storageKey, sessionId);

  // 清空消息区域（保留欢迎消息）
  messages.querySelectorAll(".message:not(:first-child)").forEach((node) => node.remove());
  runSteps.innerHTML = "";
  latestSql.value = "";
  copySqlBtn.disabled = true;
  copySqlStatus.textContent = "";
  setConfirmationMode(false);

  refreshSession();
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
async function refreshSession() {
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
    setConfirmationMode(Boolean(data.needs_confirmation));
  } catch {
    sessionStatus.textContent = "会话状态读取失败";
  }
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
    refreshSession();
  }
}

function setBadge(text, mode = "") {
  connectionBadge.textContent = text;
  connectionBadge.className = `badge ${mode}`.trim();
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

function appendMessage(role, content, toolCalls = []) {
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
  if (toolCalls.length) {
    const tools = document.createElement("div");
    tools.className = "tool-block";
    tools.innerHTML = renderToolCalls(toolCalls);
    bubble.appendChild(tools);
  }

  // 添加复制按钮（用户消息和 AI 回复各一条消息一个按钮）
  const copyBtn = createCopyButton(() => {
    // 提取纯文本内容
    let text = body.innerText;
    // 如果有工具调用，也追加工具调用信息
    if (toolCalls.length) {
      const toolTexts = toolCalls.map(call => {
        const sql = call?.nl2sql?.sql || "";
        return sql ? `\n\nSQL: ${sql}` : "";
      }).filter(Boolean);
      text += toolTexts.join("");
    }
    return text;
  });
  bubble.appendChild(copyBtn);

  article.append(avatar, bubble);
  messages.appendChild(article);
  messages.scrollTop = messages.scrollHeight;
}

function renderToolCalls(toolCalls) {
  return toolCalls
    .map((call) => {
      const base = `<div class="tool-title">工具调用：${escapeHtml(call.tool)}(${escapeHtml(call.status)})</div>`;

      // 尝试从 result 中提取 SQL
      let sqlHtml = "";
      let resultContent = "";
      let resultWithoutSql = "";

      // 处理 result 可能是对象的情况
      if (call.result) {
        if (typeof call.result === 'string') {
          resultContent = call.result;
        } else if (typeof call.result === 'object' && call.result.content) {
          resultContent = call.result.content;
        }
      }

      if (resultContent) {
        // 添加调试日志
        if (call.tool === 'query_database_tool') {
          console.log('query_database_tool resultContent:', resultContent);
        }
        // 改进的正则表达式，匹配 ```sql 或 ``` 代码块
        const sqlMatch = resultContent.match(/```sql\s+([\s\S]+?)```/) ||
                         resultContent.match(/```\s+([\s\S]+?)```/);
        if (sqlMatch) {
          let sql = sqlMatch[1].trim();
          // 清理 SQL：去除字面的 \n 和 \r 字符串，以及真正的换行符
          sql = sql.replace(/\\n/g, ' ').replace(/\\r/g, '');
          sql = sql.replace(/^[\r\n]+|[\r\n]+$/g, '').replace(/;\s*$/, '');
          sql = sql.replace(/\s+/g, ' ');  // 合并多个空白为单个空格
          // 检查是否包含 SQL 关键字
          if (sql.match(/\b(SELECT|INSERT|UPDATE|DELETE|CREATE|ALTER|DROP)\b/i)) {
            // 直接展示 SQL，不使用折叠
            sqlHtml = `<div class="sql-display"><strong>生成的 SQL：</strong><pre><code>${escapeHtml(sql)}</code></pre></div>`;
            // 从工具结果中移除 SQL 部分，避免重复显示
            resultWithoutSql = resultContent.replace(sqlMatch[0], "").trim();
          }
        }
      }

      // 如果有 nl2sql 属性(兼容旧格式)
      if (call.nl2sql) {
        const steps = call.nl2sql.steps || [];
        const stepHtml = steps.length
          ? `<div class="nl2sql-steps">${steps
              .map(
                (step) =>
                  `<div class="nl2sql-step"><span>${escapeHtml(step.name)}</span><strong>${escapeHtml(
                    step.status
                  )}</strong><em>${escapeHtml(step.detail || "")}</em></div>`
              )
              .join("")}</div>`
          : "";
        if (call.nl2sql.sql) {
          sqlHtml = `<details open><summary>生成 SQL</summary><pre><code>${escapeHtml(call.nl2sql.sql)}</code></pre></details>`;
        }
        const assumptions = call.nl2sql.assumptions || [];
        const assumptionHtml = assumptions.length
          ? `<details><summary>假设与限制</summary><ul>${assumptions
              .map((item) => `<li>${escapeHtml(item)}</li>`)
              .join("")}</ul></details>`
          : "";
        return `${base}${stepHtml}${sqlHtml}${assumptionHtml}`;
      }

      // 显示工具结果(如果有，且移除了 SQL 部分)
      let resultHtml = "";
      if (resultWithoutSql) {
        // 截取前 500 字符,避免太长
        const resultPreview = resultWithoutSql.length > 500 ? resultWithoutSql.substring(0, 500) + "..." : resultWithoutSql;
        resultHtml = `<details><summary>工具结果</summary><pre><code>${escapeHtml(resultPreview)}</code></pre></details>`;
      }

      return `${base}${sqlHtml}${resultHtml}`;
    })
    .join("");
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

  item.innerHTML = `<strong>${escapeHtml(step)}</strong><span>${escapeHtml(status)}</span>`;
  item.className = `step ${status}`;
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

  appendMessage("user", message);
  messageInput.value = "";
  runSteps.innerHTML = "";
  sendBtn.disabled = true;
  confirmBtn.disabled = true;
  setBadge("运行中", "busy");

  let finalPayload = null;
  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sessionId, user_id: getUserId(), message }),
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
          addStep(event.step, {status: event.status});
        }
        if (event.type === "sql") {
          console.log('[SQL Event]', event.sql);
          updateLatestSql(event.sql);
        }
        if (event.type === "final") finalPayload = event;
      });
    }
    if (finalPayload) {
      // 渲染执行摘要
      const stats = finalPayload.stats || {};
      const toolCount = (finalPayload.tool_calls || []).length;
      const durationMs = stats.duration_ms || 0;
      const durationSec = durationMs ? (durationMs / 1000).toFixed(1) + "s" : "N/A";
      const tokens = stats.tokens ? stats.tokens + " tokens" : "";
      runSteps.innerHTML = `<div class="step completed"><strong>${toolCount} tools</strong><span>${tokens} | ${durationSec}</span></div>`;

      appendMessage("assistant", finalPayload.reply || "没有返回内容。", finalPayload.tool_calls || []);
      updateLatestSql(
        finalPayload.latest_sql || latestSqlFromToolCalls(finalPayload.tool_calls) || sqlFromReply(finalPayload.reply)
      );
      setBadge(finalPayload.needs_confirmation ? "等待确认" : "就绪", finalPayload.needs_confirmation ? "busy" : "");
      setConfirmationMode(Boolean(finalPayload.needs_confirmation));
    } else {
      throw new Error("没有收到 final 事件");
    }
  } catch (error) {
    runSteps.innerHTML = `<div class="step error"><strong>请求失败</strong><span>${escapeHtml(error.message)}</span></div>`;
    appendMessage("assistant", `请求失败：${error.message}`);
    setBadge("请求失败", "error");
    setConfirmationMode(false);
  } finally {
    refreshSession();
  }
}

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
