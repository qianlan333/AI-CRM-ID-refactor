function pulseInboxRoot() {
  return document.querySelector("[data-customer-pulse-inbox-root]");
}

var adminConsoleApi = window.AdminApi || {};

var safeJsonParse = adminConsoleApi.safeJsonParse || function safeJsonParse(text) {
  try {
    return JSON.parse(text);
  } catch (_error) {
    return null;
  }
};

var escapeHtml = adminConsoleApi.escapeHtml || function escapeHtml(value) {
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

function requestJson(url, options = {}, root = null) {
  const requestOptions = {
    ...options,
    headers: {
      ...customerPulseAccessHeaders(root),
      ...(options.headers || {}),
    },
  };
  if (adminConsoleApi.requestJson) {
    return adminConsoleApi.requestJson(url, requestOptions);
  }
  const finalOptions = {
    ...requestOptions,
    headers: {
      Accept: "application/json",
      ...(requestOptions.body ? { "Content-Type": "application/json" } : {}),
      ...(requestOptions.headers || {}),
    },
  };
  return fetch(url, finalOptions)
    .then((response) =>
      response.text().then((text) => ({
        response,
        payload: text ? safeJsonParse(text) : null,
      })),
    )
    .then(({ response, payload }) => {
      if (!response.ok || (payload && payload.ok === false)) {
        const error = new Error((payload && payload.error) || "request failed");
        error.status = response.status;
        error.payload = payload;
        throw error;
      }
      return payload || { ok: true };
    });
}

var isPermissionError = adminConsoleApi.isPermissionError || function isPermissionError(error) {
  const message = String((error && error.message) || "");
  return error && (error.status === 401 || error.status === 403 || message.includes("令牌无效"));
};

function toDateTimeLocalValue(value) {
  const text = String(value || "").trim();
  if (!text) return "";
  return text.replace(" ", "T").slice(0, 16);
}

function availableActionButtons(card) {
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

function inlineStateHtml(title, body, tone = "inline") {
  const className =
    tone === "error"
      ? "admin-state admin-state--inline admin-state--error"
      : "admin-state admin-state--inline";
  return `<div class="${className}"><strong>${escapeHtml(title)}</strong><span>${escapeHtml(body)}</span></div>`;
}

function evidenceRefsHtml(items) {
  const rows = Array.isArray(items) ? items : [];
  if (!rows.length) {
    return inlineStateHtml("暂无证据线索", "当前没有可展示的 evidence refs。");
  }
  return rows
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

function evidenceItemsHtml(items) {
  const rows = Array.isArray(items) ? items : [];
  if (!rows.length) {
    return inlineStateHtml("暂无可展开证据", "当前没有命中可展示的原始证据内容。");
  }
  return rows
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

function inboxState() {
  return {
    stateNode: document.querySelector("[data-customer-pulse-detail-state]"),
    bodyNode: document.querySelector("[data-customer-pulse-detail-body]"),
  };
}

function setDetailState(kind, title, body) {
  const { stateNode, bodyNode } = inboxState();
  if (!stateNode || !bodyNode) return;
  bodyNode.hidden = true;
  stateNode.hidden = false;
  stateNode.className = "admin-state";
  if (kind === "loading") {
    stateNode.classList.add("admin-state--loading");
  } else if (kind === "error" || kind === "permission") {
    stateNode.classList.add("admin-state--error");
  } else if (kind === "inline") {
    stateNode.classList.add("admin-state--inline");
  } else {
    stateNode.classList.add("admin-state--empty");
  }
  stateNode.innerHTML = `<strong>${escapeHtml(title)}</strong><span>${escapeHtml(body)}</span>`;
}

function cardApiUrl(root, cardId, suffix) {
  return `${root.dataset.cardApiBase}/${cardId}${suffix}`;
}

function highlightSelectedCard(cardId) {
  document.querySelectorAll("[data-card-id]").forEach((node) => {
    node.classList.toggle("is-selected", String(node.dataset.cardId || "") === String(cardId || ""));
  });
}

function pulseFormFields(preview) {
  const actionType = String((preview && preview.action_type) || "");
  const payload = (preview && preview.preview) || {};
  if (actionType === "generate_reply_draft") {
    return `
      <label>
        <span>草稿内容</span>
        <textarea rows="7" data-preview-field="draft_message" placeholder="在这里继续编辑草稿">${escapeHtml(payload.draft_message || "")}</textarea>
        <small>${escapeHtml(payload.draft_notice || "所有外发消息默认只生成草稿，需人工确认后再发送。")}</small>
      </label>
    `;
  }
  if (actionType === "create_followup_task") {
    return `
      <label>
        <span>任务标题</span>
        <input type="text" data-preview-field="task_title" value="${escapeHtml(payload.task_title || "")}">
      </label>
      <label>
        <span>截止时间</span>
        <input type="datetime-local" data-preview-field="due_at" value="${escapeHtml(toDateTimeLocalValue(payload.due_at || ""))}">
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
        <select data-preview-field="followup_segment">
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
        <input type="text" data-preview-field="add_tag_ids" value="${escapeHtml((payload.add_tag_ids || []).join(","))}" placeholder="tag_a,tag_b">
      </label>
      <label>
        <span>移除标签 ID</span>
        <input type="text" data-preview-field="remove_tag_ids" value="${escapeHtml((payload.remove_tag_ids || []).join(","))}" placeholder="tag_c,tag_d">
      </label>
    `;
  }
  if (actionType === "set_followup_reminder") {
    return `
      <label>
        <span>提醒时间</span>
        <input type="datetime-local" data-preview-field="due_at" value="${escapeHtml(toDateTimeLocalValue(payload.due_at || ""))}">
      </label>
    `;
  }
  return "";
}

const pulseInboxStore = {
  payload: null,
  selectedCardId: null,
  detailPayloads: {},
  evidencePayloads: {},
  previewPayloads: {},
  evidenceErrors: {},
  previewErrors: {},
};

function cardById(cardId) {
  const cards = (pulseInboxStore.payload && pulseInboxStore.payload.cards) || [];
  return cards.find((item) => String(item.id) === String(cardId)) || null;
}

function upsertStoredCard(card) {
  if (!card || !pulseInboxStore.payload || !Array.isArray(pulseInboxStore.payload.cards)) return;
  const cards = pulseInboxStore.payload.cards;
  const index = cards.findIndex((item) => String(item.id) === String(card.id));
  if (index >= 0) {
    cards[index] = { ...cards[index], ...card };
  }
}

function ensureCardDetail(root, cardId) {
  const cached = pulseInboxStore.detailPayloads[String(cardId)];
  if (cached) {
    return Promise.resolve(cached);
  }
  return requestJson(cardApiUrl(root, cardId, ""), { method: "GET" }, root).then((payload) => {
    pulseInboxStore.detailPayloads[String(cardId)] = payload;
    if (payload && payload.card) {
      upsertStoredCard(payload.card);
    }
    return payload;
  });
}

function actionSlotHtml(root, card, preview, previewError) {
  const actionButtons = availableActionButtons(card);
  const feedbackButtons = Array.isArray(card.feedback_actions) ? card.feedback_actions : [];
  const actionButtonsHtml = actionButtons.length
    ? `
      <div class="admin-customer-pulse-card__actions">
        ${actionButtons
          .map(
            (item) => `
              <button
                type="button"
                class="admin-button ${item.action_type === (preview && preview.action_type) ? "admin-button--primary" : "admin-button--ghost"}"
                data-detail-action-preview
                data-card-id="${card.id}"
                data-action-type="${escapeHtml(item.action_type)}"
              >
                ${escapeHtml(item.action_label || "动作")}
              </button>
            `,
          )
          .join("")}
      </div>
    `
    : inlineStateHtml("当前角色只能查看", "该卡片已对当前角色隐藏所有可执行动作。");
  const feedbackButtonsHtml = feedbackButtons.length
    ? `
      <div class="admin-customer-pulse-card__actions">
        ${feedbackButtons
          .map(
            (item) => `
              <button
                type="button"
                class="admin-button admin-button--ghost"
                data-detail-feedback
                data-card-id="${card.id}"
                data-feedback-type="${escapeHtml(item.type || "")}"
              >
                ${escapeHtml(item.label || item.type || "反馈")}
              </button>
            `,
          )
          .join("")}
      </div>
    `
    : "";
  let editorHtml = "";
  if (preview && preview.action_type) {
    editorHtml = `
      <form class="admin-form-grid admin-form-grid--stacked" data-detail-action-form data-card-id="${card.id}" data-action-type="${escapeHtml(preview.action_type || "")}">
        <div class="admin-state admin-state--inline">
          <strong>${escapeHtml(preview.action_label || "动作预览")}</strong>
          <span>${escapeHtml(preview.action_title || preview.action_label || "请确认后执行")}</span>
        </div>
        ${
          preview.undo_notice
            ? `
              <div class="admin-state admin-state--inline">
                <strong>撤销窗口</strong>
                <span>${escapeHtml(preview.undo_notice)}</span>
              </div>
            `
            : ""
        }
        ${pulseFormFields(preview)}
        <div class="admin-customer-pulse-detail__form-actions">
          <button type="submit" class="admin-button admin-button--primary">确认并保存</button>
          <a class="admin-button admin-button--ghost" href="${escapeHtml(`${root.dataset.customerDetailBase}/${card.external_userid}`)}">打开客户详情</a>
        </div>
      </form>
    `;
  } else if (previewError) {
    editorHtml = inlineStateHtml("当前无法预览动作", previewError, "error");
  } else if (actionButtons.length) {
    editorHtml = inlineStateHtml("先预览再执行", "选择一个候选动作后，系统才会加载可编辑草稿或执行字段。");
  }
  return `
    <div>
      <div class="admin-customer-pulse-detail__section-title">候选动作</div>
      ${actionButtonsHtml}
    </div>
    ${editorHtml}
    ${
      feedbackButtonsHtml
        ? `
          <div>
            <div class="admin-customer-pulse-detail__section-title">反馈</div>
            ${feedbackButtonsHtml}
          </div>
        `
        : ""
    }
  `;
}

function evidenceSlotHtml(card, evidencePayload, evidenceError) {
  const permissions = (card && card.permissions) || {};
  const refs = Array.isArray(card.evidence_refs) ? card.evidence_refs : [];
  const canExpand = Boolean(permissions.evidence_view && card.evidence_expand_available);
  let extraHtml = "";
  if (canExpand) {
    if (evidencePayload && Array.isArray(evidencePayload.evidence) && evidencePayload.evidence.length) {
      extraHtml = `
        <div class="admin-customer-pulse-detail__section-title">原始证据</div>
        <div class="admin-profile-message-list">${evidenceItemsHtml(evidencePayload.evidence)}</div>
        ${
          Array.isArray(evidencePayload.inaccessible_refs) && evidencePayload.inaccessible_refs.length
            ? inlineStateHtml(
                "部分证据未展示",
                `有 ${evidencePayload.inaccessible_refs.length} 条 evidence refs 未通过原始边界校验。`,
              )
            : ""
        }
      `;
    } else if (evidenceError) {
      extraHtml = inlineStateHtml("当前无法展开原始证据", evidenceError, "error");
    } else if (refs.length) {
      extraHtml = `
        <div class="admin-toolbar">
          <button type="button" class="admin-button admin-button--ghost" data-detail-evidence-load data-card-id="${card.id}">
            查看原始证据
          </button>
        </div>
      `;
    }
  } else if (refs.length) {
    extraHtml = inlineStateHtml("当前角色无权展开原始证据", "可以看到 evidence refs，但不能直接读取原始记录内容。");
  }
  return `
    <div>
      <div class="admin-customer-pulse-detail__section-title">证据线索</div>
      <div class="admin-profile-message-list">${evidenceRefsHtml(refs)}</div>
    </div>
    ${extraHtml}
  `;
}

function renderDetail(root, card, detailPayload, preview, previewError, evidencePayload, evidenceError) {
  const { stateNode, bodyNode } = inboxState();
  if (!stateNode || !bodyNode || !card) return;
  bodyNode.innerHTML = `
    <div class="admin-customer-pulse-detail__body">
      <div class="admin-customer-pulse-detail__head">
        <div>
          <h2>${escapeHtml(card.customer_name || "未命名客户")}</h2>
          <p>${escapeHtml(card.title || "客户推进行动卡")}</p>
        </div>
        <div class="admin-toolbar">
          <span class="admin-inline-chip admin-inline-chip--neutral">${escapeHtml(card.card_status_label || "待处理")}</span>
          <span class="admin-inline-chip admin-inline-chip--${card.priority === "high" ? "warn" : "ok"}">${escapeHtml(card.priority_label || "常规")}</span>
        </div>
      </div>

      <div class="admin-state admin-state--inline">
        <strong>当前判断</strong>
        <span>${escapeHtml(card.current_judgement || card.summary || "暂无判断")}</span>
      </div>

      <dl class="admin-definition-list">
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
          <dd>${escapeHtml((card.latest_event && card.latest_event.title) || "最近事件")} · ${escapeHtml(
            (card.latest_event && card.latest_event.detail) || "暂无详情",
          )}</dd>
        </div>
        <div>
          <dt>为什么现在</dt>
          <dd>${escapeHtml((preview && preview.why_now) || card.why_now || "当前信号已达到行动阈值")}</dd>
        </div>
        <div>
          <dt>处理要求</dt>
          <dd>${escapeHtml(card.draft_notice || "所有外发消息默认只生成草稿，由人工确认。")}</dd>
        </div>
      </dl>

      <div class="admin-customer-pulse-flags">
        ${(card.risk_flags || [])
          .map((item) => `<span class="admin-inline-chip admin-inline-chip--warn">${escapeHtml(item.label || item.key || "风险")}</span>`)
          .join("")}
        ${(card.opportunity_flags || [])
          .map((item) => `<span class="admin-inline-chip admin-inline-chip--ok">${escapeHtml(item.label || item.key || "机会")}</span>`)
          .join("")}
      </div>

      ${evidenceSlotHtml(card, evidencePayload, evidenceError)}
      ${actionSlotHtml(root, card, preview, previewError)}

      <div class="admin-state admin-state--inline" data-detail-feedback hidden></div>
    </div>
  `;
  stateNode.hidden = true;
  bodyNode.hidden = false;
}

function renderSelectedCard(root, cardId) {
  const detailPayload = pulseInboxStore.detailPayloads[String(cardId)] || null;
  const previewPayload = pulseInboxStore.previewPayloads[String(cardId)] || null;
  const evidencePayload = pulseInboxStore.evidencePayloads[String(cardId)] || null;
  const card = (detailPayload && detailPayload.card) || cardById(cardId);
  if (!card) {
    setDetailState("empty", "当前没有可用卡片", "请先刷新行动卡。");
    return;
  }
  renderDetail(
    root,
    card,
    detailPayload,
    previewPayload,
    pulseInboxStore.previewErrors[String(cardId)] || "",
    evidencePayload,
    pulseInboxStore.evidenceErrors[String(cardId)] || "",
  );
}

function loadCardDetail(root, cardId) {
  pulseInboxStore.selectedCardId = String(cardId);
  highlightSelectedCard(cardId);
  setDetailState("loading", "正在加载行动卡详情", "系统正在读取当前判断、证据引用和可执行动作。");
  ensureCardDetail(root, cardId)
    .then(() => {
      renderSelectedCard(root, cardId);
    })
    .catch((error) => {
      if (isPermissionError(error)) {
        setDetailState("permission", "没有权限查看当前卡片", error.message || "请刷新页面后重试。");
        return;
      }
      setDetailState("error", "当前无法加载行动卡详情", error.message || "请稍后重试。");
    });
}

function loadPreview(root, cardId, actionType, options = {}) {
  pulseInboxStore.selectedCardId = String(cardId);
  highlightSelectedCard(cardId);
  pulseInboxStore.previewErrors[String(cardId)] = "";
  pulseInboxStore.previewPayloads[String(cardId)] = null;
  ensureCardDetail(root, cardId)
    .then((detailPayload) => {
      const card = (detailPayload && detailPayload.card) || cardById(cardId);
      if (!card) {
        setDetailState("empty", "当前没有可用卡片", "请先刷新行动卡。");
        return null;
      }
      renderSelectedCard(root, cardId);
      return requestJson(
        cardApiUrl(root, cardId, "/actions/preview"),
        {
          method: "POST",
          body: JSON.stringify({
            action_type: actionType || card.suggested_action_type,
            track_click: Boolean(options.trackClick),
            metric_source: options.metricSource || "customer_pulse_inbox",
          }),
        },
        root,
      );
    })
    .then((payload) => {
      if (!payload) return;
      pulseInboxStore.previewPayloads[String(cardId)] = payload.preview || {};
      renderSelectedCard(root, cardId);
    })
    .catch((error) => {
      pulseInboxStore.previewErrors[String(cardId)] = error.message || "当前无法加载动作预览。";
      renderSelectedCard(root, cardId);
    });
}

function loadEvidence(root, cardId) {
  pulseInboxStore.selectedCardId = String(cardId);
  highlightSelectedCard(cardId);
  pulseInboxStore.evidenceErrors[String(cardId)] = "";
  pulseInboxStore.evidencePayloads[String(cardId)] = null;
  ensureCardDetail(root, cardId)
    .then(() =>
      requestJson(cardApiUrl(root, cardId, "/evidence"), { method: "GET" }, root).then((payload) => {
        pulseInboxStore.evidencePayloads[String(cardId)] = payload;
        renderSelectedCard(root, cardId);
      }),
    )
    .catch((error) => {
      pulseInboxStore.evidenceErrors[String(cardId)] = error.message || "当前无法加载原始证据。";
      renderSelectedCard(root, cardId);
    });
}

function feedbackNode() {
  return document.querySelector("[data-detail-feedback]");
}

function setFeedback(message, tone) {
  const node = feedbackNode();
  if (!node) return;
  node.hidden = false;
  node.className = `admin-state admin-state--inline${tone === "error" ? " admin-state--error" : ""}`;
  node.innerHTML = `<strong>${tone === "error" ? "处理失败" : "操作结果"}</strong><span>${escapeHtml(message)}</span>`;
}

function currentFormPayload(form) {
  const actionType = String(form.dataset.actionType || "");
  if (actionType === "generate_reply_draft") {
    return { draft_message: form.querySelector("[data-preview-field='draft_message']")?.value || "" };
  }
  if (actionType === "create_followup_task") {
    return {
      task_title: form.querySelector("[data-preview-field='task_title']")?.value || "",
      due_at: (form.querySelector("[data-preview-field='due_at']")?.value || "").replace("T", " "),
    };
  }
  if (actionType === "update_followup_segment") {
    return { followup_segment: form.querySelector("[data-preview-field='followup_segment']")?.value || "" };
  }
  if (actionType === "update_tags") {
    const addTagIds = (form.querySelector("[data-preview-field='add_tag_ids']")?.value || "")
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean);
    const removeTagIds = (form.querySelector("[data-preview-field='remove_tag_ids']")?.value || "")
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean);
    return { add_tag_ids: addTagIds, remove_tag_ids: removeTagIds };
  }
  if (actionType === "set_followup_reminder") {
    return { due_at: (form.querySelector("[data-preview-field='due_at']")?.value || "").replace("T", " ") };
  }
  return {};
}

function submitAction(root, form) {
  const cardId = form.dataset.cardId;
  const actionType = form.dataset.actionType;
  const payload = {
    admin_action_token: root.dataset.adminActionToken,
    action_type: actionType,
    ...currentFormPayload(form),
  };
  requestJson(
    cardApiUrl(root, cardId, "/actions/execute"),
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
    root,
  )
    .then((responsePayload) => {
      const execution = (responsePayload && responsePayload.execution) || {};
      const message =
        execution.undo_available && execution.undo_until
          ? `操作已保存，可在 ${execution.undo_until} 前撤销。正在刷新收件箱。`
          : "操作已保存，正在刷新收件箱。";
      setFeedback(message, "success");
      window.setTimeout(() => window.location.reload(), 320);
    })
    .catch((error) => {
      if (isPermissionError(error)) {
        setFeedback(error.message || "后台动作令牌无效，请刷新页面后重试。", "error");
        return;
      }
      setFeedback(error.message || "当前无法执行行动卡。", "error");
    });
}

function submitFeedback(root, cardId, feedbackType, feedbackSource) {
  requestJson(
    cardApiUrl(root, cardId, "/feedback"),
    {
      method: "POST",
      body: JSON.stringify({
        admin_action_token: root.dataset.adminActionToken,
        feedback_type: feedbackType,
        feedback_source: feedbackSource || "customer_pulse_inbox",
      }),
    },
    root,
  )
    .then(() => {
      setFeedback("反馈已记录，正在刷新收件箱。", "success");
      window.setTimeout(() => window.location.reload(), 320);
    })
    .catch((error) => {
      if (isPermissionError(error)) {
        setFeedback(error.message || "后台动作令牌无效，请刷新页面后重试。", "error");
        return;
      }
      setFeedback(error.message || "当前无法记录反馈。", "error");
    });
}

function wireInboxInteractions(root) {
  document.addEventListener("click", (event) => {
    const selectButton = event.target.closest("[data-card-select]");
    if (selectButton) {
      loadCardDetail(root, selectButton.dataset.cardId);
      return;
    }
    const actionButton = event.target.closest("[data-card-action-preview],[data-detail-action-preview]");
    if (actionButton) {
      loadPreview(root, actionButton.dataset.cardId, actionButton.dataset.actionType, {
        trackClick: true,
        metricSource: actionButton.hasAttribute("data-detail-action-preview")
          ? "customer_pulse_inbox_detail_action"
          : "customer_pulse_inbox_card_action",
      });
      return;
    }
    const evidenceButton = event.target.closest("[data-detail-evidence-load]");
    if (evidenceButton) {
      loadEvidence(root, evidenceButton.dataset.cardId);
      return;
    }
    const feedbackButton = event.target.closest("[data-card-feedback],[data-detail-feedback]");
    if (feedbackButton) {
      submitFeedback(
        root,
        feedbackButton.dataset.cardId,
        feedbackButton.dataset.feedbackType,
        feedbackButton.hasAttribute("data-detail-feedback") ? "customer_pulse_inbox_detail_feedback" : "customer_pulse_inbox_card_feedback",
      );
    }
  });
  document.addEventListener("submit", (event) => {
    const form = event.target.closest("[data-detail-action-form]");
    if (!form) return;
    event.preventDefault();
    submitAction(root, form);
  });
}

document.addEventListener("DOMContentLoaded", () => {
  const root = pulseInboxRoot();
  if (!root) return;
  const rawPayload = root.querySelector("[data-customer-pulse-inbox-json]");
  pulseInboxStore.payload = safeJsonParse(rawPayload ? rawPayload.textContent : "") || { cards: [] };
  wireInboxInteractions(root);
  const firstCard = ((pulseInboxStore.payload && pulseInboxStore.payload.cards) || [])[0];
  if (!firstCard) {
    setDetailState("empty", "当前没有待处理行动卡", "可以先刷新行动卡，或调整筛选条件。");
    return;
  }
  loadCardDetail(root, firstCard.id);
});
