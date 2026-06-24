import {
  type BusinessClosurePayload,
  canRenderGlobalPass
} from "../shared/status_model.js";
import { escapeHtml } from "../shared/dom.js";
import { renderStatusCard } from "../shared/status_card.js";
import { renderInteractionShell } from "../shared/interaction_shell.js";

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
    ${renderInteractionShell(payload)}
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
