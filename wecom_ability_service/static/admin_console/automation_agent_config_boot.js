(function () {
  "use strict";

  const AutomationAgentConfig = window.AutomationAgentConfig || {};
  window.AutomationAgentConfig = AutomationAgentConfig;

  const PROMPT_FIELD_NAMES = ["role_prompt", "task_prompt"];

  function promptFields() {
    const fields = AutomationAgentConfig.agentFields ? AutomationAgentConfig.agentFields() : {};
    return PROMPT_FIELD_NAMES.map((name) => (name === "role_prompt" ? fields.rolePrompt : fields.taskPrompt)).filter(Boolean);
  }

  function rememberFocusedPromptField() {
    promptFields().forEach((field) => {
      field.addEventListener("focus", function () {
        AutomationAgentConfig.state.focusedPromptField = field;
      });
    });
  }

  function insertPromptPlaceholder(placeholder) {
    const value = String(placeholder || "").trim();
    if (!value) return;
    const fields = AutomationAgentConfig.agentFields();
    const activeElement = document.activeElement;
    const target = activeElement === fields.rolePrompt || activeElement === fields.taskPrompt
      ? activeElement
      : (AutomationAgentConfig.state.focusedPromptField || fields.taskPrompt);
    if (!target) return;
    const start = Number(target.selectionStart || 0);
    const end = Number(target.selectionEnd || start);
    const before = String(target.value || "").slice(0, start);
    const after = String(target.value || "").slice(end);
    target.value = before + value + after;
    const nextCursor = start + value.length;
    target.focus();
    target.setSelectionRange(nextCursor, nextCursor);
    AutomationAgentConfig.state.focusedPromptField = target;
  }

  function bindPlaceholderInsertion() {
    const { agentFormPanel } = AutomationAgentConfig.elements();
    rememberFocusedPromptField();
    if (!agentFormPanel) return;
    agentFormPanel.addEventListener("click", function (event) {
      const button = event.target.closest("[data-agent-placeholder]");
      if (!button) return;
      insertPromptPlaceholder(button.getAttribute("data-agent-placeholder"));
    });
  }

  function boot() {
    const root = AutomationAgentConfig.root ? AutomationAgentConfig.root() : null;
    if (!root) return;
    AutomationAgentConfig.syncInitialState();
    AutomationAgentConfig.renderAgentTable();
    if (typeof AutomationAgentConfig.initializeTemplates === "function") {
      AutomationAgentConfig.initializeTemplates(root);
    }
    AutomationAgentConfig.updateSummaryCounters();
    AutomationAgentConfig.bindAgentInteractions(root);
    if (typeof AutomationAgentConfig.bindTemplateInteractions === "function") {
      AutomationAgentConfig.bindTemplateInteractions(root);
    }
    if (typeof AutomationAgentConfig.bindTagPickerInteractions === "function") {
      AutomationAgentConfig.bindTagPickerInteractions(root);
    }
    bindPlaceholderInsertion(root);
    AutomationAgentConfig.loadAgents(root).catch((error) => {
      AutomationAgentConfig.showFeedback(error.message || "加载模型与智能体配置失败", "error");
    });
    if (typeof AutomationAgentConfig.refreshTemplates === "function") {
      AutomationAgentConfig.refreshTemplates(root).catch((error) => {
        AutomationAgentConfig.showFeedback(error.message || "加载模型与智能体配置失败", "error");
      });
    }
  }

  AutomationAgentConfig.insertPromptPlaceholder = insertPromptPlaceholder;
  AutomationAgentConfig.bindPlaceholderInsertion = bindPlaceholderInsertion;
  AutomationAgentConfig.boot = boot;
})();
