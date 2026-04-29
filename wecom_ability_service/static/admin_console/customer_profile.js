function customerProfileRoot() {
  return document.querySelector("[data-customer-profile-root]");
}

var AdminApi = window.AdminApi || {};

var safeJsonParse = AdminApi.safeJsonParse || function safeJsonParse(text) {
  if (!text) return null;
  try {
    return JSON.parse(text);
  } catch (_error) {
    return null;
  }
};

var escapeHtml = AdminApi.escapeHtml || function escapeHtml(value) {
  return String(value || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
};

function customerPulseAccessHeaders(root) {
  const headers = {};
  if (!root || !root.dataset) return headers;
  if (root.dataset.customerPulseTenantKey) {
    headers["X-Tenant-Key"] = root.dataset.customerPulseTenantKey;
  }
  if (root.dataset.customerPulseActorUserid) {
    headers["X-Admin-Userid"] = root.dataset.customerPulseActorUserid;
  }
  if (root.dataset.customerPulseActorRole) {
    headers["X-Admin-Role"] = root.dataset.customerPulseActorRole;
  }
  return headers;
}

var requestJson = AdminApi.requestJson || function adminApiRequestJsonUnavailable() {
  return Promise.reject(new Error("AdminApi.requestJson unavailable"));
};

function requestCustomerPulseJson(root, url, options = {}) {
  return requestJson(url, {
    ...options,
    headers: {
      ...customerPulseAccessHeaders(root),
      ...(options.headers || {}),
    },
  });
}

var isPermissionError = AdminApi.isPermissionError || function isPermissionError(error) {
  const message = String((error && error.message) || "");
  return Boolean(error) && (error.status === 401 || error.status === 403 || message.includes("令牌无效"));
};

function toDateTimeLocalValue(value) {
  const text = String(value || "").trim();
  if (!text) return "";
  return text.replace(" ", "T").slice(0, 16);
}

function showSectionError(stateNode, message) {
  if (!stateNode) return;
  stateNode.hidden = false;
  stateNode.classList.remove("admin-state--loading");
  stateNode.classList.add("admin-state--error");
  stateNode.innerHTML = ["<strong>当前无法加载</strong>", `<span>${escapeHtml(message)}</span>`].join("");
}

function showSectionEmpty(stateNode, title, body) {
  if (!stateNode) return;
  stateNode.hidden = false;
  stateNode.classList.remove("admin-state--loading", "admin-state--error");
  stateNode.innerHTML = [`<strong>${escapeHtml(title)}</strong>`, `<span>${escapeHtml(body)}</span>`].join("");
}

function renderLiveTags(payload) {
  const stateNode = document.querySelector("[data-profile-tags-state]");
  const listNode = document.querySelector("[data-profile-tags]");
  if (!stateNode || !listNode) return;
  const tags = payload && Array.isArray(payload.tags) ? payload.tags : [];
  if (!tags.length) {
    listNode.hidden = true;
    showSectionEmpty(stateNode, "当前没有实时标签", "暂未读取到企微标签。");
    return;
  }
  stateNode.hidden = true;
  listNode.hidden = false;
  listNode.innerHTML = tags
    .map((tag) => `<span class="admin-profile-tag">${tag.tag_name || tag.tag_id}</span>`)
    .join("");
}

function renderQuestionnaireAnswers(payload) {
  const stateNode = document.querySelector("[data-profile-questionnaire-state]");
  const wrapNode = document.querySelector("[data-profile-questionnaire-wrap]");
  const bodyNode = document.querySelector("[data-profile-questionnaire-body]");
  if (!stateNode || !wrapNode || !bodyNode) return;
  const answers = payload && Array.isArray(payload.answers) ? payload.answers : [];
  if (!answers.length) {
    wrapNode.hidden = true;
    showSectionEmpty(stateNode, "当前没有问卷记录", "暂未找到可展示的问卷问答。");
    return;
  }
  bodyNode.innerHTML = answers
    .map(
      (item) => `
        <tr>
          <td>${item.question || "未命名问题"}</td>
          <td>${item.answer || "未填写"}</td>
        </tr>
      `,
    )
    .join("");
  stateNode.hidden = true;
  wrapNode.hidden = false;
}

function renderMessages(payload) {
  const stateNode = document.querySelector("[data-profile-messages-state]");
  const listNode = document.querySelector("[data-profile-messages]");
  if (!stateNode || !listNode) return;
  const messages = payload && Array.isArray(payload.messages) ? payload.messages : [];
  if (!messages.length) {
    listNode.hidden = true;
    showSectionEmpty(stateNode, "当前没有聊天记录", "暂未找到聊天内容。");
    return;
  }
  listNode.innerHTML = messages
    .map(
      (item) => `
        <article class="admin-profile-message">
          <div class="admin-profile-message-meta">
            <span>${escapeHtml(item.send_time || "未知时间")}</span>
            <span>${escapeHtml(item.speaker || "未知发送方")}</span>
          </div>
          <div class="admin-profile-message-content">${escapeHtml(item.content || "无内容")}</div>
        </article>
      `,
    )
    .join("");
  stateNode.hidden = true;
  listNode.hidden = false;
}

function customerPulseElements() {
  return {
    state: document.querySelector("[data-customer-pulse-state]"),
    widget: document.querySelector("[data-customer-pulse-widget]"),
    chips: document.querySelector("[data-customer-pulse-chips]"),
    summary: document.querySelector("[data-customer-pulse-summary]"),
    detail: document.querySelector("[data-customer-pulse-detail]"),
    evidence: document.querySelector("[data-customer-pulse-evidence]"),
    actions: document.querySelector("[data-customer-pulse-actions]"),
    editor: document.querySelector("[data-customer-pulse-editor]"),
    feedback: document.querySelector("[data-customer-pulse-feedback]"),
  };
}

function customerPulseInlineStateHtml(title, body, tone) {
  const className =
    tone === "error"
      ? "admin-state admin-state--inline admin-state--error"
      : "admin-state admin-state--inline";
  return `<div class="${className}"><strong>${escapeHtml(title)}</strong><span>${escapeHtml(body)}</span></div>`;
}

function customerPulseActionButtons(card) {
  const buttons = [];
  if (card && card.draft_editor_available) {
    buttons.push({ action_type: "generate_reply_draft", action_label: "编辑草稿" });
  }
  (card && Array.isArray(card.supported_action_buttons) ? card.supported_action_buttons : []).forEach((item) => {
    if (!item || !item.action_type) return;
    if (buttons.some((button) => button.action_type === item.action_type)) return;
    buttons.push(item);
  });
  return buttons;
}

function customerPulseEvidenceRefsHtml(items) {
  const evidence = Array.isArray(items) ? items : [];
  if (!evidence.length) {
    return customerPulseInlineStateHtml("暂无证据线索", "当前没有可展示的 evidence refs。");
  }
  return evidence
    .map(
      (item) => `
        <article class="admin-profile-message">
          <div class="admin-profile-message-meta">
            <span>${escapeHtml(item.title || item.sourceType || "证据")}</span>
            <span>${escapeHtml(item.eventTime || "-")}</span>
          </div>
          <div class="admin-profile-message-content">${escapeHtml(
            [item.sourceType, item.sourceId].filter(Boolean).join(" · ") || "原始记录引用",
          )}</div>
        </article>
      `,
    )
    .join("");
}

function customerPulseEvidenceItemsHtml(items) {
  const evidence = Array.isArray(items) ? items : [];
  if (!evidence.length) {
    return customerPulseInlineStateHtml("暂无可展开证据", "当前没有命中可展示的原始证据内容。");
  }
  return evidence
    .map(
      (item) => `
        <article class="admin-profile-message">
          <div class="admin-profile-message-meta">
            <span>${escapeHtml(item.title || "证据")}</span>
            <span>${escapeHtml(item.event_time || item.source || "-")}</span>
          </div>
          <div class="admin-profile-message-content">${escapeHtml(item.detail || "暂无详情")}</div>
        </article>
      `,
    )
    .join("");
}

function customerPulseFormFields(preview) {
  const actionType = String((preview && preview.action_type) || "");
  const payload = (preview && preview.preview) || {};
  if (actionType === "generate_reply_draft") {
    return `
      <label>
        <span>草稿内容</span>
        <textarea rows="6" data-customer-pulse-field="draft_message">${escapeHtml(payload.draft_message || "")}</textarea>
        <small>${escapeHtml(payload.draft_notice || "所有外发消息默认只生成草稿，需人工确认后再发送。")}</small>
      </label>
    `;
  }
  if (actionType === "create_followup_task") {
    return `
      <label>
        <span>任务标题</span>
        <input type="text" data-customer-pulse-field="task_title" value="${escapeHtml(payload.task_title || "")}">
      </label>
      <label>
        <span>截止时间</span>
        <input type="datetime-local" data-customer-pulse-field="due_at" value="${escapeHtml(toDateTimeLocalValue(payload.due_at || ""))}">
      </label>
    `;
  }
  if (actionType === "update_followup_segment") {
    const currentSegment = String(payload.followup_segment || "focus");
    const options = [
      { value: "focus", label: "重点跟进" },
      { value: "normal", label: "普通跟进" },
      { value: "core", label: "Core" },
      { value: "top", label: "Top" },
    ];
    return `
      <label>
        <span>目标阶段</span>
        <select data-customer-pulse-field="followup_segment">
          ${options
            .map(
              (option) =>
                `<option value="${escapeHtml(option.value)}"${option.value === currentSegment ? " selected" : ""}>${escapeHtml(option.label)}</option>`,
            )
            .join("")}
        </select>
      </label>
    `;
  }
  if (actionType === "update_tags") {
    return `
      <label>
        <span>新增标签 ID</span>
        <input type="text" data-customer-pulse-field="add_tag_ids" value="${escapeHtml((payload.add_tag_ids || []).join(","))}" placeholder="tag_a,tag_b">
      </label>
      <label>
        <span>移除标签 ID</span>
        <input type="text" data-customer-pulse-field="remove_tag_ids" value="${escapeHtml((payload.remove_tag_ids || []).join(","))}" placeholder="tag_c,tag_d">
      </label>
    `;
  }
  if (actionType === "set_followup_reminder") {
    return `
      <label>
        <span>提醒时间</span>
        <input type="datetime-local" data-customer-pulse-field="due_at" value="${escapeHtml(toDateTimeLocalValue(payload.due_at || ""))}">
      </label>
    `;
  }
  return "";
}

let currentCustomerPulsePayload = null;
let currentCustomerPulsePreview = null;
let currentCustomerPulsePreviewError = "";
let currentCustomerPulseEvidencePayload = null;
let currentCustomerPulseEvidenceError = "";

function renderCustomerPulse(payload) {
  const elements = customerPulseElements();
  if (!elements.state) return;
  const detailPayload = (payload && payload.customer_pulse) || {};
  const card = detailPayload.card || null;
  currentCustomerPulsePayload = detailPayload;
  if (!detailPayload.enabled) {
    if (elements.widget) elements.widget.hidden = true;
    showSectionEmpty(elements.state, "AI 下一步未启用", "当前 feature flag 关闭。");
    return;
  }
  if (!card) {
    if (elements.widget) elements.widget.hidden = true;
    showSectionEmpty(elements.state, "当前暂不展示 AI 下一步", "当前客户还没有可执行的行动卡，或证据不足。");
    return;
  }
  elements.state.hidden = true;
  if (elements.widget) {
    elements.widget.hidden = false;
  }
  if (elements.chips) {
    elements.chips.hidden = false;
    elements.chips.innerHTML = `
      <span class="admin-inline-chip admin-inline-chip--neutral">${escapeHtml(card.card_status_label || "待处理")}</span>
      <span class="admin-inline-chip admin-inline-chip--${card.priority === "high" ? "warn" : "ok"}">${escapeHtml(card.priority_label || "常规")}</span>
      <span class="admin-inline-chip admin-inline-chip--neutral">${escapeHtml(card.confidence === null || card.confidence === undefined ? "规则建议" : `置信度 ${Number(card.confidence).toFixed(2)}`)}</span>
    `;
  }
  if (elements.summary) {
    elements.summary.hidden = false;
    elements.summary.className = `admin-state admin-state--inline${card.draft_blocked_by_ai ? " admin-state--error" : ""}`;
    elements.summary.innerHTML = [
      `<strong>${escapeHtml(card.draft_blocked_by_ai ? "已降级为规则建议" : "当前判断")}</strong>`,
      `<span>${escapeHtml(card.current_judgement || card.summary || "暂无摘要")}</span>`,
    ].join("");
  }
  if (elements.detail) {
    elements.detail.hidden = false;
    elements.detail.innerHTML = `
      <div>
        <dt>建议动作</dt>
        <dd>${escapeHtml(card.suggested_action_label || "人工确认后决定下一步")}</dd>
      </div>
      <div>
        <dt>负责人</dt>
        <dd>${escapeHtml(card.owner_display_name || card.owner_userid || "未分配")}</dd>
      </div>
      <div>
        <dt>当前阶段</dt>
        <dd>${escapeHtml(card.stage_label || "未分类")}</dd>
      </div>
      <div>
        <dt>最近事件</dt>
        <dd>${escapeHtml((card.latest_event && card.latest_event.title) || "最近事件")} · ${escapeHtml((card.latest_event && card.latest_event.detail) || "暂无详情")}</dd>
      </div>
      <div>
        <dt>为什么现在</dt>
        <dd>${escapeHtml(card.why_now || "当前信号已达到行动阈值")}</dd>
      </div>
      <div>
        <dt>处理要求</dt>
        <dd>${escapeHtml(card.draft_notice || "所有外发消息默认只生成草稿，由人工确认。")}</dd>
      </div>
    `;
  }
  if (elements.evidence) {
    const refs = Array.isArray(card.evidence_refs) ? card.evidence_refs : [];
    const permissions = card.permissions || {};
    const canExpandEvidence = Boolean(permissions.evidence_view && card.evidence_expand_available);
    elements.evidence.hidden = false;
    elements.evidence.innerHTML = `
      ${customerPulseEvidenceRefsHtml(refs)}
      ${
        currentCustomerPulseEvidencePayload && Array.isArray(currentCustomerPulseEvidencePayload.evidence)
          ? customerPulseEvidenceItemsHtml(currentCustomerPulseEvidencePayload.evidence)
          : ""
      }
      ${
        Array.isArray(currentCustomerPulseEvidencePayload && currentCustomerPulseEvidencePayload.inaccessible_refs) &&
        currentCustomerPulseEvidencePayload.inaccessible_refs.length
          ? customerPulseInlineStateHtml(
              "部分证据未展示",
              `有 ${currentCustomerPulseEvidencePayload.inaccessible_refs.length} 条 evidence refs 未通过原始边界校验。`,
            )
          : ""
      }
      ${
        !canExpandEvidence && refs.length
          ? customerPulseInlineStateHtml("当前角色无权展开原始证据", "可以看到 evidence refs，但不能直接读取原始记录内容。")
          : ""
      }
      ${currentCustomerPulseEvidenceError ? customerPulseInlineStateHtml("当前无法展开原始证据", currentCustomerPulseEvidenceError, "error") : ""}
    `;
  }
  if (elements.actions) {
    const buttons = customerPulseActionButtons(card);
    const feedbackButtons = Array.isArray(card.feedback_actions) ? card.feedback_actions : [];
    const canExpandEvidence = Boolean((card.permissions || {}).evidence_view && card.evidence_expand_available);
    elements.actions.hidden = !buttons.length && !feedbackButtons.length && !canExpandEvidence;
    elements.actions.innerHTML = `
      ${buttons
        .map(
          (item) => `
            <button
              type="button"
              class="admin-button ${item.action_type === card.suggested_action_type ? "admin-button--primary" : "admin-button--ghost"}"
              data-customer-pulse-preview
              data-card-id="${card.id}"
              data-action-type="${escapeHtml(item.action_type)}"
            >
              ${escapeHtml(item.action_label || "动作")}
            </button>
          `,
        )
        .join("")}
      ${
        canExpandEvidence
          ? `
            <button
              type="button"
              class="admin-button admin-button--ghost"
              data-customer-pulse-evidence-load
              data-card-id="${card.id}"
            >
              查看原始证据
            </button>
          `
          : ""
      }
      ${feedbackButtons
        .map(
          (item) => `
            <button
              type="button"
              class="admin-button admin-button--ghost"
              data-customer-pulse-feedback-action
              data-card-id="${card.id}"
              data-feedback-type="${escapeHtml(item.type || "")}"
            >
              ${escapeHtml(item.label || item.type || "反馈")}
            </button>
          `,
        )
        .join("")}
    `;
  }
  if (elements.editor) {
    const buttons = customerPulseActionButtons(card);
    if (currentCustomerPulsePreview && currentCustomerPulsePreview.action_type) {
      elements.editor.hidden = false;
      elements.editor.innerHTML = `
        <form class="admin-form-grid admin-form-grid--stacked" data-customer-pulse-action-form data-card-id="${card.id}" data-action-type="${escapeHtml(currentCustomerPulsePreview.action_type || "")}">
          <div class="admin-state admin-state--inline">
            <strong>${escapeHtml(currentCustomerPulsePreview.action_label || "动作预览")}</strong>
            <span>${escapeHtml(currentCustomerPulsePreview.action_title || currentCustomerPulsePreview.why_now || "请确认后执行")}</span>
          </div>
          ${
            currentCustomerPulsePreview.undo_notice
              ? `
                <div class="admin-state admin-state--inline">
                  <strong>撤销窗口</strong>
                  <span>${escapeHtml(currentCustomerPulsePreview.undo_notice)}</span>
                </div>
              `
              : ""
          }
          ${customerPulseFormFields(currentCustomerPulsePreview)}
          <div class="admin-customer-pulse-detail__form-actions">
            <button type="submit" class="admin-button admin-button--primary">确认并保存</button>
          </div>
        </form>
      `;
    } else if (currentCustomerPulsePreviewError) {
      elements.editor.hidden = false;
      elements.editor.innerHTML = `<div class="admin-state admin-state--error"><strong>当前无法加载动作预览</strong><span>${escapeHtml(currentCustomerPulsePreviewError)}</span></div>`;
    } else if (buttons.length) {
      elements.editor.hidden = false;
      elements.editor.innerHTML = customerPulseInlineStateHtml("先预览再执行", "选择一个候选动作后，系统才会加载可编辑草稿或执行字段。");
    } else {
      elements.editor.hidden = false;
      elements.editor.innerHTML = customerPulseInlineStateHtml("当前角色只能查看", "该卡片已对当前角色隐藏所有可执行动作。");
    }
  }
}

function customerPulseFeedback(message, tone) {
  const node = customerPulseElements().feedback;
  if (!node) return;
  node.hidden = false;
  node.className = `admin-state admin-state--inline${tone === "error" ? " admin-state--error" : ""}`;
  node.innerHTML = `<strong>${tone === "error" ? "处理失败" : "处理结果"}</strong><span>${escapeHtml(message)}</span>`;
}

function currentCustomerPulseCard() {
  return currentCustomerPulsePayload && currentCustomerPulsePayload.card ? currentCustomerPulsePayload.card : null;
}

function customerPulseActionPayload(form) {
  const actionType = String(form.dataset.actionType || "");
  if (actionType === "generate_reply_draft") {
    return { draft_message: form.querySelector("[data-customer-pulse-field='draft_message']")?.value || "" };
  }
  if (actionType === "create_followup_task") {
    return {
      task_title: form.querySelector("[data-customer-pulse-field='task_title']")?.value || "",
      due_at: (form.querySelector("[data-customer-pulse-field='due_at']")?.value || "").replace("T", " "),
    };
  }
  if (actionType === "update_followup_segment") {
    return { followup_segment: form.querySelector("[data-customer-pulse-field='followup_segment']")?.value || "" };
  }
  if (actionType === "update_tags") {
    return {
      add_tag_ids: (form.querySelector("[data-customer-pulse-field='add_tag_ids']")?.value || "")
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean),
      remove_tag_ids: (form.querySelector("[data-customer-pulse-field='remove_tag_ids']")?.value || "")
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean),
    };
  }
  if (actionType === "set_followup_reminder") {
    return { due_at: (form.querySelector("[data-customer-pulse-field='due_at']")?.value || "").replace("T", " ") };
  }
  return {};
}

