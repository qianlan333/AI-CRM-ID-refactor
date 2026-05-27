(function (window, document) {
  "use strict";

  const api = window.AdminApi || {};
  const escapeHtml = api.escapeHtml || ((value) => String(value || ""));
  const requestJson = api.requestJson || ((url, options) => fetch(url, options).then((response) => response.json()));
  const app = document.getElementById("group-ops-app");
  if (!app) return;

  const state = {
    mode: app.dataset.pageMode || "list",
    planId: Number(app.dataset.planId || 0),
    plans: [],
    groups: [],
    plan: null,
    planGroups: [],
    groupSummary: null,
    nodes: [],
    webhook: null,
    ownerOptions: [],
    createOwner: null,
    groupFilterOwner: null,
    notice: "",
    showCreate: false,
    showNodeForm: false,
    editingNodeId: 0,
    oneTimeToken: "",
  };

  const routes = {
    list: "/admin/automation-conversion/group-ops/ui",
    groups: "/admin/automation-conversion/group-ops/groups/ui",
    plan: (id) => `/admin/automation-conversion/group-ops/plans/${encodeURIComponent(id)}`,
    apiPlans: "/api/admin/automation-conversion/group-ops/plans",
    apiPlan: (id) => `/api/admin/automation-conversion/group-ops/plans/${encodeURIComponent(id)}`,
    apiPlanGroups: (id) => `/api/admin/automation-conversion/group-ops/plans/${encodeURIComponent(id)}/groups`,
    apiPlanGroup: (id, chatId) =>
      `/api/admin/automation-conversion/group-ops/plans/${encodeURIComponent(id)}/groups/${encodeURIComponent(chatId)}`,
    apiPlanNodes: (id) => `/api/admin/automation-conversion/group-ops/plans/${encodeURIComponent(id)}/nodes`,
    apiPlanNode: (id, nodeId) =>
      `/api/admin/automation-conversion/group-ops/plans/${encodeURIComponent(id)}/nodes/${encodeURIComponent(nodeId)}`,
    apiWebhook: (id) => `/api/admin/automation-conversion/group-ops/plans/${encodeURIComponent(id)}/webhook`,
    apiWebhookRegenerate: (id) =>
      `/api/admin/automation-conversion/group-ops/plans/${encodeURIComponent(id)}/webhook/regenerate`,
    apiGroups: "/api/admin/automation-conversion/group-ops/groups",
    apiMembers: "/api/admin/common/operation-members?scope=group_ops&page_size=100",
  };

  function normalizeItems(payload) {
    if (!payload || !Array.isArray(payload.items)) return [];
    return payload.items;
  }

  function formatNumber(value) {
    return new Intl.NumberFormat("zh-CN").format(Number(value || 0));
  }

  function statusText(status) {
    const map = { active: "启用", draft: "草稿", disabled: "停用" };
    return map[status] || status || "-";
  }

  function typeText(type) {
    return type === "webhook" ? "Webhook" : "标准编排";
  }

  function attachmentLabel(attachments) {
    const items = Array.isArray(attachments) ? attachments : [];
    if (!items.length) return "-";
    return items
      .map((item) => item && (item.msgtype || item.type || item.name || "素材"))
      .filter(Boolean)
      .join("、");
  }

  function textSummary(value) {
    const text = String(value || "").trim();
    if (!text) return "-";
    return text.length > 34 ? `${text.slice(0, 34)}...` : text;
  }

  function renderShell(content) {
    app.innerHTML = content;
    bindSharedEvents();
  }

  function renderLoading() {
    renderShell('<section class="group-ops__card"><div class="group-ops__empty">加载中</div></section>');
  }

  function renderError(message) {
    renderShell(`<section class="group-ops__card"><div class="group-ops__empty">${escapeHtml(message || "加载失败")}</div></section>`);
  }

  function pageButton(label, href, variant) {
    return `<a class="group-ops__button${variant === "primary" ? " group-ops__button--primary" : ""}" href="${escapeHtml(href)}">${escapeHtml(label)}</a>`;
  }

  function actionButton(label, action, extraClass) {
    return `<button class="group-ops__button${extraClass ? ` ${extraClass}` : ""}" type="button" data-action="${escapeHtml(action)}">${escapeHtml(label)}</button>`;
  }

  function metricCard(label, value) {
    return `<article class="group-ops__metric"><div class="group-ops__metric-label">${escapeHtml(label)}</div><div class="group-ops__metric-value">${escapeHtml(value)}</div></article>`;
  }

  function statCard(label, value) {
    return `<article class="group-ops__stat"><div class="group-ops__stat-label">${escapeHtml(label)}</div><div class="group-ops__stat-value">${escapeHtml(value)}</div></article>`;
  }

  function bindSharedEvents() {
    app.querySelectorAll("[data-action]").forEach((element) => {
      element.addEventListener("click", onAction);
    });
    app.querySelectorAll("[data-filter]").forEach((element) => {
      element.addEventListener("change", onFilterChange);
      element.addEventListener("keydown", (event) => {
        if (event.key === "Enter") onFilterChange();
      });
    });
  }

  function onFilterChange() {
    if (state.mode === "groups") loadGroupsPage();
  }

  function currentFormValue(name) {
    const element = app.querySelector(`[name="${name}"]`);
    return element ? element.value : "";
  }

  function memberLabel(member) {
    if (window.OperationMemberPicker && typeof window.OperationMemberPicker.memberLabel === "function") {
      return window.OperationMemberPicker.memberLabel(member);
    }
    const userId = member.user_id || member.userid || "";
    const displayName = member.display_name || member.name || "";
    return displayName && displayName !== userId ? `${displayName} / ${userId}` : userId;
  }

  function normalizeOwners(payload, plan) {
    const owners = new Map();
    normalizeItems(payload).forEach((member) => {
      const userId = member.user_id || member.userid;
      if (userId) owners.set(userId, { user_id: userId, display_name: member.display_name || member.name || userId });
    });
    if (plan && plan.owner_userid && !owners.has(plan.owner_userid)) {
      owners.set(plan.owner_userid, { user_id: plan.owner_userid, display_name: plan.owner_name || plan.owner_userid });
    }
    return Array.from(owners.values());
  }

  function currentMemberFor(userId) {
    const normalized = String(userId || "");
    if (!normalized) return null;
    return state.ownerOptions.find((member) => member.user_id === normalized) || { user_id: normalized, display_name: normalized };
  }

  function renderMemberField(name, currentUserId, action, label) {
    const selected = currentMemberFor(currentUserId);
    return `
      <div class="group-ops__member-field" data-member-field="${escapeHtml(name)}">
        <input type="hidden" name="${escapeHtml(name)}" value="${escapeHtml((selected || {}).user_id || "")}">
        <div class="group-ops__member-current" data-member-current="${escapeHtml(name)}">${escapeHtml(selected ? memberLabel(selected) : "未选择")}</div>
        ${actionButton(label || (selected ? "更换" : "选择"), action)}
      </div>
    `;
  }

  function setMemberField(name, member) {
    const input = app.querySelector(`[name="${name}"]`);
    const current = app.querySelector(`[data-member-current="${name}"]`);
    if (input) input.value = member.user_id || "";
    if (current) current.textContent = memberLabel(member);
  }

  function openMemberPicker({ fieldName, title, value, onPicked }) {
    if (!window.OperationMemberPicker) {
      state.notice = "人员加载失败，请稍后重试";
      if (state.mode === "detail") renderDetail();
      else if (state.mode === "groups") renderGroups();
      else renderList(state.lastTotal || state.plans.length, state.queueCount || 0);
      return;
    }
    window.OperationMemberPicker.open({
      value,
      title: title || "选择运营人员",
      onSelect: (member) => {
        setMemberField(fieldName, member);
        if (typeof onPicked === "function") onPicked(member);
      },
    });
  }

  function onAction(event) {
    const action = event.currentTarget.dataset.action;
    if (action === "create-plan") return createPlan();
    if (action === "show-create-plan") return showCreatePlan();
    if (action === "cancel-create-plan") return cancelCreatePlan();
    if (action === "save-plan") return savePlan();
    if (action === "disable-plan") return disablePlan(event.currentTarget.dataset.planId);
    if (action === "bind-group") return bindGroup(event.currentTarget.dataset.chatId);
    if (action === "remove-group") return removeGroup(event.currentTarget.dataset.chatId);
    if (action === "show-node-form") return showNodeForm();
    if (action === "edit-node") return showNodeForm(event.currentTarget.dataset.nodeId);
    if (action === "save-node") return saveNode();
    if (action === "cancel-node") return cancelNodeForm();
    if (action === "delete-node") return deleteNode(event.currentTarget.dataset.nodeId);
    if (action === "copy-webhook") return copyWebhook();
    if (action === "reset-webhook") return resetWebhook();
    if (action === "pick-create-owner") return openMemberPicker({
      fieldName: "create_owner_userid",
      title: "选择运营人员",
      value: currentFormValue("create_owner_userid"),
      onPicked: (member) => {
        state.createOwner = member;
      },
    });
    if (action === "pick-plan-owner") return openMemberPicker({
      fieldName: "owner_userid",
      title: "选择运营人员",
      value: currentFormValue("owner_userid") || (state.plan || {}).owner_userid,
      onPicked: () => {
        const target = app.querySelector("[data-available-groups]");
        if (target) {
          target.innerHTML = renderAvailableGroups();
          bindSharedEvents();
        }
      },
    });
    if (action === "pick-group-filter-owner") return openMemberPicker({
      fieldName: "owner_userid",
      title: "选择群主",
      value: currentFormValue("owner_userid"),
      onPicked: (member) => {
        state.groupFilterOwner = member;
        loadGroupsPage();
      },
    });
    if (action === "clear-group-filter-owner") {
      state.groupFilterOwner = null;
      setMemberField("owner_userid", { user_id: "", display_name: "" });
      return loadGroupsPage();
    }
    return undefined;
  }

  function showCreatePlan() {
    state.showCreate = true;
    renderList(state.lastTotal || state.plans.length, state.queueCount || 0);
  }

  function cancelCreatePlan() {
    state.showCreate = false;
    renderList(state.lastTotal || state.plans.length, state.queueCount || 0);
  }

  async function createPlan() {
    const owner = currentFormValue("create_owner_userid");
    if (!owner) {
      state.notice = "请选择运营成员";
      renderList(state.lastTotal || state.plans.length, state.queueCount || 0);
      return;
    }
    const created = await requestJson(routes.apiPlans, {
      method: "POST",
      body: {
        plan_name: currentFormValue("create_plan_name") || "新建群运营计划",
        plan_type: currentFormValue("create_plan_type") || "standard",
        owner_userid: owner,
        status: "draft",
      },
    });
    const item = created.item || created;
    if (item.id) window.location.assign(routes.plan(item.id));
  }

  async function disablePlan(planId) {
    const current = state.plans.find((item) => Number(item.id) === Number(planId));
    if (!current) return;
    await requestJson(routes.apiPlan(planId), {
      method: "PUT",
      body: {
        plan_name: current.plan_name,
        plan_code: current.plan_code,
        plan_type: current.plan_type,
        owner_userid: current.owner_userid,
        status: "disabled",
      },
    });
    loadListPage();
  }

  async function savePlan() {
    if (!state.plan || !state.plan.id) return;
    await requestJson(routes.apiPlan(state.plan.id), {
      method: "PUT",
      body: {
        plan_name: currentFormValue("plan_name") || state.plan.plan_name,
        plan_code: state.plan.plan_code,
        plan_type: state.plan.plan_type,
        owner_userid: currentFormValue("owner_userid") || state.plan.owner_userid,
        status: currentFormValue("status") || state.plan.status,
      },
    });
    state.notice = "已保存";
    loadDetailPage(state.plan.id);
  }

  async function bindGroup(chatId) {
    if (!state.plan || !chatId) return;
    await requestJson(routes.apiPlanGroups(state.plan.id), { method: "POST", body: { chat_id: chatId } });
    state.notice = "已添加";
    loadDetailPage(state.plan.id);
  }

  async function removeGroup(chatId) {
    if (!state.plan || !chatId) return;
    await requestJson(routes.apiPlanGroup(state.plan.id, chatId), { method: "DELETE" });
    state.notice = "已移除";
    loadDetailPage(state.plan.id);
  }

  function showNodeForm(nodeId) {
    state.editingNodeId = Number(nodeId || 0);
    state.showNodeForm = true;
    renderDetail();
  }

  function cancelNodeForm() {
    state.editingNodeId = 0;
    state.showNodeForm = false;
    renderDetail();
  }

  function editingNode() {
    return state.nodes.find((node) => Number(node.id) === Number(state.editingNodeId)) || null;
  }

  function parseAttachments(value) {
    const text = String(value || "").trim();
    if (!text) return [];
    try {
      const parsed = JSON.parse(text);
      return Array.isArray(parsed) ? parsed : [];
    } catch (error) {
      state.notice = "素材格式无效";
      renderDetail();
      throw error;
    }
  }

  async function saveNode() {
    if (!state.plan || !state.plan.id) return;
    const payload = {
      day_index: Number(currentFormValue("node_day_index") || 1),
      trigger_time_label: currentFormValue("node_trigger_time_label"),
      action_title: currentFormValue("node_action_title"),
      text_content: currentFormValue("node_text_content"),
      attachments: parseAttachments(currentFormValue("node_attachments")),
      sort_order: Number(currentFormValue("node_sort_order") || 0),
      status: currentFormValue("node_status") || "active",
    };
    const nodeId = Number(state.editingNodeId || 0);
    await requestJson(nodeId ? routes.apiPlanNode(state.plan.id, nodeId) : routes.apiPlanNodes(state.plan.id), {
      method: nodeId ? "PUT" : "POST",
      body: payload,
    });
    state.notice = nodeId ? "已更新动作" : "已添加动作";
    state.editingNodeId = 0;
    state.showNodeForm = false;
    loadDetailPage(state.plan.id);
  }

  async function deleteNode(nodeId) {
    if (!state.plan || !nodeId) return;
    await requestJson(routes.apiPlanNode(state.plan.id, nodeId), { method: "DELETE" });
    state.notice = "已删除动作";
    loadDetailPage(state.plan.id);
  }

  async function copyWebhook() {
    const url = state.webhook && state.webhook.webhook_url;
    if (!url) return;
    if (navigator.clipboard && navigator.clipboard.writeText) {
      await navigator.clipboard.writeText(url);
    }
    state.notice = "已复制";
    renderDetail();
  }

  async function resetWebhook() {
    if (!state.plan || !state.plan.id) return;
    state.webhook = await requestJson(routes.apiWebhookRegenerate(state.plan.id), { method: "POST" });
    state.oneTimeToken = state.webhook.plaintext_token || "";
    state.notice = "已重置";
    renderDetail();
  }

  async function loadListPage() {
    renderLoading();
    try {
      const [payload, ownersPayload] = await Promise.all([requestJson(routes.apiPlans), requestJson(routes.apiMembers)]);
      state.plans = normalizeItems(payload);
      state.ownerOptions = normalizeOwners(ownersPayload, null);
      state.lastTotal = payload.total || state.plans.length;
      state.queueCount = payload.queue_count || 0;
      renderList(state.lastTotal, state.queueCount);
    } catch (error) {
      renderError(error.message);
    }
  }

  function renderCreatePanel() {
    if (!state.showCreate) return "";
    const ownerField = renderMemberField("create_owner_userid", (state.createOwner || {}).user_id, "pick-create-owner", state.createOwner ? "更换运营成员" : "选择运营成员");
    return `
      <section class="group-ops__card">
        <div class="group-ops__filters">
          <label class="group-ops__field group-ops__field--wide"><span>计划名称</span><input name="create_plan_name" value="新建群运营计划"></label>
          <label class="group-ops__field"><span>计划类型</span><select name="create_plan_type"><option value="standard">标准编排计划</option><option value="webhook">Webhook 接收计划</option></select></label>
          <label class="group-ops__field"><span>运营成员</span>${ownerField}</label>
          <div class="group-ops__row-actions">${actionButton("保存计划", "create-plan", "group-ops__button--primary")}${actionButton("取消", "cancel-create-plan")}</div>
        </div>
      </section>
    `;
  }

  function renderList(total, queueCount) {
    const boundCount = state.plans.reduce((sum, plan) => sum + Number(plan.bound_group_count || 0), 0);
    const reach = state.plans.reduce((sum, plan) => sum + Number(plan.today_estimated_reach || 0), 0);
    const rows = state.plans
      .map(
        (plan) => `
        <tr>
          <td><strong>${escapeHtml(plan.plan_name)}</strong></td>
          <td>${escapeHtml(typeText(plan.plan_type))}</td>
          <td>${escapeHtml(plan.owner_name || plan.owner_userid || "-")}</td>
          <td>${formatNumber(plan.bound_group_count)}</td>
          <td>${formatNumber(plan.today_estimated_reach)}</td>
          <td><span class="group-ops__chip${plan.status === "active" ? " group-ops__chip--ok" : " group-ops__chip--neutral"}">${escapeHtml(statusText(plan.status))}</span></td>
          <td>
            <div class="group-ops__row-actions">
              <a class="group-ops__button group-ops__button--primary" href="${escapeHtml(routes.plan(plan.id))}">编辑</a>
              <button class="group-ops__button group-ops__button--danger" type="button" data-action="disable-plan" data-plan-id="${escapeHtml(plan.id)}">停用 / 删除</button>
            </div>
          </td>
        </tr>`,
      )
      .join("");
    renderShell(`
      <div class="group-ops__bar">
        ${pageButton("查看所有群", routes.groups)}
        ${actionButton("创建计划", "show-create-plan", "group-ops__button--primary")}
      </div>
      <div class="group-ops__notice" ${state.notice ? "" : "hidden"}>${escapeHtml(state.notice)}</div>
      <section class="group-ops__metric-grid">
        ${metricCard("运营计划", formatNumber(total))}
        ${metricCard("已绑定群", formatNumber(boundCount))}
        ${metricCard("今日预估", formatNumber(reach))}
        ${metricCard("通知排队队列", formatNumber(queueCount))}
      </section>
      ${renderCreatePanel()}
      <section class="group-ops__card">
        <div class="group-ops__table-wrap">
          <table class="group-ops__table">
            <thead>
              <tr><th>计划名称</th><th>类型</th><th>运营成员</th><th>绑定群</th><th>今日预估</th><th>状态</th><th>操作</th></tr>
            </thead>
            <tbody>${rows || '<tr><td colspan="7" class="group-ops__empty">暂无数据</td></tr>'}</tbody>
          </table>
        </div>
      </section>
    `);
    state.notice = "";
  }

  async function loadDetailPage(planId) {
    renderLoading();
    try {
      const [planPayload, groupPayload, allGroupsPayload, nodePayload, ownersPayload] = await Promise.all([
        requestJson(routes.apiPlan(planId)),
        requestJson(routes.apiPlanGroups(planId)),
        requestJson(routes.apiGroups),
        requestJson(routes.apiPlanNodes(planId)),
        requestJson(routes.apiMembers),
      ]);
      state.plan = planPayload.item || planPayload.plan || planPayload;
      state.planGroups = normalizeItems(groupPayload);
      state.groupSummary = groupPayload.summary || null;
      state.groups = normalizeItems(allGroupsPayload);
      state.nodes = normalizeItems(nodePayload);
      state.ownerOptions = normalizeOwners(ownersPayload, state.plan);
      if (state.plan.plan_type === "webhook") {
        state.webhook = await requestJson(routes.apiWebhook(planId));
      } else {
        state.webhook = null;
      }
      renderDetail();
    } catch (error) {
      renderError(error.message);
    }
  }

  function groupName(row) {
    return row.group_name || row.group_name_snapshot || row.chat_id || "-";
  }

  function groupOwner(row) {
    return row.owner_name || row.owner_userid || row.owner_userid_snapshot || "-";
  }

  function renderBoundGroups() {
    if (!state.planGroups.length) return '<div class="group-ops__empty">暂无绑定群</div>';
    return state.planGroups
      .map(
        (group) => `
        <div class="group-ops__group-item">
          <div>
            <div class="group-ops__group-name"><strong>${escapeHtml(groupName(group))}</strong></div>
            <div class="group-ops__group-meta">${escapeHtml(group.chat_id || "")}</div>
          </div>
          ${actionButton("移除", "remove-group", "") .replace(">", ` data-chat-id="${escapeHtml(group.chat_id)}">`)}
        </div>`,
      )
      .join("");
  }

  function renderAvailableGroups() {
    const selectedOwner = currentFormValue("owner_userid") || (state.plan && state.plan.owner_userid) || "";
    const bound = new Set(state.planGroups.map((group) => group.chat_id));
    const rows = state.groups.filter((group) => group.owner_userid === selectedOwner && !bound.has(group.chat_id));
    if (!rows.length) return '<div class="group-ops__empty">暂无可选群</div>';
    return rows
      .map(
        (group) => `
        <div class="group-ops__group-item">
          <div>
            <div class="group-ops__group-name"><strong>${escapeHtml(group.group_name)}</strong></div>
            <div class="group-ops__group-meta">${escapeHtml(group.chat_id)}</div>
          </div>
          ${actionButton("添加", "bind-group", "group-ops__button--primary").replace(">", ` data-chat-id="${escapeHtml(group.chat_id)}">`)}
        </div>`,
      )
      .join("");
  }

  function renderStats(summary) {
    if (state.plan.plan_type === "webhook") {
      return `
        ${statCard("绑定群", formatNumber(summary.bound_group_count))}
        ${statCard("外部联系人", formatNumber(summary.external_member_count))}
        ${statCard("接收方式", "POST")}
        ${statCard("默认动作", "入队")}
      `;
    }
    return `
      ${statCard("绑定群", formatNumber(summary.bound_group_count))}
      ${statCard("内部联系人", formatNumber(summary.internal_member_count))}
      ${statCard("外部联系人", formatNumber(summary.external_member_count))}
      ${statCard("预计通知", formatNumber(summary.estimated_reach))}
    `;
  }

  function renderNodes() {
    const current = editingNode() || {
      day_index: 1,
      trigger_time_label: "",
      action_title: "",
      text_content: "",
      attachments: [],
      sort_order: 10,
      status: "active",
    };
    const form = state.showNodeForm
      ? `
        <div class="group-ops__filters">
          <label class="group-ops__field"><span>第几天</span><input name="node_day_index" type="number" min="1" value="${escapeHtml(current.day_index)}"></label>
          <label class="group-ops__field"><span>时间</span><input name="node_trigger_time_label" value="${escapeHtml(current.trigger_time_label || "")}"></label>
          <label class="group-ops__field group-ops__field--wide"><span>动作标题</span><input name="node_action_title" value="${escapeHtml(current.action_title || "")}"></label>
          <label class="group-ops__field group-ops__field--wide"><span>标准话术</span><textarea name="node_text_content">${escapeHtml(current.text_content || "")}</textarea></label>
          <label class="group-ops__field group-ops__field--wide"><span>素材</span><textarea name="node_attachments">${escapeHtml(JSON.stringify(current.attachments || []))}</textarea></label>
          <label class="group-ops__field"><span>排序</span><input name="node_sort_order" type="number" value="${escapeHtml(current.sort_order || 0)}"></label>
          <label class="group-ops__field"><span>状态</span><select name="node_status"><option value="active"${current.status === "active" ? " selected" : ""}>启用</option><option value="draft"${current.status === "draft" ? " selected" : ""}>草稿</option><option value="disabled"${current.status === "disabled" ? " selected" : ""}>停用</option></select></label>
          <div class="group-ops__row-actions">${actionButton("保存动作", "save-node", "group-ops__button--primary")}${actionButton("取消", "cancel-node")}</div>
        </div>`
      : "";
    const rows = state.nodes
      .map(
        (node) => `
        <tr>
          <td>第 ${escapeHtml(node.day_index)} 天</td>
          <td>${escapeHtml(node.trigger_time_label || "-")}</td>
          <td>${escapeHtml(node.action_title || "-")}</td>
          <td><span class="group-ops__summary">${escapeHtml(textSummary(node.text_content))}</span></td>
          <td>${escapeHtml(attachmentLabel(node.attachments))}</td>
          <td><div class="group-ops__row-actions">
            ${actionButton("编辑", "edit-node", "").replace(">", ` data-node-id="${escapeHtml(node.id)}">`)}
            ${actionButton("删除", "delete-node", "group-ops__button--danger").replace(">", ` data-node-id="${escapeHtml(node.id)}">`)}
          </div></td>
        </tr>`,
      )
      .join("");
    return `
      <section class="group-ops__card">
        <div class="group-ops__section-head"><h2 class="group-ops__section-title">标准编排</h2>${actionButton("添加动作", "show-node-form", "group-ops__button--primary")}</div>
        ${form}
        <div class="group-ops__table-wrap">
          <table class="group-ops__table">
            <thead><tr><th>第几天</th><th>时间</th><th>动作标题</th><th>标准话术摘要</th><th>素材标签</th><th>编辑 / 删除</th></tr></thead>
            <tbody>${rows || '<tr><td colspan="6" class="group-ops__empty">暂无节点</td></tr>'}</tbody>
          </table>
        </div>
      </section>
    `;
  }

  function renderWebhook() {
    const config = state.webhook || {};
    return `
      <section class="group-ops__card">
        <div class="group-ops__section-head"><h2 class="group-ops__section-title">Webhook 接收地址</h2></div>
        <div class="group-ops__webhook-panel">
          <div class="group-ops__webhook-line">
            <span class="group-ops__chip">POST</span>
            <div class="group-ops__url">${escapeHtml(config.webhook_url || "")}</div>
            ${actionButton("复制地址", "copy-webhook", "group-ops__button--primary")}
          </div>
          <div class="group-ops__webhook-line">
            <strong>Token 状态 / 重置入口</strong>
            <span class="group-ops__chip group-ops__chip--ok">Token：${escapeHtml(config.token_status === "generated" ? "已生成" : "未生成")}</span>
            ${actionButton("重置 token", "reset-webhook")}
          </div>
          ${
            state.oneTimeToken
              ? `<div class="group-ops__webhook-line"><strong>一次性 token</strong><div class="group-ops__url">${escapeHtml(
                  state.oneTimeToken,
                )}</div><span class="group-ops__chip">复制后不可再次查看</span></div>`
              : ""
          }
        </div>
      </section>
    `;
  }

  function renderDetail() {
    const summary = state.groupSummary || state.plan.groups_summary || {
      bound_group_count: state.planGroups.length,
      internal_member_count: state.planGroups.reduce((sum, item) => sum + Number(item.internal_member_count_snapshot || 0), 0),
      external_member_count: state.planGroups.reduce((sum, item) => sum + Number(item.external_member_count_snapshot || 0), 0),
      estimated_reach: state.planGroups.reduce((sum, item) => sum + Number(item.external_member_count_snapshot || 0), 0),
    };
    const isWebhook = state.plan.plan_type === "webhook";
    renderShell(`
      <div class="group-ops__bar">
        ${pageButton("返回列表", routes.list)}
        ${actionButton(isWebhook ? "保存接口计划" : "保存计划", "save-plan", "group-ops__button--primary")}
      </div>
      <div class="group-ops__notice" ${state.notice ? "" : "hidden"}>${escapeHtml(state.notice)}</div>
      <section class="group-ops__detail-grid">
        <article class="group-ops__card">
          <div class="group-ops__section-head"><h2 class="group-ops__section-title">运营成员</h2></div>
          <div class="group-ops__filters">
            <label class="group-ops__field group-ops__field--wide">
              <span>运营成员</span>
              ${renderMemberField("owner_userid", state.plan.owner_userid, "pick-plan-owner", "更换运营成员")}
            </label>
            <label class="group-ops__field">
              <span>状态</span>
              <select name="status">
                <option value="draft"${state.plan.status === "draft" ? " selected" : ""}>草稿</option>
                <option value="active"${state.plan.status === "active" ? " selected" : ""}>启用</option>
                <option value="disabled"${state.plan.status === "disabled" ? " selected" : ""}>停用</option>
              </select>
            </label>
            <label class="group-ops__field group-ops__field--wide">
              <span>计划名称</span>
              <input name="plan_name" value="${escapeHtml(state.plan.plan_name || "")}">
            </label>
          </div>
        </article>
        <article class="group-ops__card">
          <div class="group-ops__section-head"><h2 class="group-ops__section-title">${isWebhook ? "固定群包" : "绑定群"}</h2></div>
          <div class="group-ops__group-list">${renderBoundGroups()}</div>
          <div class="group-ops__section-head" style="margin-top:14px"><h3 class="group-ops__section-title">可选群</h3></div>
          <div class="group-ops__group-list" data-available-groups>${renderAvailableGroups()}</div>
        </article>
      </section>
      <section class="group-ops__stats-grid">${renderStats(summary)}</section>
      ${isWebhook ? renderWebhook() : renderNodes()}
    `);
    state.notice = "";
  }

  function groupsQueryParams() {
    const params = new URLSearchParams();
    const keyword = currentFormValue("keyword");
    const owner = currentFormValue("owner_userid");
    const plan = currentFormValue("plan_id");
    const bind = currentFormValue("bind_status");
    if (keyword) params.set("keyword", keyword);
    if (owner) params.set("owner_userid", owner);
    if (plan) params.set("plan_id", plan);
    if (bind) params.set("bind_status", bind);
    return params.toString();
  }

  async function loadGroupsPage() {
    try {
      const query = groupsQueryParams();
      const [groupPayload, planPayload, ownersPayload] = await Promise.all([
        requestJson(query ? `${routes.apiGroups}?${query}` : routes.apiGroups),
        state.plans.length ? Promise.resolve({ items: state.plans }) : requestJson(routes.apiPlans),
        requestJson(routes.apiMembers),
      ]);
      state.groups = normalizeItems(groupPayload);
      state.plans = normalizeItems(planPayload);
      state.ownerOptions = normalizeOwners(ownersPayload, null);
      renderGroups();
    } catch (error) {
      renderError(error.message);
    }
  }

  function renderPlanFilter() {
    return state.plans
      .map((plan) => `<option value="${escapeHtml(plan.id)}">${escapeHtml(plan.plan_name)}</option>`)
      .join("");
  }

  function renderGroups() {
    const rows = state.groups
      .map(
        (group) => `
        <tr>
          <td><strong>${escapeHtml(groupName(group))}</strong></td>
          <td>${escapeHtml(group.chat_id || "-")}</td>
          <td>${escapeHtml(groupOwner(group))}</td>
          <td>${escapeHtml(group.plan_name || "-")}</td>
          <td><span class="group-ops__chip${group.bind_status === "bound" ? " group-ops__chip--ok" : " group-ops__chip--neutral"}">${escapeHtml(group.bind_status === "bound" ? "已绑定" : "未绑定")}</span></td>
        </tr>`,
      )
      .join("");
    renderShell(`
      <div class="group-ops__bar">${pageButton("返回列表", routes.list)}</div>
      <section class="group-ops__card">
        <div class="group-ops__filters">
          <label class="group-ops__field group-ops__field--wide"><span>群名 / 群 ID</span><input name="keyword" data-filter></label>
          <label class="group-ops__field"><span>群主</span>${renderMemberField("owner_userid", (state.groupFilterOwner || {}).user_id, "pick-group-filter-owner", state.groupFilterOwner ? "更换群主" : "选择群主")}</label>
          <div class="group-ops__row-actions">${actionButton("清除群主", "clear-group-filter-owner")}</div>
          <label class="group-ops__field"><span>所属计划</span><select name="plan_id" data-filter><option value="">全部</option>${renderPlanFilter()}</select></label>
          <label class="group-ops__field"><span>已绑定 / 未绑定</span><select name="bind_status" data-filter><option value="">全部</option><option value="bound">已绑定</option><option value="unbound">未绑定</option></select></label>
        </div>
      </section>
      <section class="group-ops__card">
        <div class="group-ops__table-wrap">
          <table class="group-ops__table">
            <thead><tr><th>群名</th><th>群 ID</th><th>群主</th><th>所属计划</th><th>状态</th></tr></thead>
            <tbody>${rows || '<tr><td colspan="5" class="group-ops__empty">暂无数据</td></tr>'}</tbody>
          </table>
        </div>
      </section>
    `);
  }

  if (state.mode === "detail" && state.planId) {
    loadDetailPage(state.planId);
  } else if (state.mode === "groups") {
    renderLoading();
    loadGroupsPage();
  } else {
    loadListPage();
  }
})(window, document);
