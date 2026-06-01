const bridge = window.AstrBotPluginPage || null;
const I18N = "pages.webui.";
const VISIT_KEY = "astrbot-proactive-webui-seen";

// 占位符目录由后端注册表提供（placeholders/list），前端不再硬编码 token 清单。
let placeholderGroups = [];
let placeholdersLoaded = false;
let placeholdersPromise = null;

let activeView = "dashboard";
let sessionsLoaded = false;
let sessions = [];
let sessionFilter = "";
let schedulesLoaded = false;
let schedulesPromise = null;
let aiSchedules = [];
let refreshTimer = null;
let dashboardPromise = null;
let sessionsPromise = null;

// 时间表（日历事项）状态
let calendarLoaded = false;
let calendarPromise = null;
let calendarEvents = [];
let calendarEnabled = false;
let calendarSeparator = "、";
let calendarEmptyText = "";
const _now = new Date();
let calViewYear = _now.getFullYear();
let calViewMonth = _now.getMonth() + 1; // 1-12
let calSelected = null; // { year, month, day }
let calEditingId = null;

// 时间表 · AI 生成状态
let calAiOptionsLoaded = false;
let calAiGenerating = false;
let calAiGeneratedEvents = [];

applyVisitState();

function t(key, fallback) {
  return bridge?.t?.(I18N + key, fallback) || fallback;
}

function getLocale() {
  return bridge?.getLocale?.() || document.documentElement.lang || "zh-CN";
}

