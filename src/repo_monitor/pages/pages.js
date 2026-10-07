const QUERY_KEYS = Object.freeze({
  q: "q",
  work: "work",
  state: "state",
  audit: "audit",
  sort: "sort",
});

const DEFAULT_SORT = "updated-desc";
const SORT_VALUES = new Set(["updated-desc", "updated-asc", "repo-asc", "repo-desc"]);

const state = {
  payload: null,
  query: "",
  workStatus: "",
  repositoryState: "",
  auditFreshness: "",
  sortOrder: DEFAULT_SORT,
  selectedRepository: "",
  lastFocus: null,
  loadError: "",
};

const DISPOSITION_LABELS = {
  READY: "実装待ち",
  IMPLEMENTING: "実装中",
  NEEDS_HUMAN: "人間対応",
  WAIT_EXTERNAL: "外部待ち",
  NEEDS_EVIDENCE: "証拠不足",
  NEEDS_REVIEWER: "レビュー必要",
  NEEDS_RECOVERY: "復旧可能",
};

const TRANSPORT_LABELS = {
  CURRENT: "最新",
  STALE: "期限切れ",
  INCOMPLETE: "不完全",
  INVALID: "無効",
  UNAVAILABLE: "取得不能",
  UNKNOWN: "不明",
};

const ui = {
  sourceStatus: document.getElementById("source-status"),
  generatedAt: document.getElementById("generated-at"),
  sourceBanner: document.getElementById("source-banner"),
  sourceBannerTitle: document.getElementById("source-banner-title"),
  sourceNote: document.getElementById("source-note"),
  retryLoad: document.getElementById("retry-load"),
  summaryStrip: document.getElementById("summary-strip"),
  search: document.getElementById("search"),
  workStatus: document.getElementById("work-status"),
  repositoryState: document.getElementById("repository-state"),
  auditFreshness: document.getElementById("audit-freshness"),
  sortOrder: document.getElementById("sort-order"),
  clearFilters: document.getElementById("clear-filters"),
  emptyClearFilters: document.getElementById("empty-clear-filters"),
  humanQueue: document.getElementById("human-queue"),
  humanQueueCount: document.getElementById("human-queue-count"),
  humanQueueWarning: document.getElementById("human-queue-warning"),
  humanQueueList: document.getElementById("human-queue-list"),
  repositoryTbody: document.getElementById("repository-tbody"),
  repositoryMobileList: document.getElementById("repository-mobile-list"),
  repositoryCount: document.getElementById("repository-count"),
  repositoryEmpty: document.getElementById("repository-empty"),
  repositoryInspector: document.getElementById("repository-inspector"),
  inspectorTitle: document.getElementById("inspector-title"),
  inspectorClose: document.getElementById("inspector-close"),
  inspectorContent: document.getElementById("inspector-content"),
  appStatus: document.getElementById("app-status"),
};

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = String(text);
  return node;
}

function safeUrl(value, prefix) {
  if (typeof value !== "string") return null;
  try {
    const parsed = new URL(value);
    if (parsed.protocol !== "https:") return null;
    if (parsed.hostname !== "github.com") return null;
    if (prefix && !parsed.pathname.startsWith(prefix)) return null;
    return parsed.toString();
  } catch {
    return null;
  }
}

function formatTime(value) {
  if (!value) return "--";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return new Intl.DateTimeFormat("ja-JP", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    timeZoneName: "short",
  }).format(date);
}