function customerPulseCardApiUrl(root, cardId, suffix) {
  return `${root.dataset.customerPulseCardApiBase}/${cardId}${suffix}`;
}

function loadCustomerPulsePreview(root, cardId, actionType, options = {}) {
  const card = currentCustomerPulseCard();
  if (!card) return Promise.resolve(null);
  currentCustomerPulsePreview = null;
  currentCustomerPulsePreviewError = "";
  renderCustomerPulse({ customer_pulse: currentCustomerPulsePayload });
  return requestCustomerPulseJson(root, customerPulseCardApiUrl(root, cardId, "/actions/preview"), {
    method: "POST",
    body: {
      action_type: actionType || card.suggested_action_type,
      track_click: Boolean(options.trackClick),
      metric_source: options.metricSource || "customer_profile_widget",
    },
  })
    .then((payload) => {
      currentCustomerPulsePreview = payload.preview || {};
      currentCustomerPulsePreviewError = "";
      renderCustomerPulse({ customer_pulse: currentCustomerPulsePayload });
      return currentCustomerPulsePreview;
    })
    .catch((error) => {
      currentCustomerPulsePreview = null;
      currentCustomerPulsePreviewError = error.message || "请稍后重试。";
      renderCustomerPulse({ customer_pulse: currentCustomerPulsePayload });
      return null;
    });
}

