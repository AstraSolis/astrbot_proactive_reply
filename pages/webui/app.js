const bridge = window.AstrBotPluginPage;
const I18N = "pages.webui.";
const VISIT_KEY = "astrbot-proactive-webui-seen";

let activeView = "dashboard";
let sessionsLoaded = false;
let sessions = [];
let sessionFilter = "";
let refreshTimer = null;
let dashboardPromise = null;
let sessionsPromise = null;

applyVisitState();

function t(key, fallback) {
  return bridge.t(I18N + key, fallback);
}

function apiLocale() {
  return { locale: bridge.getLocale() };
}

function applyVisitState() {
  try {
    const seen = localStorage.getItem(VISIT_KEY) === "1";
    document.body.classList.add(seen ? "returning-visit" : "first-visit");
    if (!seen) localStorage.setItem(VISIT_KEY, "1");
  } catch {
    document.body.classList.add("returning-visit");
  }
}

function getInitials(name) {
  const s = String(name || "").trim();
  if (!s) return "?";
  if (/[\u4e00-\u9fff]/.test(s)) return s.slice(0, 1);
  return s.slice(0, 2).toUpperCase();
}

function renderStatic() {
  const locale = bridge.getLocale();
  const ctx = bridge.getContext();
  const pluginName = ctx?.displayName || t("heading", "心念");

  document.documentElement.lang = locale;
  document.title = t("title", "心念管理");

  document.getElementById("sidebar-plugin-name").textContent = pluginName;
  document.getElementById("sidebar-plugin-role").textContent =
    t("sidebar_role", "主动回复管理");
  document.getElementById("sidebar-avatar").textContent = getInitials(pluginName);
  document.getElementById("sidebar-version").textContent = ctx?.version
    ? `v${ctx.version}`
    : t("sidebar_build", "心念 WebUI");

  document.getElementById("nav-section-main").textContent =
    t("nav_section_main", "主菜单");
  document.getElementById("nav-label-dashboard").textContent =
    t("tab_dashboard", "概览");
  document.getElementById("nav-label-sessions").textContent =
    t("tab_sessions", "会话");

  document.getElementById("page-title-dashboard").textContent =
    t("tab_dashboard", "概览");
  document.getElementById("page-title-sessions").textContent =
    t("tab_sessions", "会话");
  document.getElementById("section-today").textContent =
    t("section_today", "今天");
  document.getElementById("section-recent").textContent =
    t("section_recent", "近期概览");

  const refreshLabel = t("btn_refresh", "刷新");
  document.getElementById("btn-refresh").title = refreshLabel;
  document.getElementById("btn-refresh-panel").title = refreshLabel;
  document.getElementById("btn-add-session").title =
    t("btn_add_session", "添加会话");

  document.getElementById("hdr-plugin-status").textContent =
    t("plugin_status", "当前状态");
  document.getElementById("hdr-recent-activity").textContent =
    t("recent_activity", "最近记录");
  document.getElementById("lbl-stat-total").textContent =
    t("stat_total_sessions", "总会话");
  document.getElementById("lbl-stat-active").textContent =
    t("stat_active", "活跃");
  document.getElementById("lbl-stat-inactive").textContent =
    t("stat_inactive", "安静");
  document.getElementById("hdr-session-list").textContent =
    t("session_list", "会话列表");

  document.getElementById("dialog-add-title").textContent =
    t("dialog_add_title", "添加主动会话");
  document.getElementById("label-session-id").textContent =
    t("label_session_id", "会话 ID");
  document.getElementById("input-session-id").placeholder =
    t("session_id_placeholder", "例如：aiocqhttp:GroupMessage:123456789");
  document.getElementById("session-id-hint").innerHTML =
    escHtml(t("session_id_format_hint", "格式：")) +
    "<code>platform_name:message_type:session_id</code><br />" +
    escHtml(t("session_id_example", "示例：")) +
    "<code>aiocqhttp:GroupMessage:123456789</code>";
  document.getElementById("btn-dialog-cancel").textContent =
    t("btn_cancel", "取消");
  document.getElementById("submit-btn").textContent =
    t("btn_add", "添加");

  document.getElementById("sidebar-nav").setAttribute(
    "aria-label",
    t("aria_main_nav", "主导航"),
  );
  document.getElementById("menu-toggle").setAttribute(
    "aria-label",
    t("aria_menu_toggle", "打开菜单"),
  );

  applyLoadingPlaceholders();
  updateSearchShortcutHint();
  updateSearchForView(activeView);
}

