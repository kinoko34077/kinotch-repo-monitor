const STATUS_LABELS = {
  ACTIVE: "編集中",
  IDLE: "一時停止",
  STALE: "停止中",
  COMMITTED: "Commit済",
  CLEAN: "待機",
  ERROR: "エラー",
};

const DEVFLOW_STATUS_LABELS = {
  NEEDS_AUDIT: "監査待ち",
  AUDITED: "監査済",
  WORK_ORDER_READY: "作業準備",
  READY_FOR_IMPLEMENTATION: "実装待ち",
  IMPLEMENTING: "実装中",
  AWAITING_REVIEW: "レビュー待ち",
  BLOCKED: "ブロック",
  NEEDS_REAUDIT: "再監査",
  PARKED: "保留",
  DONE: "完了",
};

const ui = {
  grid: document.getElementById("repo-grid"),
  status: document.getElementById("status-line"),
  count: document.getElementById("visible-count"),
  empty: document.getElementById("empty-state"),
  refresh: document.getElementById("refresh-button"),
  rediscover: document.getElementById("rediscover-button"),
  addButton: document.getElementById("repo-add-button"),
  addDialog: document.getElementById("repo-add-dialog"),
  addForm: document.getElementById("repo-add-form"),
  addPath: document.getElementById("repo-path-input"),
  addError: document.getElementById("repo-add-error"),
  addClose: document.getElementById("repo-add-close"),
  addCancel: document.getElementById("repo-add-cancel"),
  search: document.getElementById("search-input"),
  filter: document.getElementById("status-filter"),
  dialog: document.getElementById("chat-dialog"),
  dialogTitle: document.getElementById("chat-dialog-title"),
  dialogError: document.getElementById("chat-dialog-error"),
  chatForm: document.getElementById("chat-form"),
  chatInput: document.getElementById("chat-url-input"),
  chatClear: document.getElementById("chat-clear"),
  chatClose: document.getElementById("chat-close"),
};

let currentState = { refresh_ms: 2000, repositories: [] };
let editingRepo = null;
let refreshTimer = null;
let refreshing = false;
const expandedWorkflows = new Set();

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function formatAge(seconds) {
  if (seconds === null || seconds === undefined) return "--";
  if (seconds < 60) return `${Math.floor(seconds)}秒前`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}分前`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}時間前`;
  if (seconds < 86400 * 30) return `${Math.floor(seconds / 86400)}日前`;
  if (seconds < 86400 * 365) return `${Math.floor(seconds / (86400 * 30))}か月前`;
  return `${Math.floor(seconds / (86400 * 365))}年前`;
}

function syncText(repo) {
  if (!repo.upstream) return "upstreamなし";
  return `↑${repo.ahead} ↓${repo.behind}`;
}

function shortText(value, limit = 72) {
  const text = String(value || "--").replace(/\s+/g, " ").trim();
  return text.length > limit ? `${text.slice(0, limit - 1)}…` : text;
}

function safeWebUrl(value) {
  if (!value) return null;
  try {
    const parsed = new URL(value);
    return parsed.protocol === "https:" || parsed.protocol === "http:" ? parsed.href : null;
  } catch {
    return null;
  }
}

async function api(path, options = {}) {
  const request = { ...options, headers: { ...(options.headers || {}) } };
  if (request.body && typeof request.body !== "string") {
    request.headers["Content-Type"] = "application/json";
    request.body = JSON.stringify(request.body);
  }
  const response = await fetch(path, request);
  let payload = {};
  try {
    payload = await response.json();
  } catch {
    payload = {};
  }
  if (!response.ok) throw new Error(payload.error || `HTTP ${response.status}`);
  return payload;
}

function filteredRepos() {
  const query = ui.search.value.trim().toLocaleLowerCase();
  const status = ui.filter.value;
  return currentState.repositories.filter((repo) => {
    const matchesStatus = status === "ALL" || repo.status === status;
    const workflow = repo.devflow || {};
    const haystack = `${repo.name} ${repo.branch} ${repo.path} ${repo.remote_web_url || ""} ${workflow.work_status || ""} ${workflow.repository_state || ""} ${workflow.active_work || ""} ${workflow.next_action || ""}`.toLocaleLowerCase();
    return matchesStatus && (!query || haystack.includes(query));
  });
}

function actionButton(label, className, handler) {
  const button = element("button", `button ${className || ""}`, label);
  button.type = "button";
  button.addEventListener("click", (event) => {
    event.stopPropagation();
    handler();
  });
  return button;
}

