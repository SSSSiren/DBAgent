const sessionInput = document.querySelector("#sessionId");
const newSessionBtn = document.querySelector("#newSessionBtn");
const sessionStatus = document.querySelector("#sessionStatus");
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

const storageKey = "dbagent.sessionId";

function makeSessionId() {
  return `session-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
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

function initSession() {
  const existing = localStorage.getItem(storageKey);
  sessionInput.value = existing || makeSessionId();
  localStorage.setItem(storageKey, sessionInput.value);
  refreshSession();
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

async function refreshSession() {
  const id = sessionInput.value.trim();
  if (!id) return;
  localStorage.setItem(storageKey, id);
  try {
    const response = await fetch(`/api/sessions/${encodeURIComponent(id)}`);
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
  const sessionId = sessionInput.value.trim();
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
      body: JSON.stringify({ session_id: sessionId, message }),
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

newSessionBtn.addEventListener("click", () => {
  sessionInput.value = makeSessionId();
  localStorage.setItem(storageKey, sessionInput.value);
  messages.querySelectorAll(".message:not(:first-child)").forEach((node) => node.remove());
  runSteps.innerHTML = "";
  latestSql.value = "";
  copySqlBtn.disabled = true;
  copySqlStatus.textContent = "";
  setConfirmationMode(false);
  refreshSession();
});

sessionInput.addEventListener("change", refreshSession);

document.querySelectorAll("[data-prompt]").forEach((button) => {
  button.addEventListener("click", () => {
    messageInput.value = button.dataset.prompt || "";
    messageInput.focus();
  });
});

initSession();