function applyLoadingPlaceholders() {
  const text = t("loading", "加载中…");
  document.querySelectorAll(".loading-text").forEach(el => {
    el.textContent = text;
  });
}

function updateSearchShortcutHint() {
  const kbd = document.getElementById("search-kbd");
  const isMac = /Mac|iPhone|iPad|iPod/i.test(navigator.userAgent);
  kbd.textContent = isMac ? "⌘K" : "Ctrl+K";
  kbd.hidden = false;
}

function loadingHtml() {
  return `<div class="loading"><div class="spinner"></div><span class="loading-text">${escHtml(t("loading", "加载中…"))}</span></div>`;
}

function metricCard(label, valueHtml) {
  return `
    <div class="metric-card">
      <div class="metric-card-top">
        <span class="metric-label">${label}</span>
      </div>
      <div class="metric-value">${valueHtml}</div>
    </div>`;
}

function emptyStateHtml(title, desc, actionHtml = "") {
  return `
    <div class="empty-state">
      <div class="empty-state-icon" aria-hidden="true">
        <svg viewBox="0 0 24 24"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
      </div>
      <h5>${escHtml(title)}</h5>
      <p>${desc}</p>
      ${actionHtml}
    </div>`;
}

function updateSearchForView(view) {
  const input = document.getElementById("search-input");
  if (view === "sessions") {
    input.disabled = false;
    input.placeholder = t("search_sessions", "搜索会话 ID 或用户名…");
  } else {
    input.disabled = true;
    input.value = "";
    sessionFilter = "";
    input.placeholder = t("search_hint_dashboard", "切换到会话页后可搜索");
  }
}

function switchView(view) {
  activeView = view;

  document.querySelectorAll(".nav-item").forEach(btn => {
    const isActive = btn.dataset.view === view;
    btn.classList.toggle("active", isActive);
    if (isActive) btn.setAttribute("aria-current", "page");
    else btn.removeAttribute("aria-current");
  });

  document.querySelectorAll(".view").forEach(panel => {
    panel.classList.toggle("view-active", panel.dataset.view === view);
  });

  document.getElementById("btn-refresh").style.display =
    view === "dashboard" ? "inline-flex" : "none";
  document.getElementById("btn-add-session").style.display =
    view === "sessions" ? "inline-flex" : "none";

  updateSearchForView(view);
  closeSidebar();
  hideGlobalError();

  if (view === "sessions" && !sessionsLoaded) {
    loadSessions();
  } else if (view === "sessions" && sessionsLoaded) {
    applySessionFilter();
  }
}

document.querySelectorAll(".nav-item").forEach(btn => {
  btn.addEventListener("click", () => switchView(btn.dataset.view));
});

function openSidebar() {
  document.getElementById("sidebar").classList.add("is-open");
  document.getElementById("sidebar-backdrop").classList.add("is-visible");
}

function closeSidebar() {
  document.getElementById("sidebar").classList.remove("is-open");
  document.getElementById("sidebar-backdrop").classList.remove("is-visible");
}

document.getElementById("menu-toggle").addEventListener("click", openSidebar);
document.getElementById("sidebar-backdrop").addEventListener("click", closeSidebar);

document.getElementById("search-input").addEventListener("input", e => {
  sessionFilter = e.target.value;
  if (activeView === "sessions" && sessionsLoaded) {
    applySessionFilter();
  }
});

document.addEventListener("keydown", e => {
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
    e.preventDefault();
    const input = document.getElementById("search-input");
    if (!input.disabled) input.focus();
  }
  if (e.key === "Escape") {
    hideAddDialog();
    closeSidebar();
  }
});

