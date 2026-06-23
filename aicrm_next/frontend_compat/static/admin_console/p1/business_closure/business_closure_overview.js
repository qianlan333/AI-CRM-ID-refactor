import { canRenderGlobalPass, scenarioNeedsOperatorAction, statusMeta } from "./status_model.js";
function text(value) {
    return String(value ?? "");
}
function escapeHtml(value) {
    return text(value)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;");
}
function scenarioCard(scenario) {
    const meta = statusMeta(scenario.status);
    const actionRequired = scenarioNeedsOperatorAction(scenario);
    const actionText = actionRequired ? "需要继续跟踪" : "当前无需运营动作";
    return `
    <article class="p1-closure-card p1-closure-card--${meta.tone}" data-scenario="${escapeHtml(scenario.key)}" data-status="${escapeHtml(scenario.status)}">
      <div class="p1-closure-card__head">
        <h2>${escapeHtml(scenario.title)}</h2>
        <span class="p1-closure-pill p1-closure-pill--${meta.tone}">${escapeHtml(meta.label)}</span>
      </div>
      <dl class="p1-closure-fields">
        <div><dt>Evidence</dt><dd>${escapeHtml(scenario.evidenceStatus)}</dd></div>
        <div><dt>Derived</dt><dd>${escapeHtml(scenario.derivedStatus)}</dd></div>
        <div><dt>Operator</dt><dd>${escapeHtml(actionText)}</dd></div>
      </dl>
      <p>${escapeHtml(scenario.summary)}</p>
      <p class="p1-closure-guardrail">${escapeHtml(scenario.guardrail)}</p>
    </article>
  `;
}
function renderBusinessClosure(root, payload) {
    const globalPass = canRenderGlobalPass(payload);
    root.innerHTML = `
    <section class="p1-closure-banner" data-final-verdict="${escapeHtml(payload.finalVerdict)}" data-can-claim-pass90="${globalPass ? "true" : "false"}">
      <div>
        <h2>P1 readiness</h2>
        <p>当前结论为 ${escapeHtml(payload.finalVerdict)}，不是 PASS_90_PLUS。</p>
      </div>
      <span class="p1-closure-pill p1-closure-pill--warning">P1_READY_WITH_EXCEPTIONS</span>
    </section>
    <section class="p1-closure-grid" aria-label="Business closure scenario status">
      ${payload.scenarios.map(scenarioCard).join("")}
    </section>
  `;
}
function parsePayload() {
    const payloadNode = document.getElementById("businessClosurePayload");
    if (!payloadNode?.textContent)
        return null;
    return JSON.parse(payloadNode.textContent);
}
function boot() {
    const root = document.getElementById("businessClosureApp");
    const payload = parsePayload();
    if (!root || !payload)
        return;
    renderBusinessClosure(root, payload);
}
if (typeof document !== "undefined") {
    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", boot, { once: true });
    }
    else {
        boot();
    }
}
export { renderBusinessClosure };