function loadCustomerPulseEvidence(root, cardId) {
  const card = currentCustomerPulseCard();
  if (!card) return Promise.resolve(null);
  currentCustomerPulseEvidencePayload = null;
  currentCustomerPulseEvidenceError = "";
  renderCustomerPulse({ customer_pulse: currentCustomerPulsePayload });
  return requestCustomerPulseJson(root, customerPulseCardApiUrl(root, cardId, "/evidence"), {
    method: "GET",
  })
    .then((payload) => {
      currentCustomerPulseEvidencePayload = payload;
      currentCustomerPulseEvidenceError = "";
      renderCustomerPulse({ customer_pulse: currentCustomerPulsePayload });
      return payload;
    })
    .catch((error) => {
      currentCustomerPulseEvidencePayload = null;
      currentCustomerPulseEvidenceError = error.message || "请稍后重试。";
      renderCustomerPulse({ customer_pulse: currentCustomerPulsePayload });
      return null;
    });
}

function executeCustomerPulseAction(root, form) {
  const card = currentCustomerPulseCard();
  if (!card) return Promise.resolve(null);
  return requestCustomerPulseJson(root, customerPulseCardApiUrl(root, card.id, "/actions/execute"), {
    method: "POST",
    body: {
      admin_action_token: root.dataset.adminActionToken,
      action_type: form.dataset.actionType || "",
      ...customerPulseActionPayload(form),
    },
  })
    .then((payload) => {
      const execution = (payload && payload.execution) || {};
      const message =
        execution.undo_available && execution.undo_until
          ? `操作已保存，可在 ${execution.undo_until} 前撤销。正在刷新当前客户脉冲。`
          : "操作已保存，正在刷新当前客户脉冲。";
      customerPulseFeedback(message, "success");
      return loadCustomerPulse(root);
    })
    .catch((error) => {
      customerPulseFeedback(error.message || "当前无法执行动作。", "error");
      return null;
    });
}

