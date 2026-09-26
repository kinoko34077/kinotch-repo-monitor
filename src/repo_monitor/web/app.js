const STATUS_LABELS = {
  ACTIVE: "編集中",
  IDLE: "一時停止",
  STALE: "停止中",
  COMMITTED: "Commit済",
  CLEAN: "待機",
  PENDING: "確認中",
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

let currentState = { refresh_ms: 2000, scan: {}, repositories: [] };
let editingRepoKey = null;
let dialogOpener = null;
let refreshTimer = null;
let refreshing = false;
const expandedWorkflows = new Set();
const cardViews = new Map();

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function setText(node, value) {
  const text = String(value ?? "");
  if (node.textContent !== text) node.textContent = text;
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

function repoByKey(repoKey) {
  return currentState.repositories.find((repo) => repo.key === repoKey) || null;
}

function repoMatches(repo) {
  const query = ui.search.value.trim().toLocaleLowerCase();
  const status = ui.filter.value;
  const matchesStatus = status === "ALL" || repo.status === status;
  const workflow = repo.devflow || {};
  const haystack = `${repo.name} ${repo.branch} ${repo.path} ${repo.remote_web_url || ""} ${workflow.work_status || ""} ${workflow.repository_state || ""} ${workflow.active_work || ""} ${workflow.next_action || ""}`.toLocaleLowerCase();
  return matchesStatus && (!query || haystack.includes(query));
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

function actionLink(label, className) {
  const link = element("a", `button ${className || ""}`, label);
  link.target = "_blank";
  link.rel = "noopener noreferrer";
  link.addEventListener("click", (event) => event.stopPropagation());
  return link;
}

function restoreDialogFocus() {
  const opener = dialogOpener;
  dialogOpener = null;
  if (!opener) return;
  const view = cardViews.get(opener.repoKey);
  const target = view?.actions?.[opener.action];
  if (target && !view.card.hidden && !target.hidden && target.isConnected) {
    target.focus();
    return;
  }
  ui.search.focus();
}

function openChatDialog(repo, action = "chat-edit") {
  editingRepoKey = repo.key;
  dialogOpener = { repoKey: repo.key, action };
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

function openChat(repo, action = "chat") {
  const url = safeWebUrl(repo.chat_url);
  if (!url) return openChatDialog(repo, action);
  window.open(url, "_blank", "noopener,noreferrer");
}

async function repoAction(repo, action, body = {}) {
  const key = encodeURIComponent(repo.key);
  return api(`/api/repos/${key}/${action}`, { method: "POST", body });
}

function ensureCardView(repo) {
  const existing = cardViews.get(repo.key);
  if (existing) return existing;

  const view = { repo, actions: {} };
  const card = element("article", "repo-card");
  view.card = card;
  card.dataset.repoKey = repo.key;
  card.addEventListener("click", () => openChat(view.repo));

  const heading = element("div", "card-heading");
  view.name = element("h2", "repo-name");
  const badges = element("div", "card-badges");
  view.stateBadge = element("span", "state-badge");
  badges.append(view.stateBadge);
  heading.append(view.name, badges);
  card.append(heading);

  const meta = element("dl", "repo-meta");
  const addMeta = (label) => {
    const value = element("dd", "");
    meta.append(element("dt", "", label), value);
    return value;
  };
  view.branch = addMeta("branch");
  view.changed = addMeta("変更");
  view.activity = addMeta("活動");
  view.sync = addMeta("sync");
  card.append(meta);

  const block = element("details", "workflow-summary");
  view.workflow = block;
  block.hidden = true;
  block.open = expandedWorkflows.has(repo.key);
  block.addEventListener("click", (event) => event.stopPropagation());
  block.addEventListener("toggle", () => {
    if (block.open) expandedWorkflows.add(repo.key);
    else expandedWorkflows.delete(repo.key);
  });
  const workflowHeader = element("summary", "workflow-heading");
  view.workflowBadge = element("span", "workflow-badge");
  view.workflowPreview = element("span", "workflow-next-preview");
  workflowHeader.append(view.workflowBadge, view.workflowPreview, element("span", "workflow-toggle", "詳細"));
  block.append(workflowHeader);
  const workflowBody = element("div", "workflow-details");
  const workflowMeta = element("dl", "workflow-meta");
  const addWorkflowMeta = (label) => {
    const value = element("dd", "");
    workflowMeta.append(element("dt", "", label), value);
    return value;
  };
  view.workflowRepo = addWorkflowMeta("repo");
  view.workflowWork = addWorkflowMeta("作業");
  view.workflowNext = addWorkflowMeta("次");
  workflowBody.append(workflowMeta);
  view.workflowLink = element("a", "workflow-link");
  view.workflowLink.target = "_blank";
  view.workflowLink.rel = "noopener noreferrer";
  view.workflowLink.title = "devflow Control Issueを開く";
  workflowBody.append(view.workflowLink);
  block.append(workflowBody);
  card.append(block);

  view.error = element("p", "repo-error");
  view.error.hidden = true;
  card.append(view.error);
  view.path = element("p", "repo-path");
  card.append(view.path);

  const actions = element("div", "card-actions");
  view.actions.chat = actionButton("Chat登録", "chat-open button-primary", () => openChat(view.repo, "chat"));
  view.actions.repo = actionLink("Repo", "repo-open button-secondary");
  view.actions.edit = actionButton("URL編集", "button-secondary", () => openChatDialog(view.repo, "edit"));
  view.actions.folder = actionButton("フォルダ", "button-secondary", async () => {
    try {
      await repoAction(view.repo, "open-folder");
      setStatus(`${view.repo.name} のフォルダを開きました`);
    } catch (error) {
      setStatus(`フォルダを開けません: ${error.message}`, true);
    }
  });
  view.actions.remove = actionButton("解除", "button-secondary", async () => {
    if (!window.confirm(`${view.repo.name} を一覧から解除しますか？ 再検出で復帰します。`)) return;
    try {
      await repoAction(view.repo, "remove");
      await refreshState({ quiet: true });
    } catch (error) {
      setStatus(`登録解除に失敗: ${error.message}`, true);
    }
  });
  actions.append(
    view.actions.chat,
    view.actions.repo,
    view.actions.edit,
    view.actions.folder,
    view.actions.remove,
  );
  card.append(actions);

  cardViews.set(repo.key, view);
  return view;
}

function updateCardView(view, repo) {
  view.repo = repo;
  view.card.dataset.status = repo.status;
  setText(view.name, repo.name);
  view.name.title = repo.path;
  setText(view.stateBadge, STATUS_LABELS[repo.status] || repo.status);
  setText(view.branch, `${repo.branch || "?"}  ${repo.head || "?"}`);
  setText(view.changed, `${repo.changed_count ?? 0}`);
  setText(view.activity, formatAge(repo.activity_age_seconds));
  setText(view.sync, syncText(repo));

  const workflow = repo.devflow;
  view.workflow.hidden = !workflow;
  if (workflow) {
    setText(view.workflowBadge, DEVFLOW_STATUS_LABELS[workflow.work_status] || workflow.work_status || "devflow");
    view.workflowBadge.dataset.workStatus = workflow.work_status || "UNKNOWN";
    setText(view.workflowPreview, shortText(workflow.next_action));
    view.workflowPreview.title = workflow.next_action || "";
    setText(view.workflowRepo, workflow.repository_state || "--");
    setText(view.workflowWork, workflow.active_work || "--");
    setText(view.workflowNext, workflow.next_action || "--");
    const issueUrl = safeWebUrl(workflow.issue_url);
    view.workflowLink.hidden = !issueUrl;
    if (issueUrl) {
      view.workflowLink.href = issueUrl;
      setText(view.workflowLink, `devflow #${workflow.issue_number || "?"}`);
    }
  }

  view.error.hidden = !repo.error;
  if (repo.error) setText(view.error, repo.error);
  setText(view.path, repo.path);
  view.path.title = repo.path;

  setText(view.actions.chat, repo.has_chat ? "Chatを開く" : "Chat登録");
  const repoUrl = safeWebUrl(repo.remote_web_url);
  view.actions.repo.hidden = !repoUrl;
  if (repoUrl) view.actions.repo.href = repoUrl;
}

function reconcileCards() {
  const liveKeys = new Set(currentState.repositories.map((repo) => repo.key));
  for (const [key, view] of cardViews) {
    if (liveKeys.has(key)) continue;
    if (view.card.contains(document.activeElement)) ui.search.focus();
    view.card.remove();
    cardViews.delete(key);
    expandedWorkflows.delete(key);
  }

  let cursor = ui.grid.firstElementChild;
  let visible = 0;
  for (const repo of currentState.repositories) {
    const view = cardViews.get(repo.key) || ensureCardView(repo);
    updateCardView(view, repo);
    if (view.card !== cursor) ui.grid.insertBefore(view.card, cursor);
    cursor = view.card.nextElementSibling;

    const shouldHide = !repoMatches(repo);
    if (shouldHide && view.card.contains(document.activeElement)) ui.search.focus();
    view.card.hidden = shouldHide;
    if (!shouldHide) visible += 1;
  }

  ui.count.textContent = `${visible} / ${currentState.repositories.length} repos`;
  ui.empty.hidden = visible !== 0;
}

function render() {
  reconcileCards();
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
  if (currentState.scan?.in_progress) text += " / スキャン中";
  if (currentState.scan?.error) text += ` / scan: ${currentState.scan.error}`;
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
    setStatus(
      refreshStatusText(),
      Boolean(currentState.scan?.error || (currentState.devflow?.error && !currentState.devflow?.fetched_at)),
    );
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

ui.dialog.addEventListener("close", restoreDialogFocus);
ui.chatClose.addEventListener("click", () => ui.dialog.close());
ui.chatClear.addEventListener("click", async () => {
  const repo = repoByKey(editingRepoKey);
  if (!repo) return;
  try {
    await repoAction(repo, "chat-url", { chat_url: "" });
    ui.dialog.close();
    await refreshState({ quiet: true });
  } catch (error) {
    ui.dialogError.textContent = error.message;
  }
});
ui.chatForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const repo = repoByKey(editingRepoKey);
  if (!repo) return;
  const value = ui.chatInput.value.trim();
  if (value && !safeWebUrl(value)) {
    ui.dialogError.textContent = "http:// または https:// のURLを入力してください。";
    return;
  }
  try {
    await repoAction(repo, "chat-url", { chat_url: value });
    ui.dialog.close();
    await refreshState({ quiet: true });
  } catch (error) {
    ui.dialogError.textContent = error.message;
  }
});

refreshState();
