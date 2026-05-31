(function () {
  "use strict";

  const root = document.querySelector("[data-cloud-plan-root]");
  if (!root) return;

  const api = window.AdminApi || {};
  const escapeHtml = api.escapeHtml || ((value) => String(value || ""));
  const requestJson = api.requestJson || ((url, options) => fetch(url, options).then((response) => response.json()));
  const PAGE_SIZE = 50;
  const mode = root.dataset.pageMode || "list";
  const planId = root.dataset.planId || "";
  const adminActionToken = root.dataset.adminActionToken || "";
  const state = {
    plans: [],
    plan: null,
    recipients: [],
    recipientTotal: 0,
    recipientOffset: 0,
    currentRecipient: null,
    currentMessages: [],
  };

  function qs(selector) {
    return root.querySelector(selector);
  }

  function qsa(selector) {
    return Array.from(root.querySelectorAll(selector));
  }

  function text(selector, value) {
    const node = qs(selector);
    if (node) node.textContent = value == null || value === "" ? "--" : String(value);
  }

  function toast(message) {
    const node = qs("[data-plan-toast]");
    if (!node) return;
    node.textContent = message;
    node.classList.add("is-open");
    window.clearTimeout(toast.timer);
    toast.timer = window.setTimeout(() => node.classList.remove("is-open"), 2600);
  }

  function errorMessage(error) {
    return String((error && error.message) || "请求失败");
  }

  function jsonHeaders() {
    return {
      "Content-Type": "application/json",
      "X-Admin-Action-Token": adminActionToken,
    };
  }

  function writePayload(extra) {
    return {
      admin_action_token: adminActionToken,
      operator: "admin_ui",
      ...(extra || {}),
    };
  }

  function formatDate(value) {
    if (!value) return "--";
    const textValue = String(value);
    const date = new Date(textValue);
    if (Number.isNaN(date.getTime())) return textValue;
    return date.toLocaleString("zh-CN", { hour12: false });
  }

  function planStatus(plan) {
    const review = String((plan && plan.review_status) || "");
    const run = String((plan && plan.run_status) || "");
    if (review === "approved") return { label: "已批准", tone: "ok" };
    if (review === "rejected") return { label: "已拒绝", tone: "bad" };
    if (run === "active" || run === "running") return { label: "执行中", tone: "ok" };
    return { label: "待审批", tone: "warn" };
  }

  function sendStatus(row) {
    const approval = String((row && row.approval_status) || "");
    const send = String((row && row.send_status) || "");
    if (approval === "rejected" || send === "cancelled") return { label: "已拒绝", tone: "bad" };
    if (send === "sent") return { label: "已发送", tone: "ok" };
    if (approval === "approved" || send === "queued" || send === "sending") return { label: "已批准", tone: "ok" };
    if (send === "failed") return { label: "发送失败", tone: "bad" };
    return { label: "待处理", tone: "warn" };
  }

  function badge(meta) {
    const toneClass = meta.tone ? ` cloud-plan-badge--${meta.tone}` : "";
    return `<span class="cloud-plan-badge${toneClass}">${escapeHtml(meta.label)}</span>`;
  }

  function canApproveRecipient(row) {
    const approval = String((row && row.approval_status) || "");
    const send = String((row && row.send_status) || "");
    return approval !== "approved" && approval !== "rejected" && send !== "sent" && send !== "queued" && send !== "sending";
  }

  function approveLabel(row) {
    const approval = String((row && row.approval_status) || "");
    const send = String((row && row.send_status) || "");
    if (approval === "rejected") return "已拒绝";
    if (approval === "approved" || send === "sent" || send === "queued" || send === "sending") return "已批准";
    return "批准";
  }

  function setButtonLoading(button, loadingText) {
    if (!button) return () => {};
    const originalText = button.textContent;
    const originalDisabled = button.disabled;
    button.disabled = true;
    button.textContent = loadingText;
    return () => {
      button.disabled = originalDisabled;
      button.textContent = originalText;
    };
  }

  function initListPage() {
    const refreshButton = qs("[data-plan-refresh]");
    const keywordInput = qs("[data-plan-keyword]");
    const statusSelect = qs("[data-plan-status]");
    refreshButton && refreshButton.addEventListener("click", loadPlans);
    keywordInput && keywordInput.addEventListener("keydown", (event) => {
      if (event.key === "Enter") loadPlans();
    });
    statusSelect && statusSelect.addEventListener("change", loadPlans);
    loadPlans();
  }

  function renderStats(payload) {
    const plans = payload.plans || [];
    const pending = plans.filter((plan) => String(plan.review_status || "") === "pending_review").length;
    const active = plans.filter((plan) => ["active", "running"].includes(String(plan.run_status || ""))).length;
    const touch = plans.reduce((sum, plan) => sum + Number(plan.target_count || 0), 0);
    text("[data-stat-pending-plans]", pending);
    text("[data-stat-active-plans]", active);
    text("[data-stat-today-touch]", touch);
  }

  async function loadPlans() {
    const list = qs("[data-plan-list]");
    if (!list) return;
    list.innerHTML = '<div class="cloud-plan-loading">计划列表加载中</div>';
    const params = new URLSearchParams();
    params.set("limit", "20");
    params.set("offset", "0");
    const keyword = (qs("[data-plan-keyword]") || {}).value || "";
    const status = (qs("[data-plan-status]") || {}).value || "";
    if (keyword.trim()) params.set("keyword", keyword.trim());
    if (status) params.set("status", status);
    try {
      const payload = await requestJson(`/api/admin/cloud-orchestrator/plans?${params.toString()}`);
      state.plans = payload.plans || [];
      renderStats(payload);
      if (!state.plans.length) {
        list.innerHTML = '<div class="cloud-plan-empty">暂无计划</div>';
        return;
      }
      list.innerHTML = state.plans.map(renderPlanRow).join("");
    } catch (error) {
      list.innerHTML = `<div class="cloud-plan-error">${escapeHtml(errorMessage(error))}</div>`;
    }
  }

  function renderPlanRow(plan) {
    const status = planStatus(plan);
    const planHref = `/admin/cloud-orchestrator/plans/${encodeURIComponent(plan.plan_id || "")}`;
    return `
      <article class="cloud-plan-row">
        <div>
          <div class="cloud-plan-name">${escapeHtml(plan.display_name || plan.plan_id)}</div>
        </div>
        <div class="cloud-plan-code">${escapeHtml(plan.plan_id)}</div>
        <div>${escapeHtml(plan.owner_userid || "--")}</div>
        <div class="cloud-plan-cell-muted">${escapeHtml(formatDate(plan.updated_at))}</div>
        <div>${Number(plan.target_count || 0)}</div>
        <div>${Number(plan.approved_count || 0)}</div>
        <div>${Number(plan.pending_count || 0)}</div>
        <div>${badge(status)}</div>
        <div><a class="cloud-plan-button" href="${planHref}">查看详情</a></div>
      </article>
    `;
  }

  function initDetailPage() {
    qs("[data-plan-approve]") && qs("[data-plan-approve]").addEventListener("click", approvePlan);
    qs("[data-plan-reject]") && qs("[data-plan-reject]").addEventListener("click", rejectPlan);
    qs("[data-recipient-load-more]") && qs("[data-recipient-load-more]").addEventListener("click", () => loadRecipients({ append: true }));
    qs("[data-drawer-close]") && qs("[data-drawer-close]").addEventListener("click", closeDrawer);
    qs("[data-drawer-mask]") && qs("[data-drawer-mask]").addEventListener("click", closeDrawer);
    qs("[data-drawer-approve]") && qs("[data-drawer-approve]").addEventListener("click", () => {
      if (state.currentRecipient) approveRecipient(state.currentRecipient.recipient_id, qs("[data-drawer-approve]"));
    });
    qs("[data-drawer-reject]") && qs("[data-drawer-reject]").addEventListener("click", () => {
      if (state.currentRecipient) rejectRecipient(state.currentRecipient.recipient_id, qs("[data-drawer-reject]"));
    });
    loadPlan();
    loadRecipients({ append: false });
  }

  async function loadPlan() {
    try {
      const payload = await requestJson(`/api/admin/cloud-orchestrator/plans/${encodeURIComponent(planId)}`);
      updatePlan(payload.plan);
    } catch (error) {
      text("[data-plan-detail-state]", errorMessage(error));
    }
  }

  function updatePlan(plan) {
    if (!plan) return;
    state.plan = plan;
    const status = planStatus(plan);
    text("[data-plan-detail-state]", `${plan.display_name || plan.plan_id} · ${status.label}`);
    text("[data-plan-name]", plan.display_name || plan.plan_id);
    text("[data-plan-code]", plan.plan_id);
    text("[data-plan-owner]", plan.owner_userid);
    text("[data-plan-updated]", formatDate(plan.updated_at));
    text("[data-plan-target-count]", Number(plan.target_count || 0));
    const statusNode = qs("[data-plan-status-label]");
    if (statusNode) statusNode.innerHTML = badge(status);
  }

  async function approvePlan(event) {
    const restore = setButtonLoading(event.currentTarget, "批准中");
    try {
      const payload = await requestJson(`/api/admin/cloud-orchestrator/plans/${encodeURIComponent(planId)}/approve`, {
        method: "POST",
        headers: jsonHeaders(),
        body: writePayload(),
      });
      updatePlan(payload.plan);
      toast("计划已批准");
    } catch (error) {
      toast(errorMessage(error));
    } finally {
      restore();
      if (state.currentRecipient && Number(state.currentRecipient.recipient_id) === Number(recipientId)) renderDrawer();
    }
  }

  async function rejectPlan(event) {
    const restore = setButtonLoading(event.currentTarget, "拒绝中");
    try {
      const payload = await requestJson(`/api/admin/cloud-orchestrator/plans/${encodeURIComponent(planId)}/reject`, {
        method: "POST",
        headers: jsonHeaders(),
        body: writePayload({ reason: "admin_ui_reject" }),
      });
      updatePlan(payload.plan);
      toast("计划已拒绝");
    } catch (error) {
      toast(errorMessage(error));
    } finally {
      restore();
      if (state.currentRecipient && Number(state.currentRecipient.recipient_id) === Number(recipientId)) renderDrawer();
    }
  }

  async function loadRecipients(options) {
    const append = Boolean(options && options.append);
    const tbody = qs("[data-recipient-list]");
    const moreButton = qs("[data-recipient-load-more]");
    if (!tbody) return;
    if (!append) {
      state.recipientOffset = 0;
      state.recipients = [];
      tbody.innerHTML = '<tr><td colspan="6" class="cloud-plan-state">目标人员加载中</td></tr>';
    }
    if (moreButton) moreButton.disabled = true;
    const params = new URLSearchParams({ limit: String(PAGE_SIZE), offset: String(state.recipientOffset) });
    try {
      const payload = await requestJson(`/api/admin/cloud-orchestrator/plans/${encodeURIComponent(planId)}/recipients?${params.toString()}`);
      state.plan = payload.plan || state.plan;
      updatePlan(state.plan);
      state.recipientTotal = Number(payload.total || 0);
      state.recipients = append ? state.recipients.concat(payload.rows || []) : (payload.rows || []);
      state.recipientOffset = state.recipients.length;
      renderRecipients();
    } catch (error) {
      tbody.innerHTML = `<tr><td colspan="6" class="cloud-plan-error">${escapeHtml(errorMessage(error))}</td></tr>`;
    } finally {
      updateRecipientLoadbar();
    }
  }

  function renderRecipients() {
    const tbody = qs("[data-recipient-list]");
    if (!tbody) return;
    if (!state.recipients.length) {
      tbody.innerHTML = '<tr><td colspan="6" class="cloud-plan-empty">暂无目标人员</td></tr>';
      return;
    }
    tbody.innerHTML = state.recipients.map(renderRecipientRow).join("");
    qsa("[data-open-recipient]").forEach((button) => {
      button.addEventListener("click", () => openRecipient(Number(button.dataset.recipientId || 0)));
    });
    qsa("[data-approve-recipient]").forEach((button) => {
      button.addEventListener("click", () => approveRecipient(Number(button.dataset.recipientId || 0), button));
    });
  }

  function renderRecipientRow(row) {
    const status = sendStatus(row);
    const canApprove = canApproveRecipient(row);
    return `
      <tr data-recipient-row="${Number(row.recipient_id || 0)}">
        <td>
          <strong>${escapeHtml(row.display_name || row.external_userid)}</strong>
          <div class="cloud-plan-cell-muted">${escapeHtml(row.external_userid || "")}</div>
        </td>
        <td>${escapeHtml(row.owner_userid || "--")}</td>
        <td>${escapeHtml(formatDate(row.updated_at))}</td>
        <td>${Number(row.planned_message_count || 0)}</td>
        <td>${badge(status)}</td>
        <td>
          <div class="cloud-plan-actions">
            <button class="cloud-plan-button" type="button" data-open-recipient data-recipient-id="${Number(row.recipient_id || 0)}">查看详情</button>
            <button class="cloud-plan-button cloud-plan-button--primary" type="button" data-approve-recipient data-recipient-id="${Number(row.recipient_id || 0)}" ${canApprove ? "" : "disabled"}>${escapeHtml(approveLabel(row))}</button>
          </div>
        </td>
      </tr>
    `;
  }

  function updateRecipientLoadbar() {
    const loaded = state.recipients.length;
    const total = state.recipientTotal;
    text("[data-recipient-loaded]", `已加载 ${loaded} / ${total} 人`);
    const progress = qs("[data-recipient-progress]");
    if (progress) {
      progress.style.width = total > 0 ? `${Math.min(100, Math.round((loaded / total) * 100))}%` : "0%";
    }
    const moreButton = qs("[data-recipient-load-more]");
    if (moreButton) moreButton.disabled = loaded >= total || total === 0;
  }

  async function openRecipient(recipientId) {
    if (!recipientId) return;
    state.currentRecipient = null;
    state.currentMessages = [];
    openDrawer();
    text("[data-drawer-name]", "人员详情");
    text("[data-drawer-subtitle]", "人员详情加载中");
    const tasks = qs("[data-drawer-tasks]");
    if (tasks) tasks.innerHTML = '<div class="cloud-plan-loading">人员详情加载中</div>';
    try {
      const payload = await requestJson(`/api/admin/cloud-orchestrator/plans/${encodeURIComponent(planId)}/recipients/${encodeURIComponent(recipientId)}`);
      state.currentRecipient = payload.recipient;
      state.currentMessages = payload.messages || [];
      renderDrawer();
    } catch (error) {
      if (tasks) tasks.innerHTML = `<div class="cloud-plan-error">${escapeHtml(errorMessage(error))}</div>`;
      text("[data-drawer-subtitle]", errorMessage(error));
    }
  }

  function openDrawer() {
    qs("[data-drawer-mask]") && qs("[data-drawer-mask]").classList.add("is-open");
    qs("[data-recipient-drawer]") && qs("[data-recipient-drawer]").classList.add("is-open");
  }

  function closeDrawer() {
    qs("[data-drawer-mask]") && qs("[data-drawer-mask]").classList.remove("is-open");
    qs("[data-recipient-drawer]") && qs("[data-recipient-drawer]").classList.remove("is-open");
  }

  function renderDrawer() {
    const recipient = state.currentRecipient;
    if (!recipient) return;
    const messageCount = state.currentMessages.length || Number(recipient.planned_message_count || 0);
    text("[data-drawer-name]", recipient.display_name || recipient.external_userid);
    text("[data-drawer-subtitle]", `${sendStatus(recipient).label} · ${messageCount} 次话术任务`);
    text("[data-drawer-target-name]", recipient.display_name || "--");
    text("[data-drawer-external-userid]", recipient.external_userid || "--");
    text("[data-drawer-owner]", recipient.owner_userid || "--");
    text("[data-drawer-message-count]", messageCount);
    const approveButton = qs("[data-drawer-approve]");
    if (approveButton) {
      approveButton.disabled = !canApproveRecipient(recipient);
      approveButton.textContent = canApproveRecipient(recipient) ? "批准这个人发送" : approveLabel(recipient);
    }
    const rejectButton = qs("[data-drawer-reject]");
    if (rejectButton) rejectButton.disabled = String(recipient.approval_status || "") === "rejected" || String(recipient.send_status || "") === "sent";
    const tasks = qs("[data-drawer-tasks]");
    if (!tasks) return;
    if (!state.currentMessages.length) {
      tasks.innerHTML = '<div class="cloud-plan-empty">暂无话术任务</div>';
      return;
    }
    tasks.innerHTML = state.currentMessages.map(renderTask).join("");
  }

  function renderTask(task) {
    const attachments = Array.isArray(task.attachments) ? task.attachments : [];
    const attachmentHtml = attachments.length
      ? attachments.map((item) => `<div class="cloud-plan-cell-muted">${escapeHtml(item.msgtype || item.type || "附件")} ${escapeHtml(item.title || item.name || "")}</div>`).join("")
      : "";
    return `
      <article class="cloud-plan-task">
        <div class="cloud-plan-task-meta">第 ${Number(task.sequence_index || 0)} 次 · D+${Number(task.day_offset || 0)} · ${escapeHtml(task.send_time || "--")} · ${escapeHtml(task.status || "pending")}</div>
        <div class="cloud-plan-task-text">${escapeHtml(task.content_text || "")}</div>
        ${attachmentHtml}
      </article>
    `;
  }

  function updateRecipientInState(recipient) {
    if (!recipient) return;
    state.recipients = state.recipients.map((row) => Number(row.recipient_id) === Number(recipient.recipient_id) ? recipient : row);
    if (state.currentRecipient && Number(state.currentRecipient.recipient_id) === Number(recipient.recipient_id)) {
      state.currentRecipient = recipient;
      renderDrawer();
    }
    renderRecipients();
  }

  async function approveRecipient(recipientId, button) {
    if (!recipientId) return;
    const restore = setButtonLoading(button, "批准中");
    try {
      const payload = await requestJson(`/api/admin/cloud-orchestrator/plans/${encodeURIComponent(planId)}/recipients/${encodeURIComponent(recipientId)}/approve`, {
        method: "POST",
        headers: jsonHeaders(),
        body: writePayload(),
      });
      updateRecipientInState(payload.recipient);
      toast(payload.status === "already_approved" ? "已批准" : "已批准这个人发送");
    } catch (error) {
      toast(errorMessage(error));
    } finally {
      restore();
    }
  }

  async function rejectRecipient(recipientId, button) {
    if (!recipientId) return;
    const restore = setButtonLoading(button, "拒绝中");
    try {
      const payload = await requestJson(`/api/admin/cloud-orchestrator/plans/${encodeURIComponent(planId)}/recipients/${encodeURIComponent(recipientId)}/reject`, {
        method: "POST",
        headers: jsonHeaders(),
        body: writePayload({ reason: "admin_ui_reject" }),
      });
      updateRecipientInState(payload.recipient);
      toast("已拒绝这个人");
    } catch (error) {
      toast(errorMessage(error));
    } finally {
      restore();
    }
  }

  if (mode === "detail") {
    initDetailPage();
  } else {
    initListPage();
  }
})();