function submitCustomerPulseFeedback(root, cardId, feedbackType) {
  return requestCustomerPulseJson(root, customerPulseCardApiUrl(root, cardId, "/feedback"), {
    method: "POST",
    body: {
      admin_action_token: root.dataset.adminActionToken,
      feedback_type: feedbackType,
      feedback_source: "customer_profile_widget",
    },
  })
    .then(() => {
      customerPulseFeedback("反馈已记录，正在刷新当前客户脉冲。", "success");
      return loadCustomerPulse(root);
    })
    .catch((error) => {
      customerPulseFeedback(error.message || "当前无法记录反馈。", "error");
      return null;
    });
}

function followupOrchestratorElements() {
  return {
    state: document.querySelector("[data-followup-orchestrator-widget-state]"),
    widget: document.querySelector("[data-followup-orchestrator-widget]"),
    chips: document.querySelector("[data-followup-orchestrator-widget-chips]"),
    detail: document.querySelector("[data-followup-orchestrator-widget-detail]"),
    items: document.querySelector("[data-followup-orchestrator-widget-items]"),
  };
}

function followupMissionTypeLabel(value) {
  const mapping = {
    claim_queue: "待认领客户队列",
    handoff_wave: "团队接力转派波次",
    risk_escalation_wave: "风险升级波次",
    batch_draft_wave: "批量草稿波次",
    priority_wave: "今日优先推进任务包",
  };
  return mapping[String(value || "")] || "团队任务包";
}

