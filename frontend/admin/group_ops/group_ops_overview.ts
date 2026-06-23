import { escapeHtml } from "../shared/dom.js";
import { renderStatusCard } from "../shared/status_card.js";
import {
  type GroupOpsStatusInput,
  GROUP_OPS_P1_DEFAULT_INPUTS,
  buildGroupOpsStatusViewModel
} from "./group_ops_status.js";

export interface GroupOpsOverviewPayload {
  cards: GroupOpsStatusInput[];
  evidenceSummary: {
    effectJobId: string;
    pushCenterStatus: string;
    realExternalCallEvidence: string;
    retryable: boolean;
    operatorActionRequired: boolean;
    finalStatus: string;
  };
}

const DEFAULT_EVIDENCE_SUMMARY = {
  effectJobId: "external_effect_job:97",
  pushCenterStatus: "sent",
  realExternalCallEvidence: "collected_in_prior_report",
  retryable: false,
  operatorActionRequired: false,
  finalStatus: "EVIDENCE_COLLECTED"
};

function parsePayload(): GroupOpsOverviewPayload {
  const payloadNode = document.getElementById("groupOpsP1StatusPayload");
  if (!payloadNode?.textContent) {
    return { cards: GROUP_OPS_P1_DEFAULT_INPUTS, evidenceSummary: DEFAULT_EVIDENCE_SUMMARY };
  }
  const parsed = JSON.parse(payloadNode.textContent) as Partial<GroupOpsOverviewPayload>;
  return {
    cards: parsed.cards?.length ? parsed.cards : GROUP_OPS_P1_DEFAULT_INPUTS,
    evidenceSummary: { ...DEFAULT_EVIDENCE_SUMMARY, ...(parsed.evidenceSummary || {}) }
  };
}

function renderEvidenceSummary(summary: GroupOpsOverviewPayload["evidenceSummary"]): string {
  return `
    <section class="p1-group-ops-evidence" aria-label="Group Ops send evidence summary" data-final-status="${escapeHtml(summary.finalStatus)}">
      <div class="p1-group-ops-evidence__head">
        <h2>发送证据摘要</h2>
        <p>发送链路已取证，但治理记录仍需独立 attach。</p>
      </div>
      <dl class="p1-group-ops-evidence__grid">
        <div><dt>Effect job</dt><dd>${escapeHtml(summary.effectJobId)}</dd></div>
        <div><dt>Push Center</dt><dd>${escapeHtml(summary.pushCenterStatus)}</dd></div>
        <div><dt>Real call evidence</dt><dd>${escapeHtml(summary.realExternalCallEvidence)}</dd></div>
        <div><dt>Retryable</dt><dd>${summary.retryable ? "true" : "false"}</dd></div>
        <div><dt>Operator action</dt><dd>${summary.operatorActionRequired ? "true" : "false"}</dd></div>
        <div><dt>Final status</dt><dd>${escapeHtml(summary.finalStatus)}</dd></div>
      </dl>
    </section>
  `;
}

function renderReadonlyInteractionShell(cards: GroupOpsStatusInput[]): string {
  const rows = cards.map((card) => {
    const viewModel = buildGroupOpsStatusViewModel(card);
    const guardrails = viewModel.guardrails.map((guardrail) => `<code>${escapeHtml(guardrail)}</code>`).join(" ");
    return `
      <article class="p1-group-ops-interaction-card" data-group-ops-evidence="${escapeHtml(viewModel.evidenceId)}" data-execution-mode="${escapeHtml(viewModel.executionMode)}" data-drop-intent="${escapeHtml(viewModel.blockedNoop.intent)}" data-drop-allowed="${viewModel.blockedNoop.allowed ? "true" : "false"}" data-status-after-drop="${escapeHtml(viewModel.blockedNoop.statusAfterDrop)}">
        <div class="p1-group-ops-interaction-card__head">
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
    <section class="p1-group-ops-interaction-shell" aria-label="Group Ops read-only interaction shell">
      <div class="p1-group-ops-shell-head">
        <h2>只读交互契约</h2>
        <p>Drag handle 只是视觉占位；blocked_noop 不会改状态，也不会触发真实发送、审批、名单或灰度窗口配置。</p>
      </div>
      <div class="p1-group-ops-interaction-grid">${rows}</div>
    </section>
  `;
}

export function renderGroupOpsOverview(root: HTMLElement, payload: GroupOpsOverviewPayload): void {
  const cards = payload.cards.length ? payload.cards : GROUP_OPS_P1_DEFAULT_INPUTS;
  const cardHtml = cards.map((card) => {
    const viewModel = buildGroupOpsStatusViewModel(card);
    return renderStatusCard(viewModel.scenario, {
      dragHandle: true,
      dragDisabledReason: `${viewModel.operatorPrompt} Readonly preview only; no direct send.`
    });
  }).join("");
  root.innerHTML = `
    <section class="p1-group-ops-banner" data-group-ops-slice="readonly" data-real-external-call-executed="false" data-production-write-executed="false">
      <div>
        <h2>P1 Group Ops status slice</h2>
        <p>只读展示发送 evidence 与 governance residual risk；不新增发送、审批、名单或灰度窗口配置能力。</p>
      </div>
      <span class="p1-closure-pill p1-closure-pill--warning">EVIDENCE_COLLECTED</span>
    </section>
    ${renderEvidenceSummary(payload.evidenceSummary)}
    <section class="p1-closure-grid" aria-label="Group Ops P1 status cards">
      ${cardHtml}
    </section>
    ${renderReadonlyInteractionShell(cards)}
  `;
}

function boot(): void {
  const root = document.getElementById("groupOpsP1StatusApp");
  if (!root) return;
  renderGroupOpsOverview(root, parsePayload());
}

if (typeof document !== "undefined") {
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot, { once: true });
  } else {
    boot();
  }
}
