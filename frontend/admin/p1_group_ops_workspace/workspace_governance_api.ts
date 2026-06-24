import {
  DEFAULT_WORKSPACE_DRAFT_API_CONFIG,
  assertWorkspaceSensitiveSafe,
  defaultWorkspaceDraftRequestJson,
  workspaceSimpleHash,
  type WorkspaceDraftApiConfig,
  type WorkspaceDraftRequestJson,
  type WorkspaceDraftRequestOptions
} from "./workspace_draft_api.js";

export interface WorkspaceGovernanceApiConfig extends WorkspaceDraftApiConfig {
  governanceUrl: string;
}

export interface WorkspaceGovernanceAllowlistSummary {
  allowlist_hash: string;
  allowlist_count: number;
  source_reference: Record<string, unknown>;
}

export interface WorkspaceGovernanceGrayWindow {
  start_at: string;
  end_at: string;
  timezone: string;
}

export interface WorkspaceGovernanceRequestPayload {
  idempotency_key: string;
  client_snapshot_hash: string;
  allowlist_summary: WorkspaceGovernanceAllowlistSummary;
  gray_window: WorkspaceGovernanceGrayWindow;
  request_note?: string;
}

export interface WorkspaceGovernanceStep {
  step_type: "operator_approval" | "receiver_allowlist" | "gray_window" | string;
  step_status: "pending" | "approved" | "rejected" | "expired" | string;
  actor_metadata?: Record<string, unknown>;
  created_at?: string;
  updated_at?: string;
}

export interface WorkspaceGovernanceResponse {
  ok: boolean;
  operation?: string;
  review_id?: string;
  draft_id?: string;
  review_status?: string;
  steps?: WorkspaceGovernanceStep[];
  allowlist_summary?: {
    hash?: string;
    count?: number;
    source_reference_summary?: Record<string, unknown>;
    expires_at?: string;
  };
  gray_window?: {
    start_at?: string;
    end_at?: string;
    timezone?: string;
    window_status?: string;
  };
  created_at?: string;
  updated_at?: string;
  expires_at?: string;
  preview_only?: boolean;
  production_write?: boolean;
  approved?: boolean;
  ready_for_review?: boolean;
  push_center_job_created?: boolean;
  external_effect_job_created?: boolean;
  broadcast_job_created?: boolean;
  internal_event_created?: boolean;
  real_external_call?: boolean;
  real_external_call_executed?: boolean;
  can_claim_pass_90_plus?: boolean;
  execution_status?: string;
  idempotent_replay?: boolean;
  error?: string;
  detail?: string;
}

export interface WorkspaceGovernanceListResponse {
  ok: boolean;
  items: WorkspaceGovernanceResponse[];
  total?: number;
  preview_only?: boolean;
  production_write?: boolean;
  real_external_call?: boolean;
  real_external_call_executed?: boolean;
  push_center_job_created?: boolean;
  external_effect_job_created?: boolean;
  broadcast_job_created?: boolean;
  internal_event_created?: boolean;
  can_claim_pass_90_plus?: boolean;
  execution_status?: string;
}

export interface BuildWorkspaceGovernancePayloadOptions {
  allowlistHash?: string;
  allowlistCount?: number;
  sourceReference?: Record<string, unknown>;
  grayWindow?: WorkspaceGovernanceGrayWindow;
  requestNote?: string;
}

export const DEFAULT_WORKSPACE_GOVERNANCE_API_CONFIG: WorkspaceGovernanceApiConfig = {
  ...DEFAULT_WORKSPACE_DRAFT_API_CONFIG,
  governanceUrl: "/api/admin/p1/group-ops-workspace/governance"
};

function text(value: unknown): string {
  return String(value ?? "").trim();
}

function bodyOptions(payload: unknown): WorkspaceDraftRequestOptions {
  return {
    method: "POST",
    body: JSON.stringify(payload)
  };
}

function defaultGrayWindow(snapshotHash: string): WorkspaceGovernanceGrayWindow {
  const dayOffset = Number.parseInt(workspaceSimpleHash(snapshotHash || "no_snapshot").slice(0, 2), 16) % 20;
  const day = String(1 + dayOffset).padStart(2, "0");
  return {
    start_at: `2026-06-${day}T09:00:00+08:00`,
    end_at: `2026-06-${day}T10:00:00+08:00`,
    timezone: "Asia/Shanghai"
  };
}

function stableGrayWindowHash(grayWindow: WorkspaceGovernanceGrayWindow): string {
  return workspaceSimpleHash(JSON.stringify({
    start_at: grayWindow.start_at,
    end_at: grayWindow.end_at,
    timezone: grayWindow.timezone
  }));
}