function renderFollowupOrchestratorWidget(payload, root) {
  const elements = followupOrchestratorElements();
  if (!elements.state) return;
  if (!payload || !payload.enabled) {
    if (elements.widget) elements.widget.hidden = true;
    showSectionEmpty(elements.state, "团队编排未启用", "当前租户或角色尚未进入团队编排灰度范围。");
    return;
  }
  const missionItems = Array.isArray(payload.mission_items) ? payload.mission_items : [];
  const assignmentSuggestions = Array.isArray(payload.assignment_suggestions) ? payload.assignment_suggestions : [];
  const escalationSuggestions = Array.isArray(payload.escalation_suggestions) ? payload.escalation_suggestions : [];
  const batchSuggestions = Array.isArray(payload.batch_draft_suggestions) ? payload.batch_draft_suggestions : [];
  if (!missionItems.length && !assignmentSuggestions.length && !escalationSuggestions.length && !batchSuggestions.length) {
    if (elements.widget) elements.widget.hidden = true;
    showSectionEmpty(elements.state, "当前未进入团队编排", "这位客户暂时不在任何 mission 中，也没有待审批或待接力建议。");
    return;
  }
  elements.state.hidden = true;
  if (elements.widget) elements.widget.hidden = false;
  if (elements.chips) {
    const chips = [];
    if (missionItems.length) chips.push(`<span class="admin-inline-chip admin-inline-chip--ok">Mission ${escapeHtml(missionItems.length)}</span>`);
    if (assignmentSuggestions.length) chips.push('<span class="admin-inline-chip admin-inline-chip--warn">待接力</span>');
    if (escalationSuggestions.length) chips.push('<span class="admin-inline-chip admin-inline-chip--danger">待升级</span>');
    if (batchSuggestions.length) chips.push('<span class="admin-inline-chip admin-inline-chip--neutral">批量草稿候选</span>');
    elements.chips.hidden = !chips.length;
    elements.chips.innerHTML = chips.join("");
  }
  if (elements.detail) {
    const firstMissionItem = missionItems[0] || {};
    const firstAssignment = assignmentSuggestions[0] || {};
    const firstEscalation = escalationSuggestions[0] || {};
    elements.detail.hidden = false;
    elements.detail.innerHTML = `
      <div>
        <dt>当前任务包</dt>
        <dd>${escapeHtml(followupMissionTypeLabel((firstMissionItem.payload || {}).mission_type))}</dd>
      </div>
      <div>
        <dt>当前建议归属</dt>
        <dd>${escapeHtml(firstMissionItem.suggested_assignee_userid || firstMissionItem.owner_userid || "保持当前 owner")}</dd>
      </div>
      <div>
        <dt>待审批 / 待接力</dt>
        <dd>${escapeHtml(firstAssignment.reason || "当前没有待审批的转派建议")}</dd>
      </div>
      <div>
        <dt>升级状态</dt>
        <dd>${escapeHtml(firstEscalation.reason || "当前没有升级建议")}</dd>
      </div>
      <div>
        <dt>草稿波次</dt>
        <dd>${batchSuggestions.length ? `命中 ${batchSuggestions.length} 个批量草稿 mission` : "当前未命中批量草稿波次"}</dd>
      </div>
      <div>
        <dt>入口</dt>
        <dd><a class="admin-inline-link admin-inline-link--compact" href="${escapeHtml(root.dataset.followupOrchestratorUrl || "#")}">打开团队编排</a></dd>
      </div>
    `;
  }
  if (elements.items) {
    elements.items.hidden = false;
    elements.items.innerHTML = missionItems
      .slice(0, 3)
      .map(
        (item) => `
          <article class="admin-profile-message">
            <div class="admin-profile-message-meta">
              <span>${escapeHtml(item.customer_name || item.external_userid || "客户")}</span>
              <span>${escapeHtml((item.payload || {}).stage_label || (item.payload || {}).stage_key || "未标记阶段")}</span>
              <span>${escapeHtml(item.item_status || "suggested")}</span>
            </div>
            <div class="admin-profile-message-content">${escapeHtml(
              (item.payload || {}).why_now ||
                (item.payload || {}).current_judgement ||
                "当前已进入团队编排，可前往任务包查看详情。",
            )}</div>
          </article>
        `,
      )
      .join("");
  }
}

