const state = {
  payload: null,
  query: "",
  workStatus: "",
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
  sourceNote: document.getElementById("source-note"),
  search: document.getElementById("search"),
  workStatus: document.getElementById("work-status"),
  queueList: document.getElementById("queue-list"),
  queueCount: document.getElementById("queue-count"),
  queueEmpty: document.getElementById("queue-empty"),
  repositoryList: document.getElementById("repository-list"),
  repositoryCount: document.getElementById("repository-count"),
  repositoryEmpty: document.getElementById("repository-empty"),
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
    second: "2-digit",
    timeZoneName: "short",
  }).format(date);
}

function repositoryText(repo) {
  return [
    repo.repository,
    repo.repository_full_name,
    repo.work_status,
    repo.repository_state,
    repo.active_work,
    repo.next_action,
    repo.audit_depth,
    repo.audit_freshness,
  ]
    .filter(Boolean)
    .join("\n")
    .toLocaleLowerCase();
}

function renderSource() {
  const payload = state.payload;
  const source = payload && payload.source ? payload.source : {};
  let label = "正常";
  let stateName = "OK";
  let note = "public devflow Controlから生成されたsnapshotです。";

  if (source.error) {
    label = "取得エラー";
    stateName = "ERROR";
    note = "生成時のdevflow取得エラー: " + source.error;
  } else if (source.stale) {
    label = "stale";
    stateName = "STALE";
    note = "sourceがstaleとして生成されています。現在値として扱わないでください。";
  }

  ui.sourceStatus.textContent = label;
  ui.sourceStatus.dataset.state = stateName;
  ui.generatedAt.textContent = "生成 " + formatTime(payload ? payload.generated_at : null);
  ui.sourceNote.textContent = note;
}

function populateWorkStatus() {
  const selected = state.workStatus;
  const repos = state.payload && Array.isArray(state.payload.repositories)
    ? state.payload.repositories
    : [];
  const statuses = [...new Set(
    repos.map((repo) => repo.work_status).filter(Boolean)
  )].sort((a, b) => a.localeCompare(b));

  ui.workStatus.replaceChildren();
  const all = element("option", "", "すべて");
  all.value = "";
  ui.workStatus.append(all);
  for (const status of statuses) {
    const option = element("option", "", status);
    option.value = status;
    ui.workStatus.append(option);
  }
  ui.workStatus.value = statuses.includes(selected) ? selected : "";
  state.workStatus = ui.workStatus.value;
}

function renderQueue() {
  const portfolios = state.payload && Array.isArray(state.payload.human_portfolios)
    ? state.payload.human_portfolios
    : [];
  ui.queueList.replaceChildren();

  let entryCount = 0;
  for (const portfolio of portfolios) {
    const card = element("article", "queue-card");
    const heading = element("div", "queue-heading");
    heading.append(
      element("h3", "", portfolio.repository || "unknown repository"),
      element(
        "span",
        "transport-chip",
        TRANSPORT_LABELS[portfolio.transport_status]
          || portfolio.transport_status
          || "不明",
      ),
    );
    heading.lastElementChild.dataset.state = portfolio.transport_status || "UNKNOWN";
    card.append(heading);

    card.append(
      element(
        "p",
        "queue-meta",
        "観測 " + formatTime(portfolio.observed_at)
          + " · " + (portfolio.complete ? "complete" : "incomplete"),
      ),
    );

    const entries = element("div", "queue-entries");
    const items = Array.isArray(portfolio.entries) ? portfolio.entries : [];
    for (const entry of items) {
      entryCount += 1;
      const row = element("div", "queue-entry");
      row.dataset.disposition = entry.disposition || "UNKNOWN";
      row.append(
        element(
          "span",
          "disposition-chip",
          DISPOSITION_LABELS[entry.disposition] || entry.disposition || "不明",
        ),
      );
      const body = element("div", "entry-body");
      const link = safeUrl(entry.entry_ref, "/kinoko34077/");
      if (link) {
        const anchor = element("a", "entry-link", entry.task_ref || "--");
        anchor.href = link;
        anchor.target = "_blank";
        anchor.rel = "noopener noreferrer";
        body.append(anchor);
      } else {
        body.append(element("span", "entry-link", entry.task_ref || "--"));
      }
      body.append(
        element(
          "span",
          "entry-meta",
          [entry.role, entry.source_kind, entry.evidence_freshness, entry.evidence_trust]
            .filter(Boolean)
            .join(" · "),
        ),
      );
      row.append(body);
      entries.append(row);
    }
    if (!items.length) {
      entries.append(element("p", "queue-meta", "entryなし"));
    }
    card.append(entries);
    ui.queueList.append(card);
  }

  ui.queueCount.textContent = String(entryCount);
  ui.queueEmpty.hidden = portfolios.length !== 0;
}

function renderRepositories() {
  const repos = state.payload && Array.isArray(state.payload.repositories)
    ? state.payload.repositories
    : [];
  const query = state.query.trim().toLocaleLowerCase();
  const filtered = repos.filter((repo) => {
    if (state.workStatus && repo.work_status !== state.workStatus) return false;
    if (query && !repositoryText(repo).includes(query)) return false;
    return true;
  });

  ui.repositoryList.replaceChildren();
  for (const repo of filtered) {
    const card = element("article", "repository-card");
    const heading = element("div", "card-heading");
    const titleText = repo.repository_full_name || repo.repository || "unknown";
    const issueUrl = safeUrl(repo.issue_url, "/kinoko34077/devflow/issues/");
    if (issueUrl) {
      const title = element("a", "", titleText);
      title.href = issueUrl;
      title.target = "_blank";
      title.rel = "noopener noreferrer";
      const h3 = document.createElement("h3");
      h3.append(title);
      heading.append(h3);
    } else {
      heading.append(element("h3", "", titleText));
    }
    heading.append(element("span", "work-chip", repo.work_status || "--"));
    card.append(heading);

    const metaParts = [];
    if (repo.repository_state) metaParts.push(repo.repository_state);
    if (repo.audit_depth) metaParts.push("audit " + repo.audit_depth);
    if (repo.audit_freshness) metaParts.push(repo.audit_freshness);
    if (repo.updated_at) metaParts.push("Control " + formatTime(repo.updated_at));
    card.append(element("p", "card-meta", metaParts.join(" · ")));

    if (repo.next_action) {
      card.append(element("p", "next-action", "Next: " + repo.next_action));
    }
    if (repo.active_work) {
      card.append(element("p", "active-work", repo.active_work));
    }
    if (repo.audit_sha) {
      const auditText = "Audit " + repo.audit_sha.slice(0, 12)
        + (repo.audit_ref ? " · " + repo.audit_ref : "");
      card.append(element("p", "audit-meta", auditText));
    }
    ui.repositoryList.append(card);
  }

  ui.repositoryCount.textContent = String(filtered.length) + " / " + String(repos.length);
  ui.repositoryEmpty.hidden = filtered.length !== 0;
}

function render() {
  renderSource();
  renderQueue();
  renderRepositories();
}

async function load() {
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
    populateWorkStatus();
    render();
  } catch (error) {
    ui.sourceStatus.textContent = "読込失敗";
    ui.sourceStatus.dataset.state = "ERROR";
    ui.sourceNote.textContent = String(error && error.message ? error.message : error);
    ui.generatedAt.textContent = "生成時刻 --";
  }
}

ui.search.addEventListener("input", () => {
  state.query = ui.search.value;
  renderRepositories();
});

ui.workStatus.addEventListener("change", () => {
  state.workStatus = ui.workStatus.value;
  renderRepositories();
});

load();