function apiLocale() {
  return { locale: getLocale() };
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
  const locale = getLocale();
  const ctx = bridge?.getContext?.() || {};
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

  document.getElementById("nav-label-schedules").textContent =
    t("tab_schedules", "AI 约定");
  document.getElementById("page-title-schedules").textContent =
    t("tab_schedules", "AI 约定");
  document.getElementById("hdr-schedule-list").textContent =
    t("schedule_list", "约定任务列表");
  document.getElementById("btn-detail-close").textContent =
    t("btn_close", "关闭");

  document.getElementById("nav-label-placeholders").textContent =
    t("tab_placeholders", "占位符");
  document.getElementById("page-title-placeholders").textContent =
    t("tab_placeholders", "占位符");
  document.getElementById("placeholders-subtitle").textContent =
    t("placeholders_subtitle", "点击任意占位符即可复制到剪贴板，粘贴进配置模板使用");

  renderCalendarStatic();

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
  renderPlaceholders();
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
    if (view === "schedules") {
      input.placeholder = t("search_hint_schedules", "此页面不支持搜索");
    } else if (view === "placeholders") {
      input.placeholder = t("search_hint_placeholders", "此页面不支持搜索");
    } else if (view === "calendar") {
      input.placeholder = t("search_hint_calendar", "此页面不支持搜索");
    } else {
      input.placeholder = t("search_hint_dashboard", "切换到会话页后可搜索");
    }
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
    (view === "dashboard" || view === "schedules") ? "inline-flex" : "none";
  document.getElementById("btn-add-session").style.display =
    view === "sessions" ? "inline-flex" : "none";

  updateSearchForView(view);
  closeSidebar();
  hideGlobalError();

  if (view === "sessions" && !sessionsLoaded) {
    loadSessions();
  } else if (view === "sessions" && sessionsLoaded) {
    applySessionFilter();
  } else if (view === "schedules" && !schedulesLoaded) {
    loadAiSchedules();
  } else if (view === "schedules" && schedulesLoaded) {
    renderAiSchedules(aiSchedules);
  } else if (view === "placeholders" && !placeholdersLoaded) {
    loadPlaceholders();
  } else if (view === "calendar" && !calendarLoaded) {
    loadCalendar();
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
    hideSessionDetail();
    hideConfirmDialog(false);
    hideCalendarDay();
    closeSidebar();
  }
  if (
    activeView === "calendar" &&
    calendarEnabled &&
    !isCalendarDayOpen() &&
    (e.key === "ArrowLeft" || e.key === "ArrowRight")
  ) {
    const tag = (e.target.tagName || "").toLowerCase();
    if (tag === "input" || tag === "select" || tag === "textarea") return;
    e.preventDefault();
    shiftCalendarMonth(e.key === "ArrowLeft" ? -1 : 1);
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

document.getElementById("btn-refresh").addEventListener("click", () => reloadActiveView());
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

async function loadPlaceholders() {
  if (placeholdersPromise) return placeholdersPromise;
  placeholdersPromise = (async () => {
    const container = document.getElementById("placeholders-container");
    if (container && !placeholdersLoaded) container.innerHTML = loadingHtml();
    try {
      const data = await bridge.apiGet("placeholders/list", apiLocale());
      if (!data.success) throw new Error(data.error || t("err_unknown", "未知错误"));
      placeholderGroups = data.groups || [];
      placeholdersLoaded = true;
      renderPlaceholders();
    } catch (err) {
      if (container) {
        container.innerHTML = `
        <div class="empty-state">
          <p>${escHtml(t("load_placeholders_failed", "占位符加载失败，请切换页面后重试"))}</p>
        </div>`;
      }
    } finally {
      placeholdersPromise = null;
    }
  })();
  return placeholdersPromise;
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
        : `<button type="button" class="btn btn-primary" data-action="add-session">${escHtml(t("btn_add_first", "添加第一个会话"))}</button>`,
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
    <tr class="row-clickable" data-detail-session-id="${escAttr(s.session_id)}">
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
      locale: getLocale(),
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
  const addBtn = e.target.closest('[data-action="add-session"]');
  if (addBtn) {
    showAddDialog();
    return;
  }
  const removeBtn = e.target.closest("[data-session-id]");
  if (removeBtn) {
    confirmRemove(removeBtn.dataset.sessionId);
    return;
  }
  const row = e.target.closest("[data-detail-session-id]");
  if (row) {
    const session = sessions.find(s => s.session_id === row.dataset.detailSessionId);
    if (session) showSessionDetail(session);
  }
});

async function loadAiSchedules() {
  if (schedulesPromise) return schedulesPromise;
  schedulesPromise = (async () => {
    document.getElementById("schedules-container").innerHTML = loadingHtml();
    try {
      const data = await bridge.apiGet("ai-schedules/list", apiLocale());
      if (!data.success) throw new Error(data.error || t("err_unknown", "未知错误"));
      aiSchedules = data.schedules || [];
      schedulesLoaded = true;
      renderAiSchedules(aiSchedules);
      hideGlobalError();
    } catch (err) {
      showGlobalError(t("err_schedules_load", "约定任务加载失败：") + err.message);
      document.getElementById("schedules-container").innerHTML = `
        <div class="empty-state">
          <p>${escHtml(t("load_schedules_failed", "加载失败，请刷新重试"))}</p>
        </div>`;
    } finally {
      schedulesPromise = null;
    }
  })();
  return schedulesPromise;
}

function renderAiSchedules(list) {
  if (list.length === 0) {
    document.getElementById("schedules-container").innerHTML = emptyStateHtml(
      t("empty_schedules_title", "暂无 AI 约定任务"),
      escHtml(t("empty_schedules_desc", "当 AI 在对话中约定了具体时间，任务会自动出现在此处")),
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
      <td>
        <code class="session-id-cell">${escHtml(_truncateSessionId(s.session_id))}</code>
        <span class="badge badge-secondary">${escHtml(platformLabel(s.platform))}</span>
      </td>
      <td>
        ${s.fire_soon
          ? `<span class="text-success">${escHtml(s.time_display)}</span>`
          : `<span>${escHtml(s.time_display)}</span>`}
      </td>
      <td><span class="text-note">${escHtml(s.fire_time || "—")}</span></td>
      <td class="cell-prompt">
        ${s.follow_up_prompt
          ? `<button type="button" class="prompt-preview-btn" data-full-prompt="${escAttr(s.follow_up_prompt)}">${escHtml(s.follow_up_prompt.length > 36 ? s.follow_up_prompt.slice(0, 36) + "…" : s.follow_up_prompt)}</button>`
          : `<span class="text-muted">—</span>`}
      </td>
      <td><span class="text-note">${escHtml(s.created_at || "—")}</span></td>
      <td>
        <button type="button" class="btn-text"
          data-cancel-session="${escAttr(s.session_id)}"
          data-cancel-task-id="${escAttr(s.task_id || "")}"
          data-cancel-fire="${escAttr(s.fire_time)}"
          title="${escAttr(t("cancel_title", "取消"))}">${escHtml(t("cancel_title", "取消"))}</button>
      </td>
    </tr>`).join("");

  document.getElementById("schedules-container").innerHTML = `
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>${escHtml(t("th_session", "会话"))}</th>
            <th>${escHtml(t("th_time_left", "倒计时"))}</th>
            <th>${escHtml(t("th_fire_time", "执行时间"))}</th>
            <th>${escHtml(t("th_prompt", "触发提示词"))}</th>
            <th>${escHtml(t("th_created", "创建时间"))}</th>
            <th>${escHtml(t("th_actions", "操作"))}</th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
    </div>`;
}

function _truncateSessionId(sessionId) {
  const parts = sessionId.split(":");
  if (parts.length >= 3) {
    const raw = parts.slice(2).join(":");
    return `${parts[0]}:${parts[1]}:${raw.length > 10 ? raw.slice(0, 10) + "…" : raw}`;
  }
  return sessionId.length > 24 ? sessionId.slice(0, 24) + "…" : sessionId;
}

function renderPlaceholders() {
  const container = document.getElementById("placeholders-container");
  if (!container) return;

  if (!placeholdersLoaded) {
    container.innerHTML = loadingHtml();
    return;
  }

  const copyHint = t("placeholders_copy_hint", "点击复制");
  const groupsHtml = placeholderGroups.map(group => {
    const titleKey = "placeholders_group_" + group.key;
    const hintKey = titleKey + "_hint";
    const chips = (group.tokens || []).map(item => {
      const token = item.token;
      const desc = t("ph_desc_" + token, item.desc || "");
      const full = `{${token}}`;
      return `
        <button type="button" class="ph-chip" data-token="${escAttr(token)}" title="${escAttr(copyHint + " " + full)}">
          <code class="ph-chip-token">${escHtml(full)}</code>
          <span class="ph-chip-desc">${escHtml(desc)}</span>
        </button>`;
    }).join("");

    return `
      <article class="panel ph-group">
        <header class="panel-head ph-group-head">
          <h3 class="panel-title">${escHtml(t(titleKey, group.key))}</h3>
          <span class="ph-group-hint">${escHtml(t(hintKey, ""))}</span>
        </header>
        <div class="panel-body ph-chip-grid">${chips}</div>
      </article>`;
  }).join("");

  container.innerHTML = groupsHtml;
}

document.getElementById("placeholders-container").addEventListener("click", e => {
  const chip = e.target.closest("[data-token]");
  if (chip) copyPlaceholder(chip);
});

async function copyPlaceholder(chip) {
  const token = chip.dataset.token;
  const full = `{${token}}`;
  let copied = false;
  try {
    await navigator.clipboard.writeText(full);
    copied = true;
  } catch {
    copied = fallbackCopyText(full);
  }
  if (copied) {
    toast(t("toast_copied", "已复制 {token}").replace("{token}", full), "success");
    chip.classList.add("ph-chip-copied");
    setTimeout(() => chip.classList.remove("ph-chip-copied"), 900);
  } else {
    toast(t("toast_copy_failed", "复制失败，请手动选择"), "error");
  }
}

function fallbackCopyText(text) {
  const ta = document.createElement("textarea");
  ta.value = text;
  ta.style.position = "fixed";
  ta.style.opacity = "0";
  document.body.appendChild(ta);
  ta.select();
  let ok = false;
  try {
    ok = document.execCommand("copy");
  } catch {
    ok = false;
  }
  document.body.removeChild(ta);
  return ok;
}

document.getElementById("schedules-container").addEventListener("click", e => {
  const cancelBtn = e.target.closest("[data-cancel-session]");
  if (cancelBtn) {
    cancelSchedule(
      cancelBtn.dataset.cancelSession,
      cancelBtn.dataset.cancelFire,
      cancelBtn.dataset.cancelTaskId,
    );
    return;
  }
  const promptBtn = e.target.closest("[data-full-prompt]");
  if (promptBtn) {
    showPromptDetail(promptBtn.dataset.fullPrompt);
  }
});

async function cancelSchedule(sessionId, fireTime, taskId) {
  const ok = await showConfirm({
    title: t("confirm_cancel_schedule_title", "取消约定任务"),
    message: t("confirm_cancel_schedule", "确定要取消这个约定任务吗？"),
    confirmText: t("btn_confirm", "确定"),
  });
  if (!ok) return;
  try {
    const payload = {
      session_id: sessionId,
      locale: getLocale(),
    };
    if (taskId) payload.task_id = taskId;
    else payload.fire_time = fireTime;

    const data = await bridge.apiPost("ai-schedules/cancel", payload);
    if (!data.success) throw new Error(data.error || t("toast_cancel_failed", "取消失败"));
    toast(data.message || t("toast_schedule_cancelled", "约定任务已取消"), "success");
    schedulesLoaded = false;
    await loadAiSchedules();
    if (activeView === "dashboard") await loadDashboard();
    if (sessionsLoaded) {
      sessionsLoaded = false;
      await loadSessions();
    }
  } catch (err) {
    toast(err.message, "error");
  }
}

window.showPromptDetail = function (promptText) {
  document.getElementById("detail-title").textContent = t("prompt_detail_title", "触发提示词");
  document.getElementById("detail-body").innerHTML = `
    <div class="detail-section">
      <div class="detail-section-title">${escHtml(t("prompt_full_content", "完整内容"))}</div>
      <div class="message-preview prompt-full-text">${escHtml(promptText)}</div>
    </div>`;
  document.getElementById("session-detail-dialog").style.display = "flex";
};

window.showSessionDetail = function (session) {
  document.getElementById("detail-title").textContent = t("detail_title", "会话详情");
  document.getElementById("detail-body").innerHTML = renderSessionDetailHtml(session);
  document.getElementById("session-detail-dialog").style.display = "flex";
};

window.hideSessionDetail = function () {
  document.getElementById("session-detail-dialog").style.display = "none";
};

document.getElementById("btn-detail-close").addEventListener("click", hideSessionDetail);
document.getElementById("session-detail-dialog").addEventListener("click", e => {
  if (e.target.id === "session-detail-dialog") hideSessionDetail();
});

let confirmResolver = null;

function hideConfirmDialog(result) {
  document.getElementById("confirm-dialog").style.display = "none";
  if (confirmResolver) {
    const resolve = confirmResolver;
    confirmResolver = null;
    resolve(result);
  }
}

function showConfirm({ title, message, confirmText, danger = true }) {
  if (confirmResolver) hideConfirmDialog(false);
  document.getElementById("confirm-title").textContent = title || "";
  document.getElementById("confirm-message").textContent = message || "";
  document.getElementById("btn-confirm-cancel").textContent = t("btn_cancel", "取消");
  const okBtn = document.getElementById("btn-confirm-ok");
  okBtn.textContent = confirmText || t("btn_confirm", "确定");
  okBtn.className = `btn ${danger ? "btn-danger" : "btn-primary"}`;
  document.getElementById("confirm-dialog").style.display = "flex";
  setTimeout(() => okBtn.focus(), 50);
  return new Promise(resolve => {
    confirmResolver = resolve;
  });
}

document.getElementById("btn-confirm-cancel").addEventListener("click", () => hideConfirmDialog(false));
document.getElementById("btn-confirm-ok").addEventListener("click", () => hideConfirmDialog(true));
document.getElementById("confirm-dialog").addEventListener("click", e => {
  if (e.target.id === "confirm-dialog") hideConfirmDialog(false);
});

function renderSessionDetailHtml(s) {
  const failureHtml = s.consecutive_failures > 0
    ? `<span class="badge badge-warning">${s.consecutive_failures} ${escHtml(t("label_failure_count", "次失败"))}</span>`
    : `<span class="text-muted">0</span>`;

  const messageHtml = s.last_proactive_message
    ? `<div class="message-preview">${escHtml(s.last_proactive_message)}</div>`
    : `<span class="text-muted">${escHtml(t("no_message_preview", "暂无记录"))}</span>`;

  const usernameRow = s.username ? `
    <div class="info-row">
      <span class="info-label">${escHtml(t("th_user", "用户"))}</span>
      <span class="info-value">${escHtml(s.username)}</span>
    </div>` : "";

  const aiTaskRow = s.ai_task_count > 0 ? `
    <div class="info-row">
      <span class="info-label">${escHtml(t("label_ai_tasks", "AI 约定"))}</span>
      <span class="badge badge-info">${s.ai_task_count} ${escHtml(t("label_task_unit", "个"))}</span>
    </div>` : "";

  return `
    <div class="detail-section">
      <div class="detail-section-title">${escHtml(t("detail_basic_info", "基本信息"))}</div>
      <div class="info-row">
        <span class="info-label">${escHtml(t("th_session_id", "会话 ID"))}</span>
        <code style="font-size:0.75rem;word-break:break-all;max-width:60%">${escHtml(s.session_id)}</code>
      </div>
      <div class="info-row">
        <span class="info-label">${escHtml(t("th_platform", "平台"))}</span>
        <span class="info-value">${escHtml(s.platform)} · ${escHtml(s.chat_type)}</span>
      </div>
      ${usernameRow}
    </div>
    <div class="detail-section">
      <div class="detail-section-title">${escHtml(t("detail_run_status", "运行状态"))}</div>
      <div class="info-row">
        <span class="info-label">${escHtml(t("th_status", "状态"))}</span>
        <span class="badge ${s.status === "active" ? "badge-success" : "badge-warning"}">${escHtml(s.status_display)}</span>
      </div>
      <div class="info-row">
        <span class="info-label">${escHtml(t("th_next_send", "下次发送"))}</span>
        <span>${escHtml(s.next_fire_display)}</span>
      </div>
      <div class="info-row">
        <span class="info-label">${escHtml(t("th_unreplied", "未回复"))}</span>
        <span>${s.unreplied_count > 0
          ? `<span class="badge badge-warning">${s.unreplied_count}</span>`
          : `<span class="text-muted">0</span>`}</span>
      </div>
      <div class="info-row">
        <span class="info-label">${escHtml(t("label_failures", "连续失败"))}</span>
        <span>${failureHtml}</span>
      </div>
      ${aiTaskRow}
    </div>
    <div class="detail-section">
      <div class="detail-section-title">${escHtml(t("detail_last_send", "最后发送"))}</div>
      <div class="info-row">
        <span class="info-label">${escHtml(t("th_last_send", "发送时间"))}</span>
        <span class="text-note">${escHtml(s.last_sent_time)}</span>
      </div>
      <div class="info-row info-row-col">
        <span class="info-label">${escHtml(t("label_last_message", "消息内容"))}</span>
        ${messageHtml}
      </div>
    </div>`;
}

async function confirmRemove(sessionId) {
  const msg = t("confirm_remove", '确定要移除会话 "{session_id}" 吗？').replace(
    "{session_id}",
    sessionId,
  );
  const ok = await showConfirm({
    title: t("confirm_remove_title", "移除会话"),
    message: msg,
    confirmText: t("remove_title", "移除"),
  });
  if (!ok) return;
  try {
    const data = await bridge.apiPost("sessions/remove", {
      session_id: sessionId,
      locale: getLocale(),
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
  else if (activeView === "sessions") {
    sessionsLoaded = false;
    await loadSessions();
  } else if (activeView === "schedules") {
    schedulesLoaded = false;
    await loadAiSchedules();
  } else if (activeView === "placeholders") {
    placeholdersLoaded = false;
    await loadPlaceholders();
  } else if (activeView === "calendar") {
    calendarLoaded = false;
    await loadCalendar();
  }
}

/* ==================== 时间表（日历事项） ==================== */

const CAL_REPEAT_VALUES = [0, 1, 2, 3, 4, -1];

function normRepeat(r) {
  const v = parseInt(r, 10);
  if (v === -1) return -1;
  if (v >= 0 && v <= 4) return v;
  return 0;
}

function repeatLabel(repeat) {
  const v = normRepeat(repeat);
  if (v === -1) return t("calendar_repeat_forever", "每年重复（永久）");
  if (v === 0) return t("calendar_repeat_none", "不重复（仅当年）");
  return t("calendar_repeat_" + v, `重复 ${v} 年`);
}

function eventActiveInYear(ev, year) {
  const repeat = normRepeat(ev.repeat);
  if (repeat === -1) return true;
  const base = parseInt(ev.year, 10);
  if (!Number.isFinite(base)) return false;
  return base <= year && year <= base + repeat;
}

function fmt(template, vars) {
  return String(template).replace(/\{(\w+)\}/g, (_, k) =>
    Object.prototype.hasOwnProperty.call(vars, k) ? vars[k] : `{${k}}`,
  );
}

function renderCalendarStatic() {
  const set = (id, key, fallback) => {
    const el = document.getElementById(id);
    if (el) el.textContent = t(key, fallback);
  };
  set("nav-label-calendar", "tab_calendar", "时间表");
  set("page-title-calendar", "tab_calendar", "时间表");
  set("calendar-subtitle", "calendar_subtitle", "为日期添加节日或事项");
  set("calendar-enable-label", "calendar_enable_label", "启用时间表功能");
  set("calendar-enable-hint", "calendar_enable_hint", "");
  set("cal-today", "calendar_today_btn", "回到今天");
  set("cal-import", "calendar_import", "导入");
  set("cal-export", "calendar_export", "导出");
  set("cal-clear-month", "calendar_clear_month", "清除本月");
  set("cal-clear-year", "calendar_clear_year", "清除本年");
  set("cal-clear-all", "calendar_clear_all", "清除全部");
  set("cal-day-close", "btn_close", "关闭");
  set("cal-day-save", "btn_save", "保存");
  set("cal-form-text-label", "calendar_event_text_label", "事项内容");
  set("cal-form-year-label", "calendar_year_label", "基准年");
  set("cal-form-repeat-label", "calendar_repeat_label", "重复");
  set("cal-form-year-hint", "calendar_year_forever_hint", "");
  set("calendar-display-title", "calendar_display_settings", "显示设置");
  set("cal-sep-label", "calendar_separator_label", "事项分隔符");
  set("cal-empty-label", "calendar_empty_text_label", "无事项默认文本");
  set("cal-sep-hint", "calendar_separator_hint", "");
  set("cal-empty-hint", "calendar_empty_text_hint", "");
  set("cal-settings-save", "btn_save", "保存");
  set("cal-ai-title", "calendar_ai_title", "AI 生成时间表");
  set("cal-ai-subtitle", "calendar_ai_subtitle", "输入主题，让 AI 一次性生成整套节日 / 纪念日");
  set("cal-ai-provider-label", "calendar_ai_provider_label", "模型");
  set("cal-ai-provider-hint", "calendar_ai_provider_hint", "");
  set("cal-ai-prompt-label", "calendar_ai_prompt_label", "主题提示词");
  set("cal-ai-prompt-hint", "calendar_ai_prompt_hint", "");
  set("cal-ai-generate", "calendar_ai_generate_btn", "生成");
  set("cal-ai-apply-merge", "calendar_ai_apply_merge", "合并应用");
  set("cal-ai-apply-replace", "calendar_ai_apply_replace", "替换应用");
  const aiPromptInput = document.getElementById("cal-ai-prompt-input");
  if (aiPromptInput) {
    aiPromptInput.placeholder = t(
      "calendar_ai_prompt_placeholder",
      "如：异世界/魔法/节日，或 现代都市/节日",
    );
  }

  const prevBtn = document.getElementById("cal-prev");
  if (prevBtn) prevBtn.title = t("calendar_prev_month", "上个月");
  const nextBtn = document.getElementById("cal-next");
  if (nextBtn) nextBtn.title = t("calendar_next_month", "下个月");
  const textInput = document.getElementById("cal-form-text");
  if (textInput) {
    textInput.placeholder = t("calendar_event_text_placeholder", "如：春节");
  }

  const repeatSel = document.getElementById("cal-form-repeat");
  if (repeatSel) {
    repeatSel.innerHTML = CAL_REPEAT_VALUES.map(
      v => `<option value="${v}">${escHtml(repeatLabel(v))}</option>`,
    ).join("");
  }

  // 已渲染过日历时，刷新动态文案（月份标题、星期、网格）
  if (calendarLoaded) renderCalendar();
}

async function loadCalendar() {
  if (calendarPromise) return calendarPromise;
  calendarPromise = (async () => {
    try {
      const data = await bridge.apiGet("calendar/data", apiLocale());
      if (!data.success) throw new Error(data.error || t("err_unknown", "未知错误"));
      calendarEvents = Array.isArray(data.events) ? data.events : [];
      calendarEnabled = !!data.enabled;
      calendarSeparator = typeof data.separator === "string" ? data.separator : "、";
      calendarEmptyText = typeof data.empty_text === "string" ? data.empty_text : "";
      calendarLoaded = true;
      renderCalendar();
      hideGlobalError();
    } catch (err) {
      showGlobalError(t("err_calendar_load", "时间表加载失败：") + err.message);
      console.error(err);
    } finally {
      calendarPromise = null;
    }
  })();
  return calendarPromise;
}

function renderCalendar() {
  const toggle = document.getElementById("calendar-enable-toggle");
  if (toggle) toggle.checked = calendarEnabled;

  const body = document.getElementById("calendar-body");
  const disabled = document.getElementById("calendar-disabled-state");
  if (calendarEnabled) {
    if (body) body.style.display = "";
    if (disabled) disabled.style.display = "none";
    const sepInput = document.getElementById("cal-sep-input");
    if (sepInput) sepInput.value = calendarSeparator;
    const emptyInput = document.getElementById("cal-empty-input");
    if (emptyInput) emptyInput.value = calendarEmptyText;
    renderCalendarGrid();
    loadCalendarAiOptions();
  } else {
    if (body) body.style.display = "none";
    if (disabled) {
      disabled.style.display = "";
      disabled.innerHTML = emptyStateHtml(
        t("calendar_disabled_title", "时间表功能未启用"),
        escHtml(t("calendar_disabled_desc", "打开上方开关即可编辑日历事项")),
      );
    }
  }
}

function renderCalendarGrid() {
  const title = document.getElementById("calendar-month-title");
  if (title) {
    title.textContent = fmt(t("calendar_month_label", "{year} 年 {month} 月"), {
      year: calViewYear,
      month: calViewMonth,
    });
  }

  const wd = document.getElementById("calendar-weekdays");
  if (wd) {
    wd.innerHTML = "";
    for (let i = 0; i < 7; i++) {
      const cell = document.createElement("div");
      cell.className = "calendar-weekday";
      cell.textContent = t("calendar_weekday_" + i, String(i));
      wd.appendChild(cell);
    }
  }

  const grid = document.getElementById("calendar-grid");
  if (!grid) return;
  grid.innerHTML = "";

  const y = calViewYear;
  const m = calViewMonth;
  const firstDow = (new Date(y, m - 1, 1).getDay() + 6) % 7; // 0=周一
  const daysInMonth = new Date(y, m, 0).getDate();
  const totalCells = Math.ceil((firstDow + daysInMonth) / 7) * 7;

  const today = new Date();
  const moreText = t("calendar_more_events", "+{count}");

  for (let i = 0; i < totalCells; i++) {
    const dayNum = i - firstDow + 1;
    if (dayNum < 1 || dayNum > daysInMonth) {
      const empty = document.createElement("div");
      empty.className = "calendar-cell is-outside";
      grid.appendChild(empty);
      continue;
    }

    const cell = document.createElement("button");
    cell.type = "button";
    cell.className = "calendar-cell";
    cell.dataset.day = String(dayNum);
    if (
      today.getFullYear() === y &&
      today.getMonth() + 1 === m &&
      today.getDate() === dayNum
    ) {
      cell.classList.add("is-today");
    }

    const dateEl = document.createElement("div");
    dateEl.className = "calendar-cell-date";
    dateEl.textContent = String(dayNum);
    cell.appendChild(dateEl);

    const dayEvents = calendarEvents.filter(
      ev => ev.month === m && ev.day === dayNum && eventActiveInYear(ev, y),
    );
    if (dayEvents.length) {
      const list = document.createElement("div");
      list.className = "calendar-cell-events";
      dayEvents.slice(0, 2).forEach(ev => {
        const chip = document.createElement("div");
        chip.className = "calendar-event-chip";
        chip.textContent = ev.text;
        chip.title = ev.text;
        list.appendChild(chip);
      });
      if (dayEvents.length > 2) {
        const more = document.createElement("div");
        more.className = "calendar-event-more";
        more.textContent = fmt(moreText, { count: dayEvents.length - 2 });
        list.appendChild(more);
      }
      cell.appendChild(list);
    }

    cell.addEventListener("click", () => openCalendarDay(y, m, dayNum));
    grid.appendChild(cell);
  }
}

function shiftCalendarMonth(delta) {
  let m = calViewMonth + delta;
  let y = calViewYear;
  while (m < 1) {
    m += 12;
    y -= 1;
  }
  while (m > 12) {
    m -= 12;
    y += 1;
  }
  calViewMonth = m;
  calViewYear = y;
  renderCalendarGrid();
}

function gotoCalendarToday() {
  const now = new Date();
  calViewYear = now.getFullYear();
  calViewMonth = now.getMonth() + 1;
  renderCalendarGrid();
}

async function setCalendarEnabled(enabled) {
  try {
    const data = await bridge.apiPost("calendar/enabled", {
      enabled,
      locale: getLocale(),
    });
    if (!data.success) throw new Error(data.error || t("err_unknown", "未知错误"));
    calendarEnabled = !!data.enabled;
    renderCalendar();
    if (activeView === "dashboard") loadDashboard();
  } catch (err) {
    toast(err.message, "error");
    const toggle = document.getElementById("calendar-enable-toggle");
    if (toggle) toggle.checked = calendarEnabled;
  }
}

function isCalendarDayOpen() {
  const dlg = document.getElementById("calendar-day-dialog");
  return !!dlg && dlg.style.display === "flex";
}

function openCalendarDay(year, month, day) {
  calSelected = { year, month, day };
  calEditingId = null;
  document.getElementById("cal-day-title").textContent = fmt(
    t("calendar_day_title", "{month} 月 {day} 日 · 事项"),
    { month, day },
  );
  renderCalDayEvents();
  resetCalForm();
  document.getElementById("calendar-day-dialog").style.display = "flex";
  setTimeout(() => document.getElementById("cal-form-text")?.focus(), 50);
}

function hideCalendarDay() {
  const dlg = document.getElementById("calendar-day-dialog");
  if (dlg) dlg.style.display = "none";
  calEditingId = null;
}

function dayEventsForSelected() {
  if (!calSelected) return [];
  const { month, day } = calSelected;
  return calendarEvents.filter(ev => ev.month === month && ev.day === day);
}

function renderCalDayEvents() {
  const container = document.getElementById("cal-day-events");
  if (!container) return;
  const events = dayEventsForSelected();
  if (!events.length) {
    container.innerHTML = `<div class="cal-day-empty">${escHtml(
      t("calendar_no_events", "这一天还没有事项"),
    )}</div>`;
    return;
  }
  container.innerHTML = events
    .map(ev => {
      const meta = `${escHtml(String(ev.year))} · ${escHtml(repeatLabel(ev.repeat))}`;
      return `
        <div class="cal-day-event-row">
          <div class="cal-day-event-main">
            <div class="cal-day-event-text">${escHtml(ev.text)}</div>
            <div class="cal-day-event-meta">${meta}</div>
          </div>
          <div class="cal-row-actions">
            <button type="button" class="btn btn-ghost btn-sm" onclick="editCalEvent('${escAttr(
              ev.id,
            )}')">${escHtml(t("btn_edit", "编辑"))}</button>
            <button type="button" class="btn btn-danger btn-sm" onclick="deleteCalEvent('${escAttr(
              ev.id,
            )}')">${escHtml(t("btn_delete", "删除"))}</button>
          </div>
        </div>`;
    })
    .join("");
}

// 「每年重复（永久）」时基准年无意义：禁用输入并给出提示
function applyRepeatYearState() {
  const repeatSel = document.getElementById("cal-form-repeat");
  const yearInput = document.getElementById("cal-form-year");
  const yearHint = document.getElementById("cal-form-year-hint");
  if (!repeatSel || !yearInput) return;
  const forever = parseInt(repeatSel.value, 10) === -1;
  yearInput.disabled = forever;
  if (yearHint) yearHint.style.display = forever ? "" : "none";
}

function resetCalForm() {
  calEditingId = null;
  const textInput = document.getElementById("cal-form-text");
  const yearInput = document.getElementById("cal-form-year");
  const repeatSel = document.getElementById("cal-form-repeat");
  if (textInput) textInput.value = "";
  if (yearInput) yearInput.value = calSelected ? calSelected.year : calViewYear;
  if (repeatSel) repeatSel.value = "0";
  applyRepeatYearState();
  const saveBtn = document.getElementById("cal-day-save");
  if (saveBtn) saveBtn.textContent = t("btn_save", "保存");
}

window.editCalEvent = function (id) {
  const ev = calendarEvents.find(e => e.id === id);
  if (!ev) return;
  calEditingId = id;
  document.getElementById("cal-form-text").value = ev.text;
  document.getElementById("cal-form-year").value = ev.year;
  document.getElementById("cal-form-repeat").value = String(normRepeat(ev.repeat));
  applyRepeatYearState();
  document.getElementById("cal-form-text")?.focus();
};

async function saveCalendarSettings() {
  const sepInput = document.getElementById("cal-sep-input");
  const emptyInput = document.getElementById("cal-empty-input");
  try {
    const data = await bridge.apiPost("calendar/settings", {
      separator: sepInput ? sepInput.value : calendarSeparator,
      empty_text: emptyInput ? emptyInput.value : calendarEmptyText,
      locale: getLocale(),
    });
    if (!data.success) {
      throw new Error(
        data.error || t("toast_calendar_settings_failed", "显示设置保存失败"),
      );
    }
    calendarSeparator = typeof data.separator === "string" ? data.separator : "";
    calendarEmptyText = typeof data.empty_text === "string" ? data.empty_text : "";
    toast(t("toast_calendar_settings_saved", "显示设置已保存"), "success");
  } catch (err) {
    toast(err.message, "error");
  }
}

window.deleteCalEvent = async function (id) {
  try {
    const data = await bridge.apiPost("calendar/event/delete", {
      id,
      locale: getLocale(),
    });
    if (!data.success) {
      throw new Error(data.error || t("toast_calendar_delete_failed", "删除失败"));
    }
    calendarEvents = calendarEvents.filter(e => e.id !== id);
    if (calEditingId === id) resetCalForm();
    renderCalDayEvents();
    renderCalendarGrid();
    toast(data.message || t("toast_calendar_event_deleted", "事项已删除"), "success");
  } catch (err) {
    toast(err.message, "error");
  }
};

async function saveCalDayEvent() {
  if (!calSelected) return;
  const textInput = document.getElementById("cal-form-text");
  const text = (textInput?.value || "").trim();
  if (!text) {
    toast(t("toast_event_text_required", "请输入事项内容"), "error");
    textInput?.focus();
    return;
  }
  const year = parseInt(document.getElementById("cal-form-year").value, 10);
  const repeat = parseInt(document.getElementById("cal-form-repeat").value, 10);
  const payload = {
    text,
    year: Number.isFinite(year) ? year : calSelected.year,
    month: calSelected.month,
    day: calSelected.day,
    repeat,
    locale: getLocale(),
  };
  if (calEditingId) payload.id = calEditingId;

  try {
    const data = await bridge.apiPost("calendar/event/save", payload);
    if (!data.success || !data.event) {
      throw new Error(data.error || t("toast_calendar_save_failed", "保存失败"));
    }
    if (calEditingId) {
      const idx = calendarEvents.findIndex(e => e.id === calEditingId);
      if (idx >= 0) calendarEvents[idx] = data.event;
    } else {
      calendarEvents.push(data.event);
    }
    resetCalForm();
    renderCalDayEvents();
    renderCalendarGrid();
    toast(data.message || t("toast_calendar_event_saved", "事项已保存"), "success");
  } catch (err) {
    toast(err.message, "error");
  }
}

async function clearCalendar(scope) {
  let message;
  if (scope === "month") {
    message = fmt(t("confirm_clear_month", "确定清除 {year} 年 {month} 月的全部事项吗？"), {
      year: calViewYear,
      month: calViewMonth,
    });
  } else if (scope === "year") {
    message = fmt(t("confirm_clear_year", "确定清除 {year} 年的全部事项吗？"), {
      year: calViewYear,
    });
  } else {
    message = t("confirm_clear_all", "确定清除全部时间表事项吗？此操作不可撤销。");
  }
  const ok = await showConfirm({
    title: t("confirm_clear_title", "清除时间表事项"),
    message,
    confirmText: t("btn_delete", "删除"),
  });
  if (!ok) return;

  try {
    const data = await bridge.apiPost("calendar/clear", {
      scope,
      year: calViewYear,
      month: calViewMonth,
      locale: getLocale(),
    });
    if (!data.success) {
      throw new Error(data.error || t("toast_calendar_clear_failed", "清除失败"));
    }
    await loadCalendar();
    toast(data.message || t("toast_calendar_cleared", "已清除"), "success");
  } catch (err) {
    toast(err.message, "error");
  }
}

async function exportCalendar() {
  if (!calendarEvents.length) {
    toast(t("toast_calendar_export_empty", "暂无可导出的事项"), "error");
    return;
  }
  try {
    // 由后端用 PyYAML 渲染，保证与磁盘文件格式一致
    const data = await bridge.apiGet("calendar/export", apiLocale());
    if (!data.success || typeof data.content !== "string") {
      throw new Error(data.error || t("toast_calendar_export_failed", "导出失败"));
    }
    const blob = new Blob([data.content], { type: "application/x-yaml" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `calendar_data_${calViewYear}${String(calViewMonth).padStart(2, "0")}.yaml`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
    toast(t("toast_calendar_export_done", "已导出时间表"), "success");
  } catch (err) {
    toast(err.message, "error");
  }
}

async function importCalendarFile(file) {
  if (!file) return;
  let content;
  try {
    content = await file.text();
  } catch {
    toast(t("toast_calendar_import_bad_file", "文件格式不正确，无法导入"), "error");
    return;
  }
  if (!content.trim()) {
    toast(t("toast_calendar_import_bad_file", "文件格式不正确，无法导入"), "error");
    return;
  }

  // 询问合并 / 替换：确定=替换，取消=合并（YAML 由后端解析，前端不再预解析计数）
  const replace = await showConfirm({
    title: t("confirm_import_title", "导入时间表"),
    message: t(
      "confirm_import_replace",
      "导入文件将合并或替换现有时间表。选择「替换」将清空现有事项，选择「取消」可改用合并方式。是否替换？",
    ),
    confirmText: t("btn_replace", "替换"),
    danger: false,
  });
  const mode = replace ? "replace" : "merge";

  try {
    const data = await bridge.apiPost("calendar/import", {
      content,
      mode,
      locale: getLocale(),
    });
    if (!data.success) {
      throw new Error(data.error || t("toast_calendar_import_failed", "导入失败"));
    }
    calendarEvents = Array.isArray(data.events) ? data.events : [];
    renderCalendarGrid();
    toast(data.message || t("toast_calendar_imported", "已导入"), "success");
  } catch (err) {
    toast(err.message, "error");
  }
}

async function loadCalendarAiOptions() {
  if (calAiOptionsLoaded) return;
  try {
    const data = await bridge.apiGet("calendar/ai/options", apiLocale());
    if (!data.success) throw new Error(data.error || t("err_unknown", "未知错误"));
    calAiOptionsLoaded = true;
    populateAiProviders(
      Array.isArray(data.providers) ? data.providers : [],
      typeof data.provider_id === "string" ? data.provider_id : "",
    );
  } catch (err) {
    // 选项加载失败不阻塞时间表主功能，仅在控制台记录
    console.error("加载 AI 生成选项失败", err);
  }
}

function populateAiProviders(providers, selected) {
  const sel = document.getElementById("cal-ai-provider");
  if (!sel) return;
  const defaultLabel = t("calendar_ai_provider_default", "默认（主模型）");
  const opts = [`<option value="">${escHtml(defaultLabel)}</option>`];
  providers.forEach(p => {
    const id = p && typeof p.id === "string" ? p.id : "";
    if (!id) return;
    const model = p && typeof p.model === "string" && p.model ? ` (${p.model})` : "";
    opts.push(
      `<option value="${escAttr(id)}">${escHtml(id + model)}</option>`,
    );
  });
  sel.innerHTML = opts.join("");
  // 配置中指定的模型若在列表中则默认选中
  if (selected && providers.some(p => p && p.id === selected)) {
    sel.value = selected;
  } else {
    sel.value = "";
  }
}

function setAiGenerating(on) {
  calAiGenerating = on;
  const btn = document.getElementById("cal-ai-generate");
  if (btn) {
    btn.disabled = on;
    btn.textContent = on
      ? t("calendar_ai_generating", "生成中…")
      : t("calendar_ai_generate_btn", "生成");
  }
}

async function generateCalendarAi() {
  if (calAiGenerating) return;
  const promptInput = document.getElementById("cal-ai-prompt-input");
  const userPrompt = (promptInput?.value || "").trim();
  if (!userPrompt) {
    toast(t("toast_calendar_ai_prompt_required", "请输入主题提示词"), "error");
    promptInput?.focus();
    return;
  }
  const providerSel = document.getElementById("cal-ai-provider");
  const providerId = providerSel ? providerSel.value : "";

  setAiGenerating(true);
  try {
    const data = await bridge.apiPost("calendar/ai/generate", {
      user_prompt: userPrompt,
      provider_id: providerId,
      locale: getLocale(),
    });
    if (!data.success) {
      throw new Error(data.error || t("toast_calendar_ai_failed", "AI 生成失败"));
    }
    calAiGeneratedEvents = Array.isArray(data.events) ? data.events : [];
    renderAiPreview();
    if (!calAiGeneratedEvents.length) {
      toast(t("toast_calendar_ai_empty", "AI 未生成任何有效事项"), "error");
    } else {
      toast(
        data.message || t("toast_calendar_ai_generated", "已生成事项"),
        "success",
      );
    }
  } catch (err) {
    toast(err.message, "error");
  } finally {
    setAiGenerating(false);
  }
}

function renderAiPreview() {
  const result = document.getElementById("cal-ai-result");
  const preview = document.getElementById("cal-ai-preview");
  const titleEl = document.getElementById("cal-ai-result-title");
  if (!result || !preview) return;

  if (!calAiGeneratedEvents.length) {
    result.style.display = "none";
    preview.innerHTML = "";
    return;
  }

  result.style.display = "";
  if (titleEl) {
    titleEl.textContent = fmt(
      t("calendar_ai_result_title", "预览（{count} 条）"),
      { count: calAiGeneratedEvents.length },
    );
  }

  const sorted = [...calAiGeneratedEvents].sort(
    (a, b) => a.month - b.month || a.day - b.day,
  );
  preview.innerHTML = sorted
    .map(ev => {
      const date = fmt(t("calendar_ai_preview_date", "{month}/{day}"), {
        month: ev.month,
        day: ev.day,
      });
      return `
        <div class="cal-ai-preview-row">
          <span class="cal-ai-preview-date">${escHtml(date)}</span>
          <span class="cal-ai-preview-text">${escHtml(ev.text)}</span>
          <span class="cal-ai-preview-meta">${escHtml(repeatLabel(ev.repeat))}</span>
        </div>`;
    })
    .join("");
}

async function applyCalendarAi(mode) {
  if (!calAiGeneratedEvents.length) {
    toast(t("toast_calendar_ai_empty", "AI 未生成任何有效事项"), "error");
    return;
  }
  if (mode === "replace") {
    const ok = await showConfirm({
      title: t("confirm_ai_apply_title", "应用 AI 时间表"),
      message: t(
        "confirm_ai_apply_replace",
        "「替换应用」将清空现有全部事项并写入本次生成的事项，是否继续？",
      ),
      confirmText: t("calendar_ai_apply_replace", "替换应用"),
    });
    if (!ok) return;
  }

  try {
    const data = await bridge.apiPost("calendar/ai/apply", {
      events: calAiGeneratedEvents,
      mode,
      locale: getLocale(),
    });
    if (!data.success) {
      throw new Error(data.error || t("toast_calendar_ai_apply_failed", "应用失败"));
    }
    calendarEvents = Array.isArray(data.events) ? data.events : calendarEvents;
    calAiGeneratedEvents = [];
    renderAiPreview();
    renderCalendarGrid();
    const promptInput = document.getElementById("cal-ai-prompt-input");
    if (promptInput) promptInput.value = "";
    toast(data.message || t("toast_calendar_ai_applied", "已应用"), "success");
  } catch (err) {
    toast(err.message, "error");
  }
}

function bindCalendarEvents() {
  document.getElementById("cal-prev")?.addEventListener("click", () =>
    shiftCalendarMonth(-1),
  );
  document.getElementById("cal-next")?.addEventListener("click", () =>
    shiftCalendarMonth(1),
  );
  document.getElementById("cal-today")?.addEventListener("click", gotoCalendarToday);
  document
    .getElementById("calendar-enable-toggle")
    ?.addEventListener("change", e => setCalendarEnabled(e.target.checked));
  document.getElementById("cal-clear-month")?.addEventListener("click", () =>
    clearCalendar("month"),
  );
  document.getElementById("cal-clear-year")?.addEventListener("click", () =>
    clearCalendar("year"),
  );
  document.getElementById("cal-clear-all")?.addEventListener("click", () =>
    clearCalendar("all"),
  );
  document.getElementById("cal-export")?.addEventListener("click", exportCalendar);
  document.getElementById("cal-import")?.addEventListener("click", () =>
    document.getElementById("cal-import-file")?.click(),
  );
  document.getElementById("cal-import-file")?.addEventListener("change", e => {
    const file = e.target.files?.[0];
    importCalendarFile(file);
    e.target.value = "";
  });
  document.getElementById("cal-day-save")?.addEventListener("click", saveCalDayEvent);
  document.getElementById("cal-day-close")?.addEventListener("click", hideCalendarDay);
  document
    .getElementById("cal-form-repeat")
    ?.addEventListener("change", applyRepeatYearState);
  document
    .getElementById("cal-settings-save")
    ?.addEventListener("click", saveCalendarSettings);
  document.getElementById("calendar-day-dialog")?.addEventListener("click", e => {
    if (e.target.id === "calendar-day-dialog") hideCalendarDay();
  });
  document.getElementById("cal-form-text")?.addEventListener("keydown", e => {
    if (e.key === "Enter") {
      e.preventDefault();
      saveCalDayEvent();
    }
  });
  document
    .getElementById("cal-ai-generate")
    ?.addEventListener("click", generateCalendarAi);
  document
    .getElementById("cal-ai-apply-merge")
    ?.addEventListener("click", () => applyCalendarAi("merge"));
  document
    .getElementById("cal-ai-apply-replace")
    ?.addEventListener("click", () => applyCalendarAi("replace"));
  document
    .getElementById("cal-ai-prompt-input")
    ?.addEventListener("keydown", e => {
      if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
        e.preventDefault();
        generateCalendarAi();
      }
    });
}

bindCalendarEvents();

if (!bridge) {
  renderStatic();
  showGlobalError(t("err_bridge_missing", "WebUI 桥接环境未就绪，请从 AstrBot 插件页面打开。"));
  document.getElementById("btn-refresh").disabled = true;
  document.getElementById("btn-refresh-panel").disabled = true;
  document.getElementById("btn-add-session").disabled = true;
} else {
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
    else if (activeView === "schedules" && schedulesLoaded) loadAiSchedules();
  }, 30000);

  window.addEventListener("beforeunload", () => {
    if (refreshTimer) clearInterval(refreshTimer);
  });
}