function loadFollowupOrchestratorWidget(root) {
  const elements = followupOrchestratorElements();
  if (!elements.state || root.dataset.followupOrchestratorEnabled !== "1" || !root.dataset.followupOrchestratorApiUrl) {
    return Promise.resolve(null);
  }
  return requestCustomerPulseJson(root, root.dataset.followupOrchestratorApiUrl)
    .then((payload) => {
      renderFollowupOrchestratorWidget(payload.customer_orchestrator || {}, root);
      return payload.customer_orchestrator || {};
    })
    .catch((error) => {
      if (isPermissionError(error)) {
        showSectionError(elements.state, error.message || "当前角色没有查看团队编排 widget 的权限");
      } else {
        showSectionError(elements.state, error.message || "当前无法加载团队编排状态");
      }
      return null;
    });
}

function loadLiveTags(root) {
  return requestJson(root.dataset.tagsUrl)
    .then((payload) => {
      renderLiveTags(payload);
      return payload;
    })
    .catch((error) => {
      showSectionError(document.querySelector("[data-profile-tags-state]"), error.message || "当前无法加载实时标签");
      return null;
    });
}

function loadQuestionnaireAnswers(root) {
  return requestJson(root.dataset.questionnaireUrl)
    .then((payload) => {
      renderQuestionnaireAnswers(payload);
      return payload;
    })
    .catch((error) => {
      showSectionError(document.querySelector("[data-profile-questionnaire-state]"), error.message || "当前无法加载问卷记录");
      return null;
    });
}