async function loadDashboard() {
  if (dashboardPromise) return dashboardPromise;
  dashboardPromise = (async () => {
    try {
      const data = await bridge.apiGet("dashboard/stats", apiLocale());
      if (!data.success) throw new Error(data.error || t("err_unknown", "未知错误"));
      renderDashboard(data.stats);
      hideGlobalError();
    } catch (err) {
      showGlobalError(t("err_dashboard_load", "概览加载失败：") + err.message);
      console.error(err);
    } finally {
      dashboardPromise = null;
    }
  })();
  return dashboardPromise;
}

window.refreshDashboard = function () {
  loadDashboard();
};

document.getElementById("btn-refresh").addEventListener("click", () => loadDashboard());
document.getElementById("btn-refresh-panel").addEventListener("click", () => loadDashboard());
document.getElementById("btn-add-session").addEventListener("click", () => showAddDialog());

function renderDashboard(s) {
  const ctx = bridge.getContext();
  const pluginName = ctx?.displayName || t("heading", "心念");
  const runLabel = s.proactive_running
    ? t("status_running", "运行中")
    : t("status_stopped", "已停止");

  const statusHtml = `
    <span class="status-text">
      <span class="status-dot ${s.proactive_running ? "running" : "stopped"}"></span>
      ${escHtml(runLabel)}
    </span>`;

  document.getElementById("dash-stats-grid").innerHTML = [
    metricCard(escHtml(t("stat_session_count", "总会话数")), s.session_count),
    metricCard(escHtml(t("stat_ai_schedules", "计划任务")), s.ai_schedules_count),
    metricCard(escHtml(t("stat_users", "记录用户")), s.user_count),
    metricCard(escHtml(t("stat_run_status", "运行状态")), statusHtml),
  ].join("");

  document.getElementById("plugin-status-rows").innerHTML = `
    <div class="info-row">
      <span class="info-label">${escHtml(t("label_plugin_name", "插件名称"))}</span>
      <span class="info-value">${escHtml(pluginName)}</span>
    </div>
    <div class="info-row">
      <span class="info-label">${escHtml(t("label_feature_status", "功能状态"))}</span>
      <div class="tags">
        <span class="tag ${s.proactive_enabled ? "on" : "off"}">
          <span class="tag-dot"></span>${escHtml(t("tag_proactive", "主动消息"))}
        </span>
        <span class="tag ${s.ai_schedule_enabled ? "on" : "off"}">
          <span class="tag-dot"></span>${escHtml(t("tag_ai_schedule", "计划任务"))}
        </span>
        <span class="tag ${s.proactive_running ? "on" : "off"}">
          <span class="tag-dot"></span>${escHtml(t("tag_timer", "定时任务"))}
        </span>
      </div>
    </div>`;

  const activities = s.recent_activities || [];
  if (activities.length === 0) {
    document.getElementById("timeline").innerHTML = emptyStateHtml(
      t("empty_activity_title", "暂无活动记录"),
      escHtml(t("empty_activity_desc", "当插件开始工作后，活动记录将在此显示")),
    );
    return;
  }

  const colorMap = { success: "success", warning: "warning", info: "info" };

  document.getElementById("timeline").innerHTML = `
    <div class="activity-list">${activities.map(a => {
      const tone = colorMap[a.color] || "info";
      return `
      <div class="activity-item">
        <div class="activity-main">
          <div class="activity-title">${escHtml(a.title)}</div>
          <div class="activity-desc">${escHtml(a.desc)}</div>
        </div>
        <span class="activity-pill ${tone}">${escHtml(a.time_display)}</span>
      </div>`;
    }).join("")}</div>`;
}

async function loadSessions() {
  if (sessionsPromise) return sessionsPromise;
  sessionsPromise = (async () => {
    document.getElementById("sessions-container").innerHTML = loadingHtml();
    try {
      const data = await bridge.apiGet("sessions/list", apiLocale());
      if (!data.success) throw new Error(data.error || t("err_unknown", "未知错误"));
      sessions = data.sessions || [];
      sessionsLoaded = true;
      applySessionFilter();
      hideGlobalError();
    } catch (err) {
      showGlobalError(t("err_sessions_load", "会话列表加载失败：") + err.message);
      document.getElementById("sessions-container").innerHTML = `
      <div class="empty-state">
        <p>${escHtml(t("load_sessions_failed", "加载失败，请切换页面后重试"))}</p>
      </div>`;
    } finally {
      sessionsPromise = null;
    }
  })();
  return sessionsPromise;
}

