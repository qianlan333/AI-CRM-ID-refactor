function customerProfileRoot() {
  return document.querySelector("[data-customer-profile-root]");
}

function safeJsonParse(text) {
  try {
    return JSON.parse(text);
  } catch (_error) {
    return null;
  }
}

function requestJson(url, options = {}) {
  const finalOptions = {
    headers: {
      Accept: "application/json",
      ...(options.body ? { "Content-Type": "application/json" } : {}),
      ...(options.headers || {}),
    },
    ...options,
  };
  return fetch(url, finalOptions)
    .then((response) =>
      response.text().then((text) => ({
        response,
        payload: text ? safeJsonParse(text) : null,
      })),
    )
    .then(({ response, payload }) => {
      if (!response.ok) {
        throw new Error((payload && payload.error) || "request failed");
      }
      if (payload && payload.ok === false) {
        throw new Error(payload.error || "request failed");
      }
      return payload || { ok: true };
    });
}

function showSectionError(stateNode, message) {
  if (!stateNode) return;
  stateNode.hidden = false;
  stateNode.classList.remove("admin-state--loading");
  stateNode.classList.add("admin-state--error");
  stateNode.innerHTML = ["<strong>当前无法加载</strong>", `<span>${message}</span>`].join("");
}

function showSectionEmpty(stateNode, title, body) {
  if (!stateNode) return;
  stateNode.hidden = false;
  stateNode.classList.remove("admin-state--loading", "admin-state--error");
  stateNode.innerHTML = [`<strong>${title}</strong>`, `<span>${body}</span>`].join("");
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
            <span>${item.send_time || "未知时间"}</span>
            <span>${item.speaker || "未知发送方"}</span>
          </div>
          <div class="admin-profile-message-content">${item.content || "无内容"}</div>
        </article>
      `,
    )
    .join("");
  stateNode.hidden = true;
  listNode.hidden = false;
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
    body: JSON.stringify(payload),
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

document.addEventListener("DOMContentLoaded", () => {
  const root = customerProfileRoot();
  if (!root) return;
  loadLiveTags(root);
  loadQuestionnaireAnswers(root);
  loadMessages(root, false);
  loadAutomationMember(root);
  wireFetchAllButton(root);
  wireAutomationActions(root);
  scrollToInitialSection(root);
});