function formatShortTime(value) {
  if (!value) return "--";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return new Intl.DateTimeFormat("ja-JP", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function normalize(value) {
  return String(value || "").toLocaleLowerCase();
}

function repoKey(repo) {
  return String(repo.repository_full_name || repo.repository || "");
}

function humanQueueEntryCount(payload = state.payload) {
  const portfolios = payload && Array.isArray(payload.human_portfolios)
    ? payload.human_portfolios
    : [];
  return portfolios.reduce(
    (count, portfolio) => count + (Array.isArray(portfolio.entries) ? portfolio.entries.length : 0),
    0,
  );
}

function nonCurrentPortfolioCount(payload = state.payload) {
  const portfolios = payload && Array.isArray(payload.human_portfolios)
    ? payload.human_portfolios
    : [];
  return portfolios.filter((portfolio) => portfolio.transport_status !== "CURRENT").length;
}

function portfolioForRepository(repository) {
  const portfolios = state.payload && Array.isArray(state.payload.human_portfolios)
    ? state.payload.human_portfolios
    : [];
  return portfolios.find((portfolio) => portfolio.repository === repository) || null;
}

function readLocationState() {
  const params = new URLSearchParams(window.location.search);
  state.query = params.get(QUERY_KEYS.q) || "";
  state.workStatus = params.get(QUERY_KEYS.work) || "";
  state.repositoryState = params.get(QUERY_KEYS.state) || "";
  state.auditFreshness = params.get(QUERY_KEYS.audit) || "";
  const requestedSort = params.get(QUERY_KEYS.sort) || DEFAULT_SORT;
  state.sortOrder = SORT_VALUES.has(requestedSort) ? requestedSort : DEFAULT_SORT;

  const rawHash = window.location.hash.startsWith("#repo=")
    ? window.location.hash.slice("#repo=".length)
    : "";
  try {
    state.selectedRepository = rawHash ? decodeURIComponent(rawHash) : "";
  } catch {
    state.selectedRepository = "";
  }
}

function writeLocationState() {
  const url = new URL(window.location.href);
  const params = url.searchParams;
  const entries = [
    [QUERY_KEYS.q, state.query],
    [QUERY_KEYS.work, state.workStatus],
    [QUERY_KEYS.state, state.repositoryState],
    [QUERY_KEYS.audit, state.auditFreshness],
    [QUERY_KEYS.sort, state.sortOrder === DEFAULT_SORT ? "" : state.sortOrder],
  ];
  for (const [key, value] of entries) {
    if (value) params.set(key, value);
    else params.delete(key);
  }
  url.hash = state.selectedRepository
    ? "repo=" + encodeURIComponent(state.selectedRepository)
    : "";
  history.replaceState(null, "", url);
}

function populateSelect(select, values, selected) {
  select.replaceChildren();
  const all = element("option", "", "すべて");
  all.value = "";
  select.append(all);
  for (const value of values) {
    const option = element("option", "", value);
    option.value = value;
    select.append(option);
  }
  select.value = values.includes(selected) ? selected : "";
  return select.value;
}

function populateFilters() {
  const repos = state.payload && Array.isArray(state.payload.repositories)
    ? state.payload.repositories
    : [];
  const unique = (field) => [...new Set(
    repos.map((repo) => String(repo[field] || "")).filter(Boolean),
  )].sort((a, b) => a.localeCompare(b));

  state.workStatus = populateSelect(ui.workStatus, unique("work_status"), state.workStatus);
  state.repositoryState = populateSelect(
    ui.repositoryState,
    unique("repository_state"),
    state.repositoryState,
  );
  state.auditFreshness = populateSelect(
    ui.auditFreshness,
    unique("audit_freshness"),
    state.auditFreshness,
  );

  ui.search.value = state.query;
  ui.sortOrder.value = SORT_VALUES.has(state.sortOrder) ? state.sortOrder : DEFAULT_SORT;
  state.sortOrder = ui.sortOrder.value;
}

function renderSource() {
  const payload = state.payload;
  const source = payload && payload.source ? payload.source : {};

  if (state.loadError) {
    ui.sourceStatus.textContent = "読込失敗";
    ui.sourceStatus.className = "status-badge status-error";
    ui.generatedAt.textContent = "生成 --";
    ui.sourceBanner.hidden = false;
    ui.sourceBannerTitle.textContent = "Snapshotを読み込めません";
    ui.sourceNote.textContent = state.loadError;
    return;
  }

  ui.generatedAt.textContent = "生成 " + formatTime(payload ? payload.generated_at : null);
  if (source.error) {
    ui.sourceStatus.textContent = "取得エラー";
    ui.sourceStatus.className = "status-badge status-error";
    ui.sourceBanner.hidden = false;
    ui.sourceBannerTitle.textContent = "devflow source error";
    ui.sourceNote.textContent = String(source.error);
    return;
  }

  if (source.stale) {
    ui.sourceStatus.textContent = "STALE";
    ui.sourceStatus.className = "status-badge status-warn";
    ui.sourceBanner.hidden = false;
    ui.sourceBannerTitle.textContent = "Snapshotがstaleです";
    ui.sourceNote.textContent = "このsnapshotを現在値として扱わないでください。取得 " + formatTime(source.fetched_at);
    return;
  }

  ui.sourceStatus.textContent = "CURRENT";
  ui.sourceStatus.className = "status-badge status-ok";
  ui.sourceBanner.hidden = true;
  ui.sourceBannerTitle.textContent = "";
  ui.sourceNote.textContent = "";
}

function workCounts(repos) {
  const counts = new Map();
  for (const repo of repos) {
    const value = String(repo.work_status || "--");
    counts.set(value, (counts.get(value) || 0) + 1);
  }
  return [...counts.entries()].sort((a, b) => a[0].localeCompare(b[0]));
}

function renderSummary() {
  const repos = state.payload && Array.isArray(state.payload.repositories)
    ? state.payload.repositories
    : [];
  ui.summaryStrip.replaceChildren();

  ui.summaryStrip.append(element("span", "summary-static", String(repos.length) + " repos"));

  for (const [status, count] of workCounts(repos)) {
    const button = element("button", "summary-button", status + " " + count);
    button.type = "button";
    button.dataset.workStatus = status;
    button.setAttribute("aria-pressed", String(state.workStatus === status));
    button.addEventListener("click", () => {
      state.workStatus = state.workStatus === status ? "" : status;
      ui.workStatus.value = state.workStatus;
      writeLocationState();
      renderSummary();
      renderRepositories();
      updateClearVisibility();
    });
    ui.summaryStrip.append(button);
  }

  ui.summaryStrip.append(
    element("span", "summary-static", "Human Queue " + humanQueueEntryCount()),
    element("span", "summary-static", "Audit non-current " + repos.filter(
      (repo) => repo.audit_freshness && repo.audit_freshness !== "CURRENT",
    ).length),
  );
}

function transportLabel(portfolio) {
  return TRANSPORT_LABELS[portfolio.transport_status]
    || portfolio.transport_status
    || "不明";
}

function renderHumanQueue() {
  const portfolios = state.payload && Array.isArray(state.payload.human_portfolios)
    ? state.payload.human_portfolios
    : [];
  const entries = [];
  for (const portfolio of portfolios) {
    for (const entry of Array.isArray(portfolio.entries) ? portfolio.entries : []) {
      entries.push({ portfolio, entry });
    }
  }

  const warningCount = nonCurrentPortfolioCount();
  ui.humanQueueCount.textContent = String(entries.length);
  ui.humanQueue.hidden = entries.length === 0 && warningCount === 0;
  ui.humanQueueList.replaceChildren();

  if (warningCount > 0) {
    ui.humanQueueWarning.hidden = false;
    ui.humanQueueWarning.textContent =
      warningCount + " repositoryのHuman Portfolio transportがCURRENTではありません。";
  } else {
    ui.humanQueueWarning.hidden = true;
    ui.humanQueueWarning.textContent = "";
  }

  for (const { portfolio, entry } of entries) {
    const row = element("div", "human-entry");
    const disposition = element(
      "span",
      "disposition-badge",
      DISPOSITION_LABELS[entry.disposition] || entry.disposition || "不明",
    );
    const repository = element("span", "", portfolio.repository || entry.repository || "--");
    const task = safeUrl(entry.entry_ref, "/kinoko34077/");
    let taskNode;
    if (task) {
      taskNode = element("a", "row-link", entry.task_ref || "--");
      taskNode.href = task;
      taskNode.target = "_blank";
      taskNode.rel = "noopener noreferrer";
    } else {
      taskNode = element("span", "", entry.task_ref || "--");
    }
    const meta = element(
      "span",
      "",
      [transportLabel(portfolio), entry.evidence_freshness, entry.evidence_trust]
        .filter(Boolean)
        .join(" · "),
    );
    row.append(disposition, repository, taskNode, meta);
    ui.humanQueueList.append(row);
  }
}

const VISIBLE_SEARCH_FIELDS = [
  ["Repository", (repo) => repo.repository_full_name || repo.repository],
  ["Work Status", (repo) => repo.work_status],
  ["Repository State", (repo) => repo.repository_state],
  ["Audit Freshness", (repo) => repo.audit_freshness],
  ["Next Action", (repo) => repo.next_action],
  ["Updated", (repo) => repo.updated_at],
];

const HIDDEN_SEARCH_FIELDS = [
  ["Active Work", (repo) => repo.active_work],
  ["Audit Scope", (repo) => repo.audit_scope],
  ["Audit Evidence", (repo) => repo.audit_evidence],
  ["Audit SHA", (repo) => repo.audit_sha],
  ["Audit Ref", (repo) => repo.audit_ref],
  ["Audit Depth", (repo) => repo.audit_depth],
  ["Last Audit", (repo) => repo.last_audit_at],
  ["Last Deep Audit", (repo) => repo.last_deep_audit_at],
];

function snippetForMatch(value, query) {
  const text = String(value || "").replace(/\s+/g, " ").trim();
  if (!text) return "";
  const folded = text.toLocaleLowerCase();
  const index = folded.indexOf(query);
  const start = Math.max(0, index - 28);
  const end = Math.min(text.length, Math.max(index + query.length + 70, start + 100));
  return (start > 0 ? "…" : "")
    + text.slice(start, end)
    + (end < text.length ? "…" : "");
}

function matchRepository(repo, query) {
  if (!query) return { matches: true, reason: "" };

  for (const [, read] of VISIBLE_SEARCH_FIELDS) {
    if (normalize(read(repo)).includes(query)) {
      return { matches: true, reason: "" };
    }
  }

  for (const [label, read] of HIDDEN_SEARCH_FIELDS) {
    const value = read(repo);
    if (normalize(value).includes(query)) {
      return {
        matches: true,
        reason: "一致: " + label + " — " + snippetForMatch(value, query),
      };
    }
  }

  return { matches: false, reason: "" };
}

function compareRepositories(a, b) {
  const leftName = repoKey(a);
  const rightName = repoKey(b);
  if (state.sortOrder === "repo-asc") return leftName.localeCompare(rightName);
  if (state.sortOrder === "repo-desc") return rightName.localeCompare(leftName);

  const leftTime = Date.parse(a.updated_at || "") || 0;
  const rightTime = Date.parse(b.updated_at || "") || 0;
  if (state.sortOrder === "updated-asc") {
    return leftTime - rightTime || leftName.localeCompare(rightName);
  }
  return rightTime - leftTime || leftName.localeCompare(rightName);
}

function filteredRepositories() {
  const repos = state.payload && Array.isArray(state.payload.repositories)
    ? state.payload.repositories
    : [];
  const query = state.query.trim().toLocaleLowerCase();

  return repos
    .filter((repo) => {
      if (state.workStatus && repo.work_status !== state.workStatus) return false;
      if (state.repositoryState && repo.repository_state !== state.repositoryState) return false;
      if (state.auditFreshness && repo.audit_freshness !== state.auditFreshness) return false;
      return true;
    })
    .map((repo) => ({ repo, match: matchRepository(repo, query) }))
    .filter((item) => item.match.matches)
    .sort((a, b) => compareRepositories(a.repo, b.repo));
}

function workBadge(value) {
  return element("span", "work-badge status-neutral", value || "--");
}

function auditBadge(repo) {
  const freshness = String(repo.audit_freshness || "--");
  const classValue = freshness === "CURRENT"
    ? "audit-badge audit-current"
    : freshness === "DRIFTED"
      ? "audit-badge audit-drifted"
      : "audit-badge audit-unknown";
  return element(
    "span",
    classValue,
    freshness + (repo.audit_depth ? " · " + repo.audit_depth : ""),
  );
}

function repositorySelector(repo, className = "repo-select") {
  const button = element("button", className, repoKey(repo) || "unknown");
  button.type = "button";
  button.dataset.repoKey = repoKey(repo);
  button.setAttribute("aria-label", (repoKey(repo) || "repository") + " の詳細");
  button.addEventListener("click", () => setSelectedRepository(repoKey(repo), button));
  return button;
}

function controlLink(repo, className = "row-link") {
  const link = safeUrl(repo.issue_url, "/kinoko34077/devflow/issues/");
  if (!link) return element("span", className, "--");
  const anchor = element("a", className, "Control ↗");
  anchor.href = link;
  anchor.target = "_blank";
  anchor.rel = "noopener noreferrer";
  return anchor;
}

function renderRepositoryTable(items) {
  ui.repositoryTbody.replaceChildren();
  for (const { repo, match } of items) {
    const row = element("tr", "repo-row");
    row.dataset.repoKey = repoKey(repo);
    row.dataset.selected = String(state.selectedRepository === repoKey(repo));

    const repositoryCell = document.createElement("td");
    repositoryCell.append(repositorySelector(repo));

    const workCell = document.createElement("td");
    workCell.append(workBadge(repo.work_status));

    const stateCell = document.createElement("td");
    stateCell.append(element("span", "state-label status-neutral", repo.repository_state || "--"));

    const auditCell = document.createElement("td");
    auditCell.append(auditBadge(repo));

    const updatedCell = element("td", "", formatShortTime(repo.updated_at));

    const nextCell = element("td", "next-cell");
    nextCell.append(element("span", "next-preview", repo.next_action || "--"));
    if (match.reason) {
      nextCell.append(element("span", "match-reason", match.reason));
    }

    const actionCell = document.createElement("td");
    actionCell.append(controlLink(repo));

    row.append(
      repositoryCell,
      workCell,
      stateCell,
      auditCell,
      updatedCell,
      nextCell,
      actionCell,
    );
    ui.repositoryTbody.append(row);
  }
}

function renderRepositoryMobileList(items) {
  ui.repositoryMobileList.replaceChildren();
  for (const { repo, match } of items) {
    const row = element("article", "mobile-repo-row");
    row.dataset.repoKey = repoKey(repo);
    row.dataset.selected = String(state.selectedRepository === repoKey(repo));

    const top = element("div", "mobile-repo-top");
    top.append(repositorySelector(repo), controlLink(repo));

    const badges = element("div", "mobile-repo-badges");
    badges.append(
      workBadge(repo.work_status),
      auditBadge(repo),
      element("span", "state-label status-neutral", repo.repository_state || "--"),
    );

    row.append(
      top,
      badges,
      element("p", "mobile-next", repo.next_action || "--"),
    );
    if (match.reason) {
      row.append(element("p", "match-reason", match.reason));
    }
    ui.repositoryMobileList.append(row);
  }
}

function renderRepositories() {
  const items = filteredRepositories();
  renderRepositoryTable(items);
  renderRepositoryMobileList(items);

  const total = state.payload && Array.isArray(state.payload.repositories)
    ? state.payload.repositories.length
    : 0;
  ui.repositoryCount.textContent = String(items.length) + " / " + String(total);
  ui.repositoryEmpty.hidden = items.length !== 0;
}

function inspectorSection(title, value) {
  const section = element("section", "inspector-section");
  section.append(
    element("h3", "", title),
    element("p", "inspector-prose", value || "--"),
  );
  return section;
}

function appendDefinition(list, term, value) {
  list.append(
    element("dt", "", term),
    element("dd", "", value || "--"),
  );
}

function renderInspectorHumanPortfolio(repo, container) {
  const portfolio = portfolioForRepository(repo.repository_full_name || "");
  if (!portfolio) return;
  const items = Array.isArray(portfolio.entries) ? portfolio.entries : [];
  if (items.length === 0 && portfolio.transport_status === "CURRENT") return;

  const section = element("section", "inspector-section");
  section.append(element("h3", "", "Human Portfolio"));
  section.append(element(
    "p",
    "inspector-prose",
    "Transport: " + transportLabel(portfolio)
      + (portfolio.complete ? " · complete" : " · incomplete"),
  ));

  for (const entry of items) {
    const line = element("p", "inspector-prose");
    const link = safeUrl(entry.entry_ref, "/kinoko34077/");
    const label = (DISPOSITION_LABELS[entry.disposition] || entry.disposition || "不明")
      + " · " + (entry.task_ref || "--");
    if (link) {
      const anchor = element("a", "", label);
      anchor.href = link;
      anchor.target = "_blank";
      anchor.rel = "noopener noreferrer";
      line.append(anchor);
    } else {
      line.textContent = label;
    }
    section.append(line);
  }
  container.append(section);
}

function renderInspector() {
  const repos = state.payload && Array.isArray(state.payload.repositories)
    ? state.payload.repositories
    : [];
  const repo = repos.find((item) => repoKey(item) === state.selectedRepository) || null;

  ui.inspectorContent.replaceChildren();

  if (!repo) {
    ui.repositoryInspector.dataset.open = "false";
    ui.inspectorTitle.textContent = "Repository detail";
    ui.inspectorContent.append(element(
      "p",
      "inspector-placeholder",
      "一覧からrepositoryを選択すると、Next Action・Active Work・audit detailを表示します。",
    ));
    return;
  }

  ui.repositoryInspector.dataset.open = "true";
  ui.inspectorTitle.textContent = "Repository detail";

  const repoLine = element("div", "inspector-repo-line");
  repoLine.append(
    element("h3", "inspector-repo", repoKey(repo)),
    controlLink(repo),
  );
  ui.inspectorContent.append(repoLine);

  const badges = element("div", "inspector-badges");
  badges.append(
    workBadge(repo.work_status),
    element("span", "state-label status-neutral", repo.repository_state || "--"),
    auditBadge(repo),
  );
  ui.inspectorContent.append(badges);

  ui.inspectorContent.append(
    inspectorSection("次のアクション", repo.next_action),
    inspectorSection("現在の作業", repo.active_work),
  );

  renderInspectorHumanPortfolio(repo, ui.inspectorContent);

  const auditSection = element("section", "inspector-section");
  auditSection.append(element("h3", "", "Audit"));
  const auditList = element("dl", "audit-list");
  appendDefinition(auditList, "Freshness", repo.audit_freshness);
  appendDefinition(auditList, "Depth", repo.audit_depth);
  appendDefinition(auditList, "Ref", repo.audit_ref);
  appendDefinition(auditList, "SHA", repo.audit_sha);
  appendDefinition(auditList, "Last audit", formatTime(repo.last_audit_at));
  appendDefinition(auditList, "Last deep", formatTime(repo.last_deep_audit_at));
  appendDefinition(auditList, "Control updated", formatTime(repo.updated_at));
  auditSection.append(auditList);

  if (repo.audit_scope || repo.audit_evidence) {
    const disclosure = document.createElement("details");
    disclosure.className = "audit-disclosure";
    disclosure.append(element("summary", "", "Audit detail"));
    if (repo.audit_scope) {
      disclosure.append(
        element("p", "", "Scope\n" + repo.audit_scope),
      );
    }
    if (repo.audit_evidence) {
      disclosure.append(
        element("p", "", "Evidence\n" + repo.audit_evidence),
      );
    }
    auditSection.append(disclosure);
  }

  ui.inspectorContent.append(auditSection);
}

function focusSelectedRepository() {
  const buttons = [...document.querySelectorAll("[data-repo-key]")];
  const target = buttons.find(
    (node) => node.tagName === "BUTTON" && node.dataset.repoKey === state.selectedRepository,
  );
  if (target) {
    target.focus();
    return;
  }
  ui.search.focus();
}

function setSelectedRepository(repositoryKey, sourceElement = null) {
  state.selectedRepository = repositoryKey || "";
  state.lastFocus = sourceElement || document.activeElement;
  writeLocationState();
  renderRepositories();
  renderInspector();
  ui.appStatus.textContent = state.selectedRepository
    ? state.selectedRepository + " の詳細を表示しました。"
    : "詳細を閉じました。";
}

function closeInspector({ returnFocus = true } = {}) {
  const previous = state.lastFocus;
  state.selectedRepository = "";
  writeLocationState();
  renderRepositories();
  renderInspector();
  if (returnFocus) {
    if (previous && typeof previous.focus === "function" && document.contains(previous)) {
      previous.focus();
    } else {
      focusSelectedRepository();
    }
  }
  ui.appStatus.textContent = "Repository detailを閉じました。";
}

function updateClearVisibility() {
  const active = Boolean(
    state.query
      || state.workStatus
      || state.repositoryState
      || state.auditFreshness
      || state.sortOrder !== DEFAULT_SORT,
  );
  ui.clearFilters.hidden = !active;
}

function clearFilters() {
  state.query = "";
  state.workStatus = "";
  state.repositoryState = "";
  state.auditFreshness = "";
  state.sortOrder = DEFAULT_SORT;
  ui.search.value = "";
  ui.workStatus.value = "";
  ui.repositoryState.value = "";
  ui.auditFreshness.value = "";
  ui.sortOrder.value = DEFAULT_SORT;
  writeLocationState();
  renderSummary();
  renderRepositories();
  updateClearVisibility();
  ui.search.focus();
}

function render() {
  renderSource();
  renderSummary();
  renderHumanQueue();
  renderRepositories();
  renderInspector();
  updateClearVisibility();
}

function syncControlsFromState() {
  ui.search.value = state.query;
  ui.workStatus.value = [...ui.workStatus.options].some((option) => option.value === state.workStatus)
    ? state.workStatus
    : "";
  state.workStatus = ui.workStatus.value;
  ui.repositoryState.value = [...ui.repositoryState.options].some(
    (option) => option.value === state.repositoryState,
  ) ? state.repositoryState : "";
  state.repositoryState = ui.repositoryState.value;
  ui.auditFreshness.value = [...ui.auditFreshness.options].some(
    (option) => option.value === state.auditFreshness,
  ) ? state.auditFreshness : "";
  state.auditFreshness = ui.auditFreshness.value;
  ui.sortOrder.value = SORT_VALUES.has(state.sortOrder) ? state.sortOrder : DEFAULT_SORT;
  state.sortOrder = ui.sortOrder.value;
}

async function loadState() {
  state.loadError = "";
  ui.sourceStatus.textContent = "読込中";
  ui.sourceStatus.className = "status-badge status-neutral";
  try {
    const response = await fetch("./state.json", { cache: "no-store" });
    if (!response.ok) {
      throw new Error("state.json HTTP " + response.status);
    }
    const payload = await response.json();
    if (payload.schema_version !== "repo-monitor-pages.v1") {
      throw new Error("unsupported state.json schema");
    }
    state.payload = payload;
    populateFilters();

    if (
      state.selectedRepository
      && !payload.repositories.some((repo) => repoKey(repo) === state.selectedRepository)
    ) {
      state.selectedRepository = "";
      writeLocationState();
    }

    render();
    ui.appStatus.textContent =
      String(payload.repositories.length) + " repositoryを読み込みました。";
  } catch (error) {
    state.payload = null;
    state.loadError = String(error && error.message ? error.message : error);
    ui.repositoryTbody.replaceChildren();
    ui.repositoryMobileList.replaceChildren();
    ui.humanQueueList.replaceChildren();
    ui.repositoryCount.textContent = "0";
    ui.humanQueue.hidden = true;
    renderSource();
    ui.repositoryEmpty.hidden = false;
    ui.appStatus.textContent = "Snapshotの読込に失敗しました。";
  }
}

ui.search.addEventListener("input", () => {
  state.query = ui.search.value;
  writeLocationState();
  renderRepositories();
  updateClearVisibility();
});

ui.workStatus.addEventListener("change", () => {
  state.workStatus = ui.workStatus.value;
  writeLocationState();
  renderSummary();
  renderRepositories();
  updateClearVisibility();
});

ui.repositoryState.addEventListener("change", () => {
  state.repositoryState = ui.repositoryState.value;
  writeLocationState();
  renderRepositories();
  updateClearVisibility();
});

ui.auditFreshness.addEventListener("change", () => {
  state.auditFreshness = ui.auditFreshness.value;
  writeLocationState();
  renderRepositories();
  updateClearVisibility();
});

ui.sortOrder.addEventListener("change", () => {
  state.sortOrder = SORT_VALUES.has(ui.sortOrder.value)
    ? ui.sortOrder.value
    : DEFAULT_SORT;
  writeLocationState();
  renderRepositories();
  updateClearVisibility();
});

ui.clearFilters.addEventListener("click", clearFilters);
ui.emptyClearFilters.addEventListener("click", clearFilters);
ui.retryLoad.addEventListener("click", loadState);
ui.inspectorClose.addEventListener("click", () => closeInspector());

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && state.selectedRepository) {
    event.preventDefault();
    closeInspector();
  }
});

window.addEventListener("popstate", () => {
  readLocationState();
  if (state.payload) {
    syncControlsFromState();
    render();
  }
});

window.addEventListener("hashchange", () => {
  const before = state.selectedRepository;
  readLocationState();
  if (state.payload && before !== state.selectedRepository) {
    renderRepositories();
    renderInspector();
  }
});

readLocationState();
loadState();