function applySessionFilter() {
  const q = sessionFilter.trim().toLowerCase();
  const list = !q
    ? sessions
    : sessions.filter(
        s =>
          s.session_id.toLowerCase().includes(q) ||
          (s.username && s.username.toLowerCase().includes(q)),
      );
  updateSessionStats(list);
  renderSessions(list);
}

function updateSessionStats(list) {
  document.getElementById("count-total").textContent = list.length;
  document.getElementById("count-active").textContent =
    list.filter(s => s.status === "active").length;
  document.getElementById("count-inactive").textContent =
    list.filter(s => s.status !== "active").length;
}

function renderSessions(list) {
  if (list.length === 0) {
    const isFiltered = sessionFilter.trim().length > 0;
    document.getElementById("sessions-container").innerHTML = emptyStateHtml(
      isFiltered ? t("empty_search_title", "未找到匹配会话") : t("empty_sessions_title", "还没有主动会话"),
      isFiltered
        ? escHtml(t("empty_search_desc", "请尝试其他关键词"))
        : `${escHtml(t("empty_sessions_desc", "点击顶部 + 添加，或在聊天中使用"))} <code>/proactive add_session</code>`,
      isFiltered
        ? ""
        : `<button type="button" class="btn btn-primary" onclick="showAddDialog()">${escHtml(t("btn_add_first", "添加第一个会话"))}</button>`,
    );
    return;
  }

  const platformLabel = p => {
    if (p === "qq" || p === "aiocqhttp") return "QQ";
    if (p === "wechat") return t("platform_wechat", "微信");
    if (p === "telegram") return "TG";
    return p;
  };

  const rows = list.map(s => `
    <tr>
      <td><code>${escHtml(s.session_id)}</code></td>
      <td><span class="badge badge-secondary">${escHtml(platformLabel(s.platform))}</span></td>
      <td>${s.username ? escHtml(s.username) : '<span class="text-muted">—</span>'}</td>
      <td>
        ${s.next_fire_soon
          ? `<span class="text-success">${escHtml(s.next_fire_display)}</span>`
          : `<span class="text-muted">${escHtml(s.next_fire_display)}</span>`}
      </td>
      <td><span class="text-note">${escHtml(s.last_sent_time)}</span></td>
      <td>
        ${s.unreplied_count > 0
          ? `<span class="badge badge-warning">${s.unreplied_count}</span>`
          : `<span class="text-muted">0</span>`}
      </td>
      <td>
        <span class="badge ${s.status === "active" ? "badge-success" : "badge-warning"}">
          ${escHtml(s.status_display)}
        </span>
        ${s.ai_task_count > 0
          ? `<span class="badge badge-info">${escHtml(t("badge_ai_tasks", "计划 ×{count}").replace("{count}", s.ai_task_count))}</span>`
          : ""}
      </td>
      <td>
        <button type="button" class="btn-text" data-session-id="${escAttr(s.session_id)}" title="${escAttr(t("remove_title", "移除"))}">${escHtml(t("remove_title", "移除"))}</button>
      </td>
    </tr>`).join("");

  document.getElementById("sessions-container").innerHTML = `
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>${escHtml(t("th_session_id", "会话 ID"))}</th>
            <th>${escHtml(t("th_platform", "平台"))}</th>
            <th>${escHtml(t("th_user", "用户"))}</th>
            <th>${escHtml(t("th_next_send", "下次发送"))}</th>
            <th>${escHtml(t("th_last_send", "最后发送"))}</th>
            <th>${escHtml(t("th_unreplied", "未回复"))}</th>
            <th>${escHtml(t("th_status", "状态"))}</th>
            <th>${escHtml(t("th_actions", "操作"))}</th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
    </div>`;
}

