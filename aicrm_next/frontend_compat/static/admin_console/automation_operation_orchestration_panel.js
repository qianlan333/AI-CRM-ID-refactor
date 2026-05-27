(() => {
  function initOperationPanel(root) {
  if (!root || root.dataset.operationPanelReady === "1") return;
  const apiUrls = JSON.parse(root.dataset.apiUrls || "{}");
  const endpoints = {
    tasks: apiUrls.tasks || "/api/admin/automation-conversion/tasks",
    taskBase: apiUrls.task_base || "/api/admin/automation-conversion/tasks/0",
    profileOptions: apiUrls.profile_segment_templates_options || "/api/admin/automation-conversion/profile-segment-templates/options",
    profileDetailBase: apiUrls.profile_segment_template_detail_base || "/api/admin/automation-conversion/profile-segment-templates/0",
    agents: apiUrls.agents_options || apiUrls.agents || "/api/admin/automation-conversion/agents",
    behaviorRules: apiUrls.behavior_segment_rules || "/api/admin/automation-conversion/behavior-segment-rules",
  };
  const state = {
    groups: [],
    tasks: [],
    currentTask: null,
    profileTemplates: [],
    profileSegments: [],
    behaviorRules: [],
    agents: [],
    preview: {},
  };
  const labels = { status: { draft: "草稿", active: "启用", paused: "停用", archived: "归档" } };
  const VALID_MODES = new Set(["unified", "profile_layered", "behavior_layered", "agent"]);
  const normalizeContentMode = (mode) => VALID_MODES.has(String(mode || "")) ? String(mode) : "unified";
  const dom = {
    groupFilter: root.querySelector("[data-group-filter]"),
    taskSearch: root.querySelector("[data-task-search]"),
    groupSelect: root.querySelector("[data-field='group_id']"),
    list: root.querySelector("[data-task-list]"),
    form: root.querySelector("[data-task-form]"),
    empty: root.querySelector("[data-task-empty]"),
    feedback: root.querySelector("[data-task-feedback]"),
    listFeedback: root.querySelector("[data-task-list-feedback]"),
    previewTotal: root.querySelector("[data-preview-total]"),
    strategyPanel: root.querySelector("[data-strategy-panel]"),
  };
  const escapeHtml = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[char]));
  const withId = (url, id) => String(url || "").replace(/\/0(?=\/|$)/, `/${encodeURIComponent(String(id || 0))}`);
  const currentId = () => Number((state.currentTask || {}).id || 0);
  const getField = (name) => root.querySelector(`[data-field="${name}"]`);
  const getValue = (name) => getField(name)?.value ?? "";
  const setValue = (name, value) => { const field = getField(name); if (field) field.value = value ?? ""; };
  const showFeedback = (target, message, ok = false) => {
    if (!target) return;
    target.textContent = message;
    target.classList.toggle("is-success", ok);
    target.style.display = "block";
  };
  const clearFeedback = () => [dom.feedback, dom.listFeedback].forEach((item) => { if (item) item.style.display = "none"; });
  const requestJson = async (url, options = {}) => {
    const response = await fetch(url, { headers: { Accept: "application/json", "Content-Type": "application/json", ...(options.headers || {}) }, ...options });
    const data = await response.json().catch(() => ({}));
    if (!response.ok || data.ok === false) throw new Error(data.error || data.detail || "操作失败，请稍后重试");
    return data;
  };

  function operationContent(task = state.currentTask || {}) {
    const config = task.config && typeof task.config === "object" ? task.config : {};
    const content = task.operation_content || config.operation_content || {};
    return {
      content_mode: normalizeContentMode(content.content_mode || task.content_mode || "unified"),
      profile_segment_template_id: Number(content.profile_segment_template_id || task.profile_segment_template_id || 0),
      unified_content_json: content.unified_content_json || task.unified_content_json || {},
      segment_contents_json: Array.isArray(content.segment_contents_json || task.segment_contents_json) ? (content.segment_contents_json || task.segment_contents_json) : [],
      agent_config_json: content.agent_config_json || task.agent_config_json || {},
    };
  }

  function contentSummary(content, agent = false) {
    const text = String(content.content_text || "").trim();
    const total = (content.image_library_ids || []).length + (content.miniprogram_library_ids || []).length + (content.attachment_library_ids || []).length;
    if (agent) return total ? `已配置素材 ${total} 个` : "未配置素材";
    if (!text && !total) return "未配置";
    return `已配置 · ${text ? "有话术" : "无话术"} · ${total} 素材`;
  }

  function groupName(id) {
    const group = state.groups.find((item) => Number(item.id) === Number(id));
    return group ? group.group_name : "未分组";
  }

  function syncGroupControls() {
    const options = [`<option value="">全部分组</option>`, `<option value="0">未分组</option>`].concat(state.groups.map((group) => `<option value="${group.id}">${escapeHtml(group.group_name)}</option>`)).join("");
    if (dom.groupFilter) dom.groupFilter.innerHTML = options;
    if (dom.groupSelect) dom.groupSelect.innerHTML = [`<option value="">未分组</option>`].concat(state.groups.map((group) => `<option value="${group.id}">${escapeHtml(group.group_name)}</option>`)).join("");
  }

  function filteredTasks() {
    const groupValue = dom.groupFilter?.value ?? "";
    const keyword = String(dom.taskSearch?.value || "").trim().toLowerCase();
    return state.tasks.filter((task) => {
      if (groupValue === "0" && task.group_id) return false;
      if (groupValue && groupValue !== "0" && Number(task.group_id || 0) !== Number(groupValue)) return false;
      if (keyword && !String(task.task_name || "").toLowerCase().includes(keyword)) return false;
      return true;
    });
  }

  function renderList() {
    if (!dom.list) return;
    const tasks = filteredTasks();
    if (!tasks.length) {
      dom.list.innerHTML = `<div class="op-task-empty">暂无任务</div>`;
      return;
    }
    const grouped = new Map();
    tasks.forEach((task) => {
      const key = task.group_id ? String(task.group_id) : "0";
      if (!grouped.has(key)) grouped.set(key, []);
      grouped.get(key).push(task);
    });
    dom.list.innerHTML = [...grouped.entries()].map(([key, items]) => `
      <section class="op-task-group">
        <div class="op-task-group__title">${escapeHtml(key === "0" ? "未分组" : groupName(key))}</div>
        ${items.map((task) => {
          const active = Number(task.id) === currentId();
          const status = String(task.status || "draft");
          return `<article class="op-task-item${active ? " is-active" : ""}" data-task-id="${task.id}">
            <div class="op-task-item__top"><strong>${escapeHtml(task.task_name || "未命名任务")}</strong><span class="op-task-badge is-${escapeHtml(status)}">${escapeHtml(labels.status[status] || status)}</span></div>
            <div class="op-task-actions"><button class="op-task-button is-soft" type="button" data-task-action="edit">编辑</button></div>
          </article>`;
        }).join("")}
      </section>
    `).join("");
  }

  function setCurrentTask(task) {
    state.currentTask = task ? { ...task } : null;
    dom.empty.hidden = Boolean(task);
    dom.form.hidden = !task;
    if (!task) {
      renderList();
      return;
    }
    const content = operationContent(task);
    setValue("task_name", task.task_name || "");
    setValue("group_id", task.group_id || "");
    setValue("status", task.status || "draft");
    setValue("description", task.description || "");
    setValue("send_time", task.send_time || "10:00");
    setValue("target_audience_code", task.target_audience_code || "operating");
    setValue("audience_day_offset", task.audience_day_offset || 1);
    setMode(content.content_mode, false);
    renderList();
  }

  async function refreshTask() {
    const data = await requestJson(withId(endpoints.taskBase, currentId()));
    const task = data.task;
    const index = state.tasks.findIndex((item) => Number(item.id) === Number(task.id));
    if (index >= 0) state.tasks[index] = task;
    setCurrentTask(task);
    return task;
  }

  async function loadProfileTemplates() {
    const data = await requestJson(endpoints.profileOptions);
    state.profileTemplates = data.items || data.options || data.templates || [];
  }

  function normalizeSegments(raw) {
    const rows = Array.isArray(raw) ? raw : [];
    return rows.map((item) => ({
      segment_key: item.segment_key || item.category_key || item.profile_segment_key || item.key || String(item.id || ""),
      segment_name: item.segment_name || item.category_name || item.profile_segment_name || item.name || item.label || item.segment_key || String(item.id || ""),
      hit_count: item.hit_count ?? item.count ?? item.preview_count,
    })).filter((item) => item.segment_key);
  }

  async function loadProfileSegments(templateId) {
    if (!templateId) {
      state.profileSegments = [];
      return [];
    }
    const data = await requestJson(withId(endpoints.profileDetailBase, templateId));
    const bundle = data.template_bundle || data.bundle || data;
    const template = bundle.template || data.template || {};
    state.profileSegments = normalizeSegments(bundle.categories || bundle.segments || bundle.profile_segments || template.categories || template.segments || []);
    return state.profileSegments;
  }

  async function loadBehaviorRules() {
    const data = await requestJson(endpoints.behaviorRules);
    state.behaviorRules = data.rules || [];
  }

  async function loadAgents() {
    const data = await requestJson(endpoints.agents);
    state.agents = data.items || data.agents || data.options || [];
  }

  async function safeLoadAuxiliary() {
    const results = await Promise.allSettled([loadProfileTemplates(), loadBehaviorRules(), loadAgents()]);
    results.forEach((result) => {
      if (result.status === "rejected") {
        console.warn("[automation_operation_orchestration_panel] auxiliary load failed", result.reason);
      }
    });
  }

  async function loadTasks() {
    const data = await requestJson(endpoints.tasks);
    state.groups = data.groups || [];
    state.tasks = data.tasks || data.items || [];
    syncGroupControls();
    const selected = state.currentTask ? state.tasks.find((item) => Number(item.id) === currentId()) : state.tasks[0];
    setCurrentTask(selected || null);
  }

  async function saveBaseTask(statusOverride = "", silent = false) {
    if (!state.currentTask) throw new Error("请先选择一个运营任务");
    const payload = {
      metadata: {
        ...(state.currentTask.metadata || {}),
        description: String(getValue("description") || "").trim(),
        send_time: getValue("send_time") || "10:00",
        target_audience_code: getValue("target_audience_code") || "operating",
        audience_day_offset: Number(getValue("audience_day_offset") || 1),
      },
      config: state.currentTask.config || {},
    };
    const data = await requestJson(withId(endpoints.taskBase, currentId()), { method: "PUT", body: JSON.stringify(payload) });
    const task = data.task;
    if (statusOverride) task.status = statusOverride;
    const index = state.tasks.findIndex((item) => Number(item.id) === Number(task.id));
    if (index >= 0) state.tasks[index] = task;
    setCurrentTask(task);
    if (!silent) showFeedback(dom.feedback, "任务已保存", true);
    return task;
  }

  async function createTask() {
    const stamp = Date.now();
    const data = await requestJson(endpoints.tasks, {
      method: "POST",
      body: JSON.stringify({
        task_name: "新运营任务",
        task_code: `next_operation_task_${stamp}`,
        task_type: "metadata",
        status: "draft",
        idempotency_key: `next-operation-task-${stamp}`,
        operator: "frontend",
      }),
    });
    state.tasks.unshift(data.task);
    setCurrentTask(data.task);
    showFeedback(dom.listFeedback, "已新增运营任务", true);
  }

  async function createGroup() {
    const name = String(window.prompt("请输入分组名称", "") || "").trim();
    if (!name) return;
    state.groups.push({ id: Date.now(), group_name: name });
    syncGroupControls();
    showFeedback(dom.listFeedback, "已新增本地分组", true);
  }

  async function previewAudience() {
    if (!state.currentTask) return;
    state.preview = {};
    dom.previewTotal.textContent = "-";
    showFeedback(dom.feedback, "当前页面仅刷新外层任务字段，发送内容请进入标准组件配置。", true);
  }

  async function updateStrategy(payload) {
    const data = await requestJson(`${withId(endpoints.taskBase, currentId())}/send-strategy`, {
      method: "PUT",
      body: JSON.stringify(payload),
    });
    const task = data.task;
    const index = state.tasks.findIndex((item) => Number(item.id) === Number(task.id));
    if (index >= 0) state.tasks[index] = task;
    setCurrentTask(task);
    return task;
  }

  async function saveContent(url, body) {
    await requestJson(url, { method: "PUT", body: JSON.stringify(body) });
    await refreshTask();
    showFeedback(dom.feedback, "发送内容已保存", true);
  }

  function findSegmentContent(segmentKey) {
    const content = operationContent();
    const row = (content.segment_contents_json || []).find((item) => String(item.segment_key) === String(segmentKey));
    return row?.content_package || row || {};
  }

  function renderUnified(content) {
    const unified = content.unified_content_json || {};
    return `
      <div class="op-task-strategy-head">
        <div><h4>统一内容</h4><div class="op-task-muted">${escapeHtml(contentSummary(unified))}</div></div>
        <button class="op-task-button is-soft" type="button" data-config-unified>配置话术和素材</button>
      </div>`;
  }

  function renderProfile(content) {
    const selectedTemplateId = Number(content.profile_segment_template_id || 0);
    const options = [`<option value="">请选择画像模板</option>`].concat(state.profileTemplates.map((item) => {
      const id = item.id || item.template_id || item.value || "";
      const name = item.label || item.name || item.template_name || item.code || id;
      return `<option value="${escapeHtml(id)}" ${Number(id) === selectedTemplateId ? "selected" : ""}>${escapeHtml(name)}</option>`;
    })).join("");
    const rows = state.profileSegments.length ? state.profileSegments.map((segment) => {
      const current = findSegmentContent(segment.segment_key);
      const count = segment.hit_count === undefined ? "" : `<span class="op-task-chip">${Number(segment.hit_count)} 人</span>`;
      return `<article class="op-task-segment" data-profile-segment="${escapeHtml(segment.segment_key)}" data-segment-name="${escapeHtml(segment.segment_name)}">
        <div class="op-task-segment-row">
          <div><strong>${escapeHtml(segment.segment_name)}</strong><div class="op-task-muted">${escapeHtml(segment.segment_key)} ${count}</div><div class="op-task-muted">${escapeHtml(contentSummary(current))}</div></div>
          <button class="op-task-button is-soft" type="button" data-config-profile-segment="${escapeHtml(segment.segment_key)}">配置话术和素材</button>
        </div>
      </article>`;
    }).join("") : `<div class="op-task-empty">当前画像模板还没有可填写的分层，请先选择包含分层分类的画像模板。</div>`;
    return `
      <label class="op-task-field"><span>画像模板</span><select data-profile-template-select>${options}</select></label>
      <div class="op-task-segments">${rows}</div>`;
  }

  function renderBehavior() {
    const rule = state.behaviorRules[0] || { rule_key: "default_message_count", rule_name: "默认：消息数三层", segments: [
      { segment_key: "lt_2", segment_name: "消息少于 2" },
      { segment_key: "between_2_9", segment_name: "消息 2-9" },
      { segment_key: "gte_10", segment_name: "消息大于等于 10" },
    ] };
    const rows = (rule.segments || []).map((segment) => {
      const current = findSegmentContent(segment.segment_key);
      return `<article class="op-task-segment" data-behavior-segment="${escapeHtml(segment.segment_key)}" data-segment-name="${escapeHtml(segment.segment_name)}">
        <div class="op-task-segment-row">
          <div><strong>${escapeHtml(segment.segment_name)}</strong><div class="op-task-muted">${escapeHtml(segment.segment_key)}</div><div class="op-task-muted">${escapeHtml(contentSummary(current))}</div></div>
          <button class="op-task-button is-soft" type="button" data-config-behavior-segment="${escapeHtml(segment.segment_key)}">配置话术和素材</button>
        </div>
      </article>`;
    }).join("");
    return `
      <label class="op-task-field"><span>消息分层规则</span><select data-behavior-rule-select><option value="${escapeHtml(rule.rule_key)}">${escapeHtml(rule.rule_name || "默认：消息数三层")}</option></select></label>
      <div class="op-task-segments">${rows}</div>`;
  }

  function renderAgent(content) {
    const agentConfig = content.agent_config_json || {};
    const options = [`<option value="">请选择智能体</option>`].concat(state.agents.map((agent) => {
      const code = agent.agent_code || agent.code || agent.value || "";
      const name = agent.agent_name || agent.name || agent.label || code;
      return `<option value="${escapeHtml(code)}" ${String(agentConfig.agent_code || "") === String(code) ? "selected" : ""}>${escapeHtml(name)}</option>`;
    })).join("");
    return `
      <label class="op-task-field"><span>智能体</span><select data-agent-select>${options}</select></label>
      <div class="op-task-strategy-head">
        <div><h4>Agent 个性化素材</h4><div class="op-task-muted">${escapeHtml(contentSummary(agentConfig, true))}</div></div>
        <button class="op-task-button is-soft" type="button" data-config-agent-materials>配置素材</button>
      </div>`;
  }

  function renderStrategyPanel() {
    if (!state.currentTask) return;
    const content = operationContent();
    const mode = normalizeContentMode(content.content_mode || "unified");
    root.querySelectorAll("[data-mode]").forEach((button) => button.classList.toggle("is-active", button.dataset.mode === mode));
    if (mode === "profile_layered") dom.strategyPanel.innerHTML = renderProfile(content);
    else if (mode === "behavior_layered") dom.strategyPanel.innerHTML = renderBehavior(content);
    else if (mode === "agent") dom.strategyPanel.innerHTML = renderAgent(content);
    else dom.strategyPanel.innerHTML = renderUnified(content);
  }

  async function setMode(mode, updateTask = true) {
    if (!state.currentTask) return;
    mode = normalizeContentMode(mode);
    const content = operationContent();
    if (!updateTask) {
      renderStrategyPanel();
      return;
    }
    if (mode === "profile_layered") {
      await loadProfileTemplates().catch(() => {});
    }
    if (mode === "behavior_layered") {
      await loadBehaviorRules().catch(() => {});
      await updateStrategy({ content_mode: "behavior_layered" });
      return;
    }
    if (mode === "agent") {
      await loadAgents().catch(() => {});
      if (content.agent_config_json.agent_code) await updateStrategy({ content_mode: "agent", agent_code: content.agent_config_json.agent_code });
      else {
        state.currentTask.config = { ...(state.currentTask.config || {}), operation_content: { ...content, content_mode: "agent" } };
        renderStrategyPanel();
      }
      return;
    }
    await updateStrategy({ content_mode: "unified" });
  }

  function openSendContentComposer(options) {
    if (!window.AICRMSendContentComposer || typeof window.AICRMSendContentComposer.open !== "function") {
      showFeedback(dom.feedback, "标准内容编辑器未加载，请刷新页面后重试");
      return;
    }
    window.AICRMSendContentComposer.open(options || {});
  }

  function openUnifiedComposer() {
    const content = operationContent();
    openSendContentComposer({
      title: "统一内容",
      textEnabled: true,
      value: content.unified_content_json || {},
      onConfirm: (contentPackage) => saveContent(`${withId(endpoints.taskBase, currentId())}/send-content/unified`, { content_package: contentPackage }),
    });
  }

  function openProfileComposer(segmentKey, segmentName) {
    const content = operationContent();
    const templateId = Number(dom.strategyPanel.querySelector("[data-profile-template-select]")?.value || content.profile_segment_template_id || 0);
    if (!templateId) {
      showFeedback(dom.feedback, "请先选择画像模板");
      return;
    }
    openSendContentComposer({
      title: segmentName,
      textEnabled: true,
      value: findSegmentContent(segmentKey),
      onConfirm: (contentPackage) => saveContent(`${withId(endpoints.taskBase, currentId())}/send-content/profile-segments/${encodeURIComponent(segmentKey)}`, {
        profile_segment_template_id: templateId,
        segment_name: segmentName,
        content_package: contentPackage,
      }),
    });
  }

  function openBehaviorComposer(segmentKey, segmentName) {
    openSendContentComposer({
      title: segmentName,
      textEnabled: true,
      value: findSegmentContent(segmentKey),
      onConfirm: (contentPackage) => saveContent(`${withId(endpoints.taskBase, currentId())}/send-content/behavior-segments/${encodeURIComponent(segmentKey)}`, {
        segment_name: segmentName,
        content_package: contentPackage,
      }),
    });
  }

  function openAgentComposer() {
    const agentCode = String(dom.strategyPanel.querySelector("[data-agent-select]")?.value || "").trim();
    if (!agentCode) {
      showFeedback(dom.feedback, "请先选择智能体");
      return;
    }
    const config = operationContent().agent_config_json || {};
    openSendContentComposer({
      title: "Agent 个性化素材",
      textEnabled: false,
      value: {
        content_text: "",
        image_library_ids: config.image_library_ids || [],
        miniprogram_library_ids: config.miniprogram_library_ids || [],
        attachment_library_ids: config.attachment_library_ids || [],
      },
      onConfirm: (contentPackage) => saveContent(`${withId(endpoints.taskBase, currentId())}/send-content/agent-materials`, {
        agent_code: agentCode,
        content_package: contentPackage,
      }),
    });
  }

  root.addEventListener("click", async (event) => {
    try {
      clearFeedback();
      const modeButton = event.target.closest("[data-mode]");
      if (modeButton) await setMode(modeButton.dataset.mode || "unified").catch((error) => showFeedback(dom.feedback, error.message || "切换策略失败"));
      if (event.target.closest("[data-create-task]")) await createTask().catch((error) => showFeedback(dom.listFeedback, error.message || "新增失败"));
      if (event.target.closest("[data-create-group]")) await createGroup().catch((error) => showFeedback(dom.listFeedback, error.message || "新增失败"));
      if (event.target.closest("[data-preview-audience]")) await previewAudience().catch((error) => showFeedback(dom.feedback, error.message || "预览失败"));
      if (event.target.closest("[data-config-unified]")) openUnifiedComposer();
      const profileButton = event.target.closest("[data-config-profile-segment]");
      if (profileButton) openProfileComposer(profileButton.dataset.configProfileSegment || "", profileButton.closest("[data-segment-name]")?.dataset.segmentName || "");
      const behaviorButton = event.target.closest("[data-config-behavior-segment]");
      if (behaviorButton) openBehaviorComposer(behaviorButton.dataset.configBehaviorSegment || "", behaviorButton.closest("[data-segment-name]")?.dataset.segmentName || "");
      if (event.target.closest("[data-config-agent-materials]")) openAgentComposer();
      const actionButton = event.target.closest("[data-task-action]");
      if (actionButton) {
        const taskId = Number(actionButton.closest("[data-task-id]")?.dataset.taskId || 0);
        if (actionButton.dataset.taskAction === "edit") setCurrentTask(state.tasks.find((item) => Number(item.id) === taskId));
      }
    } catch (error) {
      showFeedback(dom.feedback, error.message || "操作失败，请刷新后重试");
    }
  });

  root.addEventListener("change", async (event) => {
    if (event.target.matches("[data-profile-template-select]")) {
      const templateId = Number(event.target.value || 0);
      if (templateId) {
        await updateStrategy({ content_mode: "profile_layered", profile_segment_template_id: templateId }).catch((error) => showFeedback(dom.feedback, error.message || "画像模板保存失败"));
        await loadProfileSegments(templateId).catch((error) => showFeedback(dom.feedback, error.message || "画像模板详情加载失败"));
      } else {
        state.profileSegments = [];
      }
      renderStrategyPanel();
    }
    if (event.target.matches("[data-agent-select]")) {
      const agentCode = String(event.target.value || "").trim();
      if (agentCode) await updateStrategy({ content_mode: "agent", agent_code: agentCode }).catch((error) => showFeedback(dom.feedback, error.message || "智能体保存失败"));
    }
  });

  root.addEventListener("input", (event) => {
    if (event.target === dom.taskSearch) renderList();
    if (!state.currentTask || !event.target.matches("[data-field]")) return;
    state.currentTask[event.target.dataset.field] = event.target.value;
  });
  dom.groupFilter?.addEventListener("change", renderList);

  window.__automationOperationSaveDraft = async () => saveBaseTask("draft", true);
  window.__automationOperationPublish = async () => saveBaseTask("active", true);

  (async () => {
    try {
      await safeLoadAuxiliary();
      await loadTasks();
      const content = operationContent();
      if (content.content_mode === "profile_layered" && content.profile_segment_template_id) {
        await loadProfileSegments(content.profile_segment_template_id).catch((error) => showFeedback(dom.feedback, error.message || "画像模板详情加载失败"));
      }
      renderStrategyPanel();
      root.dataset.operationPanelReady = "1";
    } catch (error) {
      root.dataset.operationPanelError = error.message || "运营任务加载失败";
      showFeedback(dom.feedback, error.message || "运营任务加载失败");
    }
  })();
  }

  function boot() {
    const root = document.querySelector("[data-operation-task-root]");
    if (!root) return;
    try {
      initOperationPanel(root);
    } catch (error) {
      root.dataset.operationPanelError = error.message || "初始化失败";
      const feedback = root.querySelector("[data-task-feedback]");
      if (feedback) {
        feedback.textContent = root.dataset.operationPanelError;
        feedback.style.display = "block";
      }
    }
  }

  window.AICRMAutomationOperationPanel = { init: initOperationPanel };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
