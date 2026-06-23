import {
  type BusinessClosurePayload,
  canRenderGlobalPass
} from "../shared/status_model.js";
import { escapeHtml } from "../shared/dom.js";
import { renderStatusCard } from "../shared/status_card.js";
import { dragPreviewForScenario, validateDropIntent } from "../shared/interaction_contract.js";

function readonlyInteractionDemo(payload: BusinessClosurePayload): string {
  const rows = payload.scenarios.map((scenario) => {
    const preview = dragPreviewForScenario(scenario);
    const blockedDrop = validateDropIntent(scenario, "blocked_noop");
    const guardrails = preview.guardrails.map((guardrail) => `<code>${escapeHtml(guardrail)}</code>`).join(" ");
    return `
      <article class="p1-drag-demo-card" data-drag-entity="${escapeHtml(preview.entity)}" data-execution-mode="${escapeHtml(preview.executionMode)}" data-drop-intent="${escapeHtml(blockedDrop.intent)}" data-drop-allowed="${blockedDrop.allowed ? "true" : "false"}">
        <div class="p1-drag-demo-card__head">
          <span class="p1-drag-handle" aria-hidden="true">⋮⋮</span>
          <strong>${escapeHtml(preview.label)}</strong>
        </div>
        <dl class="p1-closure-fields">
          <div><dt>Execution</dt><dd>${escapeHtml(preview.executionMode)}</dd></div>
          <div><dt>Drop</dt><dd>${escapeHtml(blockedDrop.intent)}</dd></div>
          <div><dt>Status after drop</dt><dd>${escapeHtml(blockedDrop.statusAfterDrop)}</dd></div>
        </dl>
        <p>${escapeHtml(blockedDrop.reason)}</p>
        <p class="p1-drag-guardrails">${guardrails}</p>
      </article>
    `;
  }).join("");
  return `
    <section class="p1-drag-demo" aria-label="Read-only drag-ready interaction contract">
      <div class="p1-drag-demo__head">
        <h2>Drag-ready interaction contract</h2>
        <p>只读交互占位：blocked_noop 不会改变 evidence status，也不会触发 external effect。</p>
      </div>
      <div class="p1-drag-demo__grid">${rows}</div>
    </section>
  `;
}

function renderBusinessClosure(root: HTMLElement, payload: BusinessClosurePayload): void {
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
      ${payload.scenarios.map((scenario) => renderStatusCard(scenario, {
        dragHandle: true,
        dragDisabledReason: "Readonly preview only: drag-ready visual contract is not wired to execution."
      })).join("")}
    </section>
    ${readonlyInteractionDemo(payload)}
  `;
}

function parsePayload(): BusinessClosurePayload | null {
  const payloadNode = document.getElementById("businessClosurePayload");
  if (!payloadNode?.textContent) return null;
  return JSON.parse(payloadNode.textContent) as BusinessClosurePayload;
}

function boot(): void {
  const root = document.getElementById("businessClosureApp");
  const payload = parsePayload();
  if (!root || !payload) return;
  renderBusinessClosure(root, payload);
}

if (typeof document !== "undefined") {
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot, { once: true });
  } else {
    boot();
  }
}

export { renderBusinessClosure };
