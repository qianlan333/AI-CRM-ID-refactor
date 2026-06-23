import { escapeHtml } from "../shared/dom.js";
import { renderStatusCard } from "../shared/status_card.js";
import {
  type PushCenterStatusInput,
  PUSH_CENTER_P1_DEFAULT_INPUTS,
  buildPushCenterStatusViewModel
} from "./push_center_status.js";

export interface PushCenterOverviewPayload {
  cards: PushCenterStatusInput[];
}

function parsePayload(): PushCenterOverviewPayload {
  const payloadNode = document.getElementById("pushCenterP1StatusPayload");
  if (!payloadNode?.textContent) return { cards: PUSH_CENTER_P1_DEFAULT_INPUTS };
  const parsed = JSON.parse(payloadNode.textContent) as Partial<PushCenterOverviewPayload>;
  return {
    cards: parsed.cards?.length ? parsed.cards : PUSH_CENTER_P1_DEFAULT_INPUTS
  };
}

function renderReadonlyInteractionShell(inputs: PushCenterStatusInput[]): string {
  const rows = inputs.map((input) => {
    const viewModel = buildPushCenterStatusViewModel(input);
    const guardrails = viewModel.guardrails.map((guardrail) => `<code>${escapeHtml(guardrail)}</code>`).join(" ");
    return `
      <article class="p1-push-interaction-card" data-push-center-card="${escapeHtml(viewModel.scenario.key)}" data-execution-mode="${escapeHtml(viewModel.executionMode)}" data-drop-intent="${escapeHtml(viewModel.blockedNoop.intent)}" data-drop-allowed="${viewModel.blockedNoop.allowed ? "true" : "false"}" data-status-after-drop="${escapeHtml(viewModel.blockedNoop.statusAfterDrop)}">
        <div class="p1-push-interaction-card__head">
          <span class="p1-drag-handle" aria-hidden="true">⋮⋮</span>
          <strong>${escapeHtml(viewModel.scenario.title)}</strong>
        </div>
        <dl class="p1-closure-fields">
          <div><dt>Execution</dt><dd>${escapeHtml(viewModel.executionMode)}</dd></div>
          <div><dt>Drop</dt><dd>${escapeHtml(viewModel.blockedNoop.intent)}</dd></div>
          <div><dt>After</dt><dd>${escapeHtml(viewModel.blockedNoop.statusAfterDrop)}</dd></div>
        </dl>
        <p>${escapeHtml(viewModel.operatorPrompt)}</p>
        <p class="p1-drag-guardrails">${guardrails}</p>
      </article>
    `;
  }).join("");
  return `
    <section class="p1-push-interaction-shell" aria-label="Push Center read-only interaction shell">
      <div class="p1-push-shell-head">
        <h2>只读交互契约</h2>
        <p>Drag handle 只是视觉占位；blocked_noop 不改变状态，也不会触发 external effect 或生产写入。</p>
      </div>
      <div class="p1-push-interaction-grid">${rows}</div>
    </section>
  `;
}

export function renderPushCenterOverview(root: HTMLElement, payload: PushCenterOverviewPayload): void {
  const cards = payload.cards.length ? payload.cards : PUSH_CENTER_P1_DEFAULT_INPUTS;
  const cardHtml = cards.map((input) => {
    const viewModel = buildPushCenterStatusViewModel(input);
    return renderStatusCard(viewModel.scenario, {
      dragHandle: true,
      dragDisabledReason: `${viewModel.operatorPrompt} Readonly preview only; no direct send.`
    });
  }).join("");
  root.innerHTML = `
    <section class="p1-push-banner" data-push-center-slice="readonly" data-real-external-call-executed="false" data-production-write-executed="false">
      <div>
        <h2>P1 Push Center status slice</h2>
        <p>只读呈现 Business Closure exception 状态；不新增写操作、不绕过 Push Center、不触发真实外呼。</p>
      </div>
      <span class="p1-closure-pill p1-closure-pill--warning">P1_READY_WITH_EXCEPTIONS</span>
    </section>
    <section class="p1-closure-grid" aria-label="Push Center P1 status cards">
      ${cardHtml}
    </section>
    ${renderReadonlyInteractionShell(cards)}
  `;
}

function boot(): void {
  const root = document.getElementById("pushCenterP1StatusApp");
  if (!root) return;
  renderPushCenterOverview(root, parsePayload());
}

if (typeof document !== "undefined") {
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot, { once: true });
  } else {
    boot();
  }
}
