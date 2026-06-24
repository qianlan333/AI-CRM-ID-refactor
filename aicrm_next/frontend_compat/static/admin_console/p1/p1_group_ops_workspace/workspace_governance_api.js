import { DEFAULT_WORKSPACE_DRAFT_API_CONFIG, assertWorkspaceSensitiveSafe, defaultWorkspaceDraftRequestJson, workspaceSimpleHash } from "./workspace_draft_api.js";
export const DEFAULT_WORKSPACE_GOVERNANCE_API_CONFIG = {
    ...DEFAULT_WORKSPACE_DRAFT_API_CONFIG,
    governanceUrl: "/api/admin/p1/group-ops-workspace/governance"
};
function text(value) {
    return String(value ?? "").trim();
}
function bodyOptions(payload) {
    return {
        method: "POST",
        body: JSON.stringify(payload)
    };
}
function defaultGrayWindow(snapshotHash) {
    const dayOffset = Number.parseInt(workspaceSimpleHash(snapshotHash || "no_snapshot").slice(0, 2), 16) % 20;
    const day = String(1 + dayOffset).padStart(2, "0");
    return {
        start_at: `2026-06-${day}T09:00:00+08:00`,
        end_at: `2026-06-${day}T10:00:00+08:00`,
        timezone: "Asia/Shanghai"
    };
}
function stableGrayWindowHash(grayWindow) {
    return workspaceSimpleHash(JSON.stringify({
        start_at: grayWindow.start_at,
        end_at: grayWindow.end_at,
        timezone: grayWindow.timezone
    }));
}
export function stableGovernanceIdempotencyKey(draftId, snapshotHash, allowlistHash, grayWindowHash) {
    return [
        "p1-gow-governance",
        text(draftId),
        text(snapshotHash || "no_snapshot"),
        text(allowlistHash || "allowlist_missing"),
        text(grayWindowHash || "window_missing")
    ].join(":");
}
export function assertWorkspaceGovernancePayloadSafe(payload) {
    assertWorkspaceSensitiveSafe(payload);
    const start = Date.parse(payload.gray_window.start_at);
    const end = Date.parse(payload.gray_window.end_at);
    if (!Number.isFinite(start) || !Number.isFinite(end) || end <= start) {
        throw new Error("governance_payload_invalid_gray_window");
    }
    if (!payload.idempotency_key || !payload.client_snapshot_hash || !payload.allowlist_summary.allowlist_hash) {
        throw new Error("governance_payload_missing_required_field");
    }
    return true;
}
export function buildWorkspaceGovernanceRequestPayload(draftId, snapshotHash, options = {}) {
    const grayWindow = options.grayWindow || defaultGrayWindow(snapshotHash);
    const allowlistHash = options.allowlistHash || `allowlist-${workspaceSimpleHash(`${draftId}:${snapshotHash}:summary`)}`;
    const grayWindowHash = stableGrayWindowHash(grayWindow);
    const payload = {
        idempotency_key: stableGovernanceIdempotencyKey(draftId, snapshotHash, allowlistHash, grayWindowHash),
        client_snapshot_hash: snapshotHash,
        allowlist_summary: {
            allowlist_hash: allowlistHash,
            allowlist_count: options.allowlistCount ?? 0,
            source_reference: options.sourceReference || {
                reference_type: "p1_workspace_governance",
                reference_id: `draft-${text(draftId) || "not_saved"}`,
                summary_only: true
            }
        },
        gray_window: grayWindow
    };
    if (options.requestNote) {
        payload.request_note = options.requestNote;
    }
    assertWorkspaceGovernancePayloadSafe(payload);
    return payload;
}
export function assertGovernanceResponseSafe(value) {
    assertWorkspaceSensitiveSafe(value);
    const payload = value;
    if (payload.approved === true
        || payload.push_center_job_created === true
        || payload.external_effect_job_created === true
        || payload.broadcast_job_created === true
        || payload.internal_event_created === true
        || payload.real_external_call === true
        || payload.real_external_call_executed === true
        || payload.can_claim_pass_90_plus === true) {
        throw new Error("governance_api_response_violates_execution_guardrail");
    }
    if (payload.execution_status && payload.execution_status !== "not_execution"
        || payload.review_status === "sent"
        || payload.review_status === "completed"
        || payload.review_status === "approved") {
        throw new Error("governance_api_response_claims_execution_state");
    }
    const list = value;
    if (Array.isArray(list.items)) {
        list.items.forEach((item) => assertGovernanceResponseSafe(item));
    }
    return true;
}
function asGovernanceResponse(value) {
    const payload = value && typeof value === "object" ? value : { ok: false };
    assertGovernanceResponseSafe(payload);
    return payload;
}
function asGovernanceListResponse(value) {
    const payload = value && typeof value === "object" ? value : { ok: false, items: [] };
    if (!Array.isArray(payload.items)) {
        payload.items = [];
    }
    assertGovernanceResponseSafe(payload);
    return payload;
}
export function isGovernanceConflictError(error) {
    const message = text(error instanceof Error ? error.message : error).toLowerCase();
    return message.includes("conflict") || message.includes("409") || message.includes("active governance review exists");
}
export async function requestGovernance(draftId, payload, config = DEFAULT_WORKSPACE_GOVERNANCE_API_CONFIG, requestJson = defaultWorkspaceDraftRequestJson()) {
    assertWorkspaceGovernancePayloadSafe(payload);
    return asGovernanceResponse(await requestJson(`${config.draftsUrl}/${encodeURIComponent(draftId)}/governance/request`, bodyOptions(payload)));
}
export async function getGovernanceReview(reviewId, config = DEFAULT_WORKSPACE_GOVERNANCE_API_CONFIG, requestJson = defaultWorkspaceDraftRequestJson()) {
    return asGovernanceResponse(await requestJson(`${config.governanceUrl}/${encodeURIComponent(reviewId)}`));
}
export async function getDraftGovernance(draftId, config = DEFAULT_WORKSPACE_GOVERNANCE_API_CONFIG, requestJson = defaultWorkspaceDraftRequestJson()) {
    return asGovernanceListResponse(await requestJson(`${config.draftsUrl}/${encodeURIComponent(draftId)}/governance`));
}
