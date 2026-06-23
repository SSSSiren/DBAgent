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
  article.append(avatar, bubble);
  messages.appendChild(article);
  messages.scrollTop = messages.scrollHeight;
}

function renderToolCalls(toolCalls) {
  return toolCalls
    .map((call) => {
      const base = `<div class="tool-title">工具调用：${escapeHtml(call.tool)}(${escapeHtml(call.status)})</div>`;
      if (!call.nl2sql) return base;
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
      const sqlHtml = call.nl2sql.sql
        ? `<details open><summary>生成 SQL</summary><pre><code>${escapeHtml(call.nl2sql.sql)}</code></pre></details>`
        : "";
      const assumptions = call.nl2sql.assumptions || [];
      const assumptionHtml = assumptions.length
        ? `<details><summary>假设与限制</summary><ul>${assumptions
            .map((item) => `<li>${escapeHtml(item)}</li>`)
            .join("")}</ul></details>`
        : "";
      return `${base}${stepHtml}${sqlHtml}${assumptionHtml}`;
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
    await navigator.clipboard.writeText(sql);
    copySqlStatus.textContent = "已复制";
  } catch {
    latestSql.focus();
    latestSql.select();
    copySqlStatus.textContent = "请按 Ctrl/Cmd+C";
  }
  window.setTimeout(() => {
    copySqlStatus.textContent = "";
  }, 1800);
}

function addStep(step, state) {
  const item = document.createElement("div");
  item.className = "step";
  const status = state?.current_step || "running";
  item.innerHTML = `<strong>${escapeHtml(step)}</strong><span>${escapeHtml(status)}</span>`;
  runSteps.appendChild(item);
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
      : "未选择数据库";
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
        if (event.type === "step") addStep(event.step, event.state);
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