export function stableGovernanceIdempotencyKey(
  draftId: string,
  snapshotHash: string,
  allowlistHash: string,
  grayWindowHash: string
): string {
  return [
    "p1-gow-governance",
    text(draftId),
    text(snapshotHash || "no_snapshot"),
    text(allowlistHash || "allowlist_missing"),
    text(grayWindowHash || "window_missing")
  ].join(":");
}

export function assertWorkspaceGovernancePayloadSafe(payload: WorkspaceGovernanceRequestPayload): true {
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

export function buildWorkspaceGovernanceRequestPayload(
  draftId: string,
  snapshotHash: string,
  options: BuildWorkspaceGovernancePayloadOptions = {}
): WorkspaceGovernanceRequestPayload {
  const grayWindow = options.grayWindow || defaultGrayWindow(snapshotHash);
  const allowlistHash = options.allowlistHash || `allowlist-${workspaceSimpleHash(`${draftId}:${snapshotHash}:summary`)}`;
  const grayWindowHash = stableGrayWindowHash(grayWindow);
  const payload: WorkspaceGovernanceRequestPayload = {
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

export function assertGovernanceResponseSafe(value: WorkspaceGovernanceResponse | WorkspaceGovernanceListResponse): true {
  assertWorkspaceSensitiveSafe(value);
  const payload = value as WorkspaceGovernanceResponse;
  if (
    payload.approved === true
    || payload.push_center_job_created === true
    || payload.external_effect_job_created === true
    || payload.broadcast_job_created === true
    || payload.internal_event_created === true
    || payload.real_external_call === true
    || payload.real_external_call_executed === true
    || payload.can_claim_pass_90_plus === true
  ) {
    throw new Error("governance_api_response_violates_execution_guardrail");
  }
  if (
    payload.execution_status && payload.execution_status !== "not_execution"
    || payload.review_status === "sent"
    || payload.review_status === "completed"
    || payload.review_status === "approved"
  ) {
    throw new Error("governance_api_response_claims_execution_state");
  }
  const list = value as WorkspaceGovernanceListResponse;
  if (Array.isArray(list.items)) {
    list.items.forEach((item) => assertGovernanceResponseSafe(item));
  }
  return true;
}

function asGovernanceResponse(value: unknown): WorkspaceGovernanceResponse {
  const payload = value && typeof value === "object" ? value as WorkspaceGovernanceResponse : { ok: false };
  assertGovernanceResponseSafe(payload);
  return payload;
}

function asGovernanceListResponse(value: unknown): WorkspaceGovernanceListResponse {
  const payload = value && typeof value === "object" ? value as WorkspaceGovernanceListResponse : { ok: false, items: [] };
  if (!Array.isArray(payload.items)) {
    payload.items = [];
  }
  assertGovernanceResponseSafe(payload);
  return payload;
}

export function isGovernanceConflictError(error: unknown): boolean {
  const message = text(error instanceof Error ? error.message : error).toLowerCase();
  return message.includes("conflict") || message.includes("409") || message.includes("active governance review exists");
}

export async function requestGovernance(
  draftId: string,
  payload: WorkspaceGovernanceRequestPayload,
  config: WorkspaceGovernanceApiConfig = DEFAULT_WORKSPACE_GOVERNANCE_API_CONFIG,
  requestJson: WorkspaceDraftRequestJson = defaultWorkspaceDraftRequestJson()
): Promise<WorkspaceGovernanceResponse> {
  assertWorkspaceGovernancePayloadSafe(payload);
  return asGovernanceResponse(await requestJson(
    `${config.draftsUrl}/${encodeURIComponent(draftId)}/governance/request`,
    bodyOptions(payload)
  ));
}

export async function getGovernanceReview(
  reviewId: string,
  config: WorkspaceGovernanceApiConfig = DEFAULT_WORKSPACE_GOVERNANCE_API_CONFIG,
  requestJson: WorkspaceDraftRequestJson = defaultWorkspaceDraftRequestJson()
): Promise<WorkspaceGovernanceResponse> {
  return asGovernanceResponse(await requestJson(`${config.governanceUrl}/${encodeURIComponent(reviewId)}`));
}

export async function getDraftGovernance(
  draftId: string,
  config: WorkspaceGovernanceApiConfig = DEFAULT_WORKSPACE_GOVERNANCE_API_CONFIG,
  requestJson: WorkspaceDraftRequestJson = defaultWorkspaceDraftRequestJson()
): Promise<WorkspaceGovernanceListResponse> {
  return asGovernanceListResponse(await requestJson(`${config.draftsUrl}/${encodeURIComponent(draftId)}/governance`));
}