function loadMessages(root, fetchAll) {
  const url = new URL(root.dataset.messagesUrl, window.location.origin);
  if (fetchAll) {
    url.searchParams.set("fetch_all", "1");
  }
  return requestJson(url.toString())
    .then((payload) => {
      renderMessages(payload);
      return payload;
    })
    .catch((error) => {
      showSectionError(document.querySelector("[data-profile-messages-state]"), error.message || "当前无法加载聊天记录");
      return null;
    });
}

function loadCustomerPulse(root) {
  const elements = customerPulseElements();
  if (!elements.state || !root.dataset.pulseUrl) return Promise.resolve(null);
  return requestCustomerPulseJson(root, root.dataset.pulseUrl)
    .then((payload) => {
      currentCustomerPulsePreview = null;
      currentCustomerPulsePreviewError = "";
      currentCustomerPulseEvidencePayload = null;
      currentCustomerPulseEvidenceError = "";
      renderCustomerPulse(payload);
      return payload;
    })
    .catch((error) => {
      showSectionError(elements.state, error.message || "当前无法加载 AI 下一步");
      return null;
    });
}

function wireFetchAllButton(root) {
  const button = document.querySelector("[data-profile-fetch-all-messages]");
  if (!button) return;
  button.addEventListener("click", () => {
    button.disabled = true;
    button.textContent = "正在加载全部聊天记录";
    loadMessages(root, true).finally(() => {
      button.disabled = false;
      button.textContent = "获取全部聊天记录";
    });
  });
}

function scrollToInitialSection(root) {
  const sectionId = root.dataset.initialSection;
  if (!sectionId) return;
  const section = document.getElementById(sectionId);
  if (!section) return;
  window.setTimeout(() => {
    section.scrollIntoView({ block: "start", behavior: "smooth" });
  }, 120);
}

function automationElements() {
  return {
    state: document.querySelector("[data-automation-state]"),
    detail: document.querySelector("[data-automation-detail]"),
    feedback: document.querySelector("[data-automation-feedback]"),
    actionsWrap: document.querySelector("[data-automation-actions]"),
    buttons: Array.from(document.querySelectorAll("[data-automation-action]")),
    inPool: document.querySelector("[data-automation-in-pool]"),
    currentPool: document.querySelector("[data-automation-current-pool]"),
    currentStage: document.querySelector("[data-automation-current-stage]"),
    currentTarget: document.querySelector("[data-automation-current-target]"),
    questionnaireStatus: document.querySelector("[data-automation-questionnaire-status]"),
    latestManualAction: document.querySelector("[data-automation-latest-manual-action]"),
    lastAiPushAt: document.querySelector("[data-automation-last-ai-push-at]"),
    cooldown: document.querySelector("[data-automation-ai-cooldown]"),
  };
}

function setAutomationFeedback(message, tone) {
  const feedback = automationElements().feedback;
  if (!feedback) return;
  feedback.hidden = false;
  feedback.className = `admin-state admin-state--inline${tone === "error" ? " admin-state--error" : ""}`;
  feedback.innerHTML = [`<strong>${tone === "error" ? "执行失败" : "操作结果"}</strong>`, `<span>${message}</span>`].join("");
}

function clearAutomationFeedback() {
  const feedback = automationElements().feedback;
  if (!feedback) return;
  feedback.hidden = true;
  feedback.innerHTML = "";
}

function memberLookupPayload(root) {
  return {
    external_contact_id: root.dataset.externalUserid || "",
  };
}

function actionUrlFor(root, action) {
  const mapping = {
    put_in_pool: root.dataset.automationPutInPoolUrl,
    remove_from_pool: root.dataset.automationRemoveFromPoolUrl,
    set_focus: root.dataset.automationSetFocusUrl,
    set_normal: root.dataset.automationSetNormalUrl,
    mark_won: root.dataset.automationMarkWonUrl,
    unmark_won: root.dataset.automationUnmarkWonUrl,
    push_openclaw: root.dataset.automationPushOpenclawUrl,
  };
  return mapping[action];
}

let automationCooldownTimer = null;

function renderAutomationCooldown(seconds) {
  const elements = automationElements();
  if (!elements.cooldown) return;
  if (!seconds || seconds <= 0) {
    elements.cooldown.textContent = "未冷却";
    return;
  }
  elements.cooldown.textContent = `冷却中，还剩 ${seconds} 秒`;
}

function startAutomationCooldown(seconds, root) {
  window.clearInterval(automationCooldownTimer);
  let remaining = Number(seconds || 0);
  renderAutomationCooldown(remaining);
  if (remaining <= 0) return;
  automationCooldownTimer = window.setInterval(() => {
    remaining -= 1;
    renderAutomationCooldown(remaining);
    if (remaining <= 0) {
      window.clearInterval(automationCooldownTimer);
      loadAutomationMember(root);
    }
  }, 1000);
}