window.showAddDialog = function () {
  document.getElementById("input-session-id").value = "";
  document.getElementById("add-dialog").style.display = "flex";
  setTimeout(() => document.getElementById("input-session-id").focus(), 50);
};

window.hideAddDialog = function () {
  document.getElementById("add-dialog").style.display = "none";
};

window.submitAdd = async function () {
  const sessionId = document.getElementById("input-session-id").value.trim();
  if (!sessionId) {
    toast(t("toast_enter_session_id", "请输入会话 ID"), "error");
    return;
  }
  if (sessionId.split(":").length < 3) {
    toast(t("toast_invalid_format", "格式不正确，应为 platform:type:id"), "error");
    return;
  }

  const btn = document.getElementById("submit-btn");
  btn.disabled = true;
  btn.textContent = t("btn_adding", "添加中…");
  try {
    const data = await bridge.apiPost("sessions/add", {
      session_id: sessionId,
      locale: bridge.getLocale(),
    });
    if (!data.success) throw new Error(data.error || t("toast_add_failed", "添加失败"));
    toast(data.message || t("toast_session_added", "会话已添加"), "success");
    hideAddDialog();
    await loadSessions();
    if (activeView === "dashboard") await loadDashboard();
  } catch (err) {
    toast(err.message, "error");
  } finally {
    btn.disabled = false;
    btn.textContent = t("btn_add", "添加");
  }
};

document.getElementById("btn-dialog-cancel").addEventListener("click", hideAddDialog);
document.getElementById("submit-btn").addEventListener("click", () => submitAdd());
document.getElementById("add-dialog").addEventListener("click", e => {
  if (e.target.id === "add-dialog") hideAddDialog();
});

document.getElementById("input-session-id").addEventListener("keydown", e => {
  if (e.key === "Enter") submitAdd();
  if (e.key === "Escape") hideAddDialog();
});

document.getElementById("sessions-container").addEventListener("click", e => {
  const button = e.target.closest("[data-session-id]");
  if (!button) return;
  confirmRemove(button.dataset.sessionId);
});

async function confirmRemove(sessionId) {
  const msg = t("confirm_remove", '确定要移除会话 "{session_id}" 吗？').replace(
    "{session_id}",
    sessionId,
  );
  if (!confirm(msg)) return;
  try {
    const data = await bridge.apiPost("sessions/remove", {
      session_id: sessionId,
      locale: bridge.getLocale(),
    });
    if (!data.success) throw new Error(data.error || t("toast_remove_failed", "移除失败"));
    toast(data.message || t("toast_session_removed", "会话已移除"), "success");
    await loadSessions();
    if (activeView === "dashboard") await loadDashboard();
  } catch (err) {
    toast(err.message, "error");
  }
}

function showGlobalError(msg) {
  const el = document.getElementById("global-error");
  el.textContent = msg;
  el.style.display = "block";
}

function hideGlobalError() {
  document.getElementById("global-error").style.display = "none";
}

let toastTimer = null;
function toast(msg, type) {
  if (toastTimer) {
    clearTimeout(toastTimer);
    document.querySelector(".toast-banner")?.remove();
  }
  const el = document.createElement("div");
  el.className = `toast-banner toast-${type}`;
  el.textContent = msg;
  document.body.appendChild(el);
  toastTimer = setTimeout(() => el.remove(), 3000);
}

function escHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function escAttr(str) {
  return escHtml(str).replace(/'/g, "&#39;");
}

async function reloadActiveView() {
  if (activeView === "dashboard") await loadDashboard();
  else if (activeView === "sessions") await loadSessions();
}

await bridge.ready();
renderStatic();
bridge.onContext(() => {
  renderStatic();
  reloadActiveView();
});

await reloadActiveView();

refreshTimer = setInterval(() => {
  if (activeView === "dashboard") loadDashboard();
  else if (activeView === "sessions" && sessionsLoaded) loadSessions();
}, 30000);

window.addEventListener("beforeunload", () => {
  if (refreshTimer) clearInterval(refreshTimer);
});