function actionLink(label, className, url) {
  const link = element("a", `button ${className || ""}`, label);
  link.href = url;
  link.target = "_blank";
  link.rel = "noopener noreferrer";
  link.addEventListener("click", (event) => event.stopPropagation());
  return link;
}

function openChatDialog(repo) {
  editingRepo = repo;
  ui.dialogTitle.textContent = `${repo.name} のChat URL`;
  ui.chatInput.value = repo.chat_url || "";
  ui.dialogError.textContent = "";
  ui.dialog.showModal();
  window.setTimeout(() => ui.chatInput.focus(), 0);
}

function openAddDialog() {
  ui.addPath.value = "";
  ui.addError.textContent = "";
  ui.addDialog.showModal();
  window.setTimeout(() => ui.addPath.focus(), 0);
}

function openChat(repo) {
  const url = safeWebUrl(repo.chat_url);
  if (!url) return openChatDialog(repo);
  window.open(url, "_blank", "noopener,noreferrer");
}

async function repoAction(repo, action, body = {}) {
  const key = encodeURIComponent(repo.key);
  return api(`/api/repos/${key}/${action}`, { method: "POST", body });
}

function renderDevflow(repo) {
  if (!repo.devflow) return null;
  const workflow = repo.devflow;
  const block = element("details", "workflow-summary");
  block.open = expandedWorkflows.has(repo.key);
  block.addEventListener("click", (event) => event.stopPropagation());
  block.addEventListener("toggle", () => {
    if (block.open) expandedWorkflows.add(repo.key);
    else expandedWorkflows.delete(repo.key);
  });

  const header = element("summary", "workflow-heading");
  const badge = element(
    "span",
    "workflow-badge",
    DEVFLOW_STATUS_LABELS[workflow.work_status] || workflow.work_status || "devflow",
  );
  badge.dataset.workStatus = workflow.work_status || "UNKNOWN";
  const preview = element("span", "workflow-next-preview", shortText(workflow.next_action));
  preview.title = workflow.next_action || "";
  header.append(badge, preview, element("span", "workflow-toggle", "詳細"));
  block.append(header);

  const body = element("div", "workflow-details");
  const details = element("dl", "workflow-meta");
  const rows = [
    ["repo", workflow.repository_state || "--"],
    ["作業", workflow.active_work || "--"],
    ["次", workflow.next_action || "--"],
  ];
  for (const [label, value] of rows) {
    details.append(element("dt", "", label), element("dd", "", value));
  }
  body.append(details);

  const issueUrl = safeWebUrl(workflow.issue_url);
  if (issueUrl) {
    const issue = element("a", "workflow-link", `devflow #${workflow.issue_number || "?"}`);
    issue.href = issueUrl;
    issue.target = "_blank";
    issue.rel = "noopener noreferrer";
    issue.title = "devflow Control Issueを開く";
    body.append(issue);
  }
  block.append(body);
  return block;
}

function renderCard(repo) {
  const card = element("article", "repo-card");
  card.dataset.status = repo.status;
  card.addEventListener("click", () => openChat(repo));

  const heading = element("div", "card-heading");
  const name = element("h2", "repo-name", repo.name);
  name.title = repo.path;
  const badges = element("div", "card-badges");
  badges.append(element("span", "state-badge", STATUS_LABELS[repo.status] || repo.status));
  heading.append(name, badges);
  card.append(heading);

  const meta = element("dl", "repo-meta");
  const rows = [
    ["branch", `${repo.branch || "?"}  ${repo.head || "?"}`],
    ["変更", `${repo.changed_count ?? 0}`],
    ["活動", formatAge(repo.activity_age_seconds)],
    ["sync", syncText(repo)],
  ];
  for (const [label, value] of rows) meta.append(element("dt", "", label), element("dd", "", value));
  card.append(meta);

  const workflow = renderDevflow(repo);
  if (workflow) card.append(workflow);

  if (repo.error) card.append(element("p", "repo-error", repo.error));
  const path = element("p", "repo-path", repo.path);
  path.title = repo.path;
  card.append(path);

  const actions = element("div", "card-actions");
  const chatLabel = repo.has_chat ? "Chatを開く" : "Chat登録";
  actions.append(actionButton(chatLabel, "chat-open button-primary", () => openChat(repo)));

  const repoUrl = safeWebUrl(repo.remote_web_url);
  if (repoUrl) actions.append(actionLink("Repo", "repo-open button-secondary", repoUrl));

  actions.append(
    actionButton("URL編集", "button-secondary", () => openChatDialog(repo)),
    actionButton("フォルダ", "button-secondary", async () => {
      try {
        await repoAction(repo, "open-folder");
        setStatus(`${repo.name} のフォルダを開きました`);
      } catch (error) {
        setStatus(`フォルダを開けません: ${error.message}`, true);
      }
    }),
    actionButton("解除", "button-secondary", async () => {
      if (!window.confirm(`${repo.name} を一覧から解除しますか？ 再検出で復帰します。`)) return;
      try {
        await repoAction(repo, "remove");
        await refreshState({ quiet: true });
      } catch (error) {
        setStatus(`登録解除に失敗: ${error.message}`, true);
      }
    }),
  );
  card.append(actions);
  return card;
}