function renderAutomationDetail(detail, root) {
  const elements = automationElements();
  const member = (detail && detail.member) || {};
  const latestManualAction = (detail && detail.latest_manual_action) || {};
  if (!elements.state || !elements.detail || !elements.actionsWrap) return;
  elements.state.hidden = true;
  elements.detail.hidden = false;
  elements.actionsWrap.hidden = false;
  elements.inPool.textContent = member.in_pool ? "是" : "否";
  elements.currentPool.textContent = member.current_pool_label || member.current_pool || "已移出";
  elements.currentStage.textContent = member.current_stage_label || member.current_stage || "已移出";
  elements.currentTarget.textContent = member.current_target_label || member.current_target || "无";
  elements.questionnaireStatus.textContent = detail.questionnaire && detail.questionnaire.status_label
    ? `${detail.questionnaire.status_label}${detail.questionnaire.result_label ? " / " + detail.questionnaire.result_label : ""}`
    : "待提交";
  elements.latestManualAction.textContent = latestManualAction.action
    ? `${latestManualAction.action} · ${latestManualAction.created_at || ""}`
    : "暂无";
  elements.lastAiPushAt.textContent = detail.last_ai_push_at || "暂无";
  const remainingSeconds = Number(detail.ai_cooldown_remaining_seconds || 0);
  startAutomationCooldown(remainingSeconds, root);
  elements.buttons.forEach((button) => {
    const action = button.dataset.automationAction;
    const enabled = Boolean(detail.actions && detail.actions[action] && detail.actions[action].enabled);
    if (action === "push_openclaw" && remainingSeconds > 0) {
      button.disabled = true;
    } else {
      button.disabled = !enabled;
    }
  });
}

function loadAutomationMember(root) {
  const stateNode = document.querySelector("[data-automation-state]");
  const url = root.dataset.automationMemberUrl;
  clearAutomationFeedback();
  if (stateNode) {
    stateNode.hidden = false;
    stateNode.classList.add("admin-state--loading");
  }
  return requestJson(url)
    .then((payload) => {
      renderAutomationDetail(payload.detail || {}, root);
      return payload.detail || {};
    })
    .catch((error) => {
      showSectionError(stateNode, error.message || "当前无法加载自动化状态");
      return null;
    });
}

function runAutomationAction(root, action) {
  const url = actionUrlFor(root, action);
  if (!url) return Promise.resolve(null);
  clearAutomationFeedback();
  const payload = memberLookupPayload(root);
  return requestJson(url, {
    method: "POST",
    body: payload,
  })
    .then((response) => {
      if (action === "push_openclaw" && response.accepted) {
        setAutomationFeedback("已推送给 OpenClaw", "success");
      } else if (response.status === "cooldown_blocked") {
        setAutomationFeedback(`OpenClaw 冷却中，还剩 ${response.remaining_seconds || 0} 秒`, "error");
      } else {
        setAutomationFeedback("操作已执行", "success");
      }
      return loadAutomationMember(root);
    })
    .catch((error) => {
      setAutomationFeedback(error.message || "操作执行失败", "error");
      return null;
    });
}

function wireAutomationActions(root) {
  automationElements().buttons.forEach((button) => {
    button.addEventListener("click", () => {
      if (button.disabled) return;
      const originalText = button.textContent;
      button.disabled = true;
      button.textContent = "处理中";
      runAutomationAction(root, button.dataset.automationAction).finally(() => {
        button.textContent = originalText;
      });
    });
  });
}

function wireCustomerPulseActions(root) {
  document.addEventListener("click", (event) => {
    const previewButton = event.target.closest("[data-customer-pulse-preview]");
    if (previewButton) {
      loadCustomerPulsePreview(root, previewButton.dataset.cardId, previewButton.dataset.actionType, {
        trackClick: true,
        metricSource: "customer_profile_widget_action",
      });
      return;
    }
    const evidenceButton = event.target.closest("[data-customer-pulse-evidence-load]");
    if (evidenceButton) {
      loadCustomerPulseEvidence(root, evidenceButton.dataset.cardId);
      return;
    }
    const feedbackButton = event.target.closest("[data-customer-pulse-feedback-action]");
    if (feedbackButton) {
      submitCustomerPulseFeedback(root, feedbackButton.dataset.cardId, feedbackButton.dataset.feedbackType);
    }
  });
  document.addEventListener("submit", (event) => {
    const form = event.target.closest("[data-customer-pulse-action-form]");
    if (!form) return;
    event.preventDefault();
    executeCustomerPulseAction(root, form);
  });
}

document.addEventListener("DOMContentLoaded", () => {
  const root = customerProfileRoot();
  if (!root) return;
  loadCustomerPulse(root);
  loadFollowupOrchestratorWidget(root);
  loadLiveTags(root);
  loadQuestionnaireAnswers(root);
  loadMessages(root, false);
  loadAutomationMember(root);
  wireFetchAllButton(root);
  wireAutomationActions(root);
  wireCustomerPulseActions(root);
  scrollToInitialSection(root);
});