function render() {
  ui.grid.replaceChildren();
  const repos = filteredRepos();
  for (const repo of repos) ui.grid.append(renderCard(repo));
  ui.count.textContent = `${repos.length} / ${currentState.repositories.length} repos`;
  ui.empty.hidden = repos.length !== 0;
}

function setStatus(message, isError = false) {
  ui.status.textContent = message;
  ui.status.dataset.error = isError ? "true" : "false";
}

function scheduleRefresh() {
  window.clearTimeout(refreshTimer);
  const base = Math.max(500, Number(currentState.refresh_ms) || 2000);
  const delay = document.hidden ? Math.max(base, 5000) : base;
  refreshTimer = window.setTimeout(() => refreshState({ quiet: true }), delay);
}

function refreshStatusText() {
  const updated = new Date((currentState.updated_at || Date.now() / 1000) * 1000);
  let text = `最終更新 ${updated.toLocaleTimeString()} / ${currentState.repositories.length} repos`;
  if (currentState.devflow?.stale) text += " / devflow取得失敗（前回値を表示）";
  return text;
}

async function refreshState({ quiet = false } = {}) {
  if (refreshing) return;
  refreshing = true;
  if (!quiet) setStatus("更新中…");
  try {
    currentState = await api("/api/state");
    render();
    setStatus(refreshStatusText(), Boolean(currentState.devflow?.error && !currentState.devflow?.fetched_at));
  } catch (error) {
    setStatus(`更新失敗: ${error.message}`, true);
  } finally {
    refreshing = false;
    scheduleRefresh();
  }
}

ui.refresh.addEventListener("click", () => refreshState());
ui.rediscover.addEventListener("click", async () => {
  try {
    setStatus("repoを再検出中…");
    currentState = await api("/api/rediscover", { method: "POST", body: {} });
    render();
    setStatus(`再検出完了 / ${currentState.repositories.length} repos`);
  } catch (error) {
    setStatus(`再検出失敗: ${error.message}`, true);
  } finally {
    scheduleRefresh();
  }
});
ui.addButton.addEventListener("click", openAddDialog);
ui.addClose.addEventListener("click", () => ui.addDialog.close());
ui.addCancel.addEventListener("click", () => ui.addDialog.close());
ui.addForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const path = ui.addPath.value.trim();
  if (!path) {
    ui.addError.textContent = "repoの絶対パスを入力してください。";
    return;
  }
  ui.addError.textContent = "";
  try {
    const added = await api("/api/repos/add", { method: "POST", body: { path } });
    ui.addDialog.close();
    await refreshState({ quiet: true });
    setStatus(`${added.name} を追加しました`);
  } catch (error) {
    ui.addError.textContent = error.message;
  }
});
ui.search.addEventListener("input", render);
ui.filter.addEventListener("change", render);
document.addEventListener("visibilitychange", scheduleRefresh);

ui.chatClose.addEventListener("click", () => ui.dialog.close());
ui.chatClear.addEventListener("click", async () => {
  if (!editingRepo) return;
  try {
    await repoAction(editingRepo, "chat-url", { chat_url: "" });
    ui.dialog.close();
    await refreshState({ quiet: true });
  } catch (error) {
    ui.dialogError.textContent = error.message;
  }
});
ui.chatForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!editingRepo) return;
  const value = ui.chatInput.value.trim();
  if (value && !safeWebUrl(value)) {
    ui.dialogError.textContent = "http:// または https:// のURLを入力してください。";
    return;
  }
  try {
    await repoAction(editingRepo, "chat-url", { chat_url: value });
    ui.dialog.close();
    await refreshState({ quiet: true });
  } catch (error) {
    ui.dialogError.textContent = error.message;
  }
});

refreshState();
