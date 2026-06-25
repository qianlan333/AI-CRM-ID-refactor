(function () {
  const STYLE_ID = "user-ops-batch-send-modal-style";
  const MODAL_ID = "batch-send-modal-backdrop";
  const DEFAULT_PREVIEW_URL = "/api/admin/user-ops/batch-send/preview";
  const DEFAULT_EXECUTE_URL = "/api/admin/user-ops/batch-send/execute";

  let state = {
    targetSource: "",
    targetSourceId: null,
    targetLabel: "",
    previewUrl: DEFAULT_PREVIEW_URL,
    executeUrl: DEFAULT_EXECUTE_URL,
    operator: "admin"
  };

  function ensureStyle() {
    if (document.getElementById(STYLE_ID)) return;
    const style = document.createElement("style");
    style.id = STYLE_ID;
    style.textContent = `
      .uops-batch-backdrop {
        display: none;
        position: fixed;
        inset: 0;
        z-index: 70;
        align-items: center;
        justify-content: center;
        padding: 24px;
        background: rgba(16, 24, 40, .45);
      }
      .uops-batch-backdrop.show { display: flex; }
      .uops-batch-modal {
        width: min(760px, 96vw);
        max-height: min(820px, 92vh);
        overflow: auto;
        border: 1px solid #e7ebf2;
        border-radius: 18px;
        background: #fff;
        box-shadow: 0 24px 80px rgba(16, 24, 40, .28);
      }
      .uops-batch-head,
      .uops-batch-actions {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 12px;
        padding: 18px 22px;
        border-bottom: 1px solid #e7ebf2;
      }
      .uops-batch-actions {
        justify-content: flex-end;
        border-top: 1px solid #eef2f7;
        border-bottom: 0;
        padding: 16px 22px;
      }
      .uops-batch-head h3 { margin: 0; font-size: 18px; font-weight: 850; }
      .uops-batch-body { padding: 20px 22px; }
      .uops-batch-field { display: grid; gap: 7px; margin-bottom: 14px; }
      .uops-batch-field label { color: #667085; font-size: 13px; font-weight: 800; }
      .uops-batch-textarea {
        width: 100%;
        min-height: 104px;
        border: 1px solid #d0d5dd;
        border-radius: 10px;
        background: #fff;
        color: #1d2939;
        font: inherit;
        outline: none;
        padding: 10px 12px;
        resize: vertical;
      }
      .uops-batch-codebox {
        padding: 11px 12px;
        border: 1px solid #d0d5dd;
        border-radius: 10px;
        background: #f8fafc;
        color: #344054;
        overflow-wrap: anywhere;
      }
      .uops-batch-note {
        padding: 10px 12px;
        border: 1px solid #fedf89;
        border-radius: 12px;
        margin-top: 10px;
        background: #fffaeb;
        color: #93370d;
        font-size: 13px;
      }
      .uops-batch-status {
        min-height: 20px;
        margin: 0 0 12px;
        color: #667085;
        font-size: 13px;
        font-weight: 700;
      }
      .uops-batch-status.success { color: #067647; }
      .uops-batch-status.error { color: #d92d20; }
      .uops-batch-btn {
        min-height: 36px;
        border: 1px solid #d0d5dd;
        border-radius: 10px;
        background: #fff;
        color: #344054;
        cursor: pointer;
        font: inherit;
        font-weight: 800;
        padding: 8px 12px;
      }
      .uops-batch-btn.primary {
        border-color: #2563eb;
        background: #2563eb;
        color: #fff;
      }
      .uops-batch-btn.ghost { background: #f9fafb; }
      .uops-batch-badge {
        display: inline-flex;
        align-items: center;
        margin-left: 6px;
        padding: 5px 9px;
        border: 1px solid #dbeafe;
        border-radius: 999px;
        background: #eff6ff;
        color: #1849a9;
        font-size: 12px;
        font-weight: 900;
      }
      .uops-batch-preview {
        margin-top: 12px;
        border: 1px solid #eef2f7;
        border-radius: 12px;
        overflow: hidden;
      }
      .uops-batch-preview-head {
        display: flex;
        justify-content: space-between;
        gap: 12px;
        padding: 12px;
        background: #fafbfc;
        color: #344054;
        font-weight: 800;
      }
      .uops-batch-preview-list {
        max-height: 220px;
        overflow: auto;
      }
      .uops-batch-preview-row {
        display: grid;
        grid-template-columns: minmax(110px, .8fr) minmax(110px, .8fr) minmax(180px, 1fr);
        gap: 10px;
        padding: 10px 12px;
        border-top: 1px solid #eef2f7;
        color: #344054;
        font-size: 13px;
      }
      .uops-batch-mono {
        font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
        font-size: 12px;
        overflow-wrap: anywhere;
      }
      .uops-batch-empty { padding: 16px; color: #667085; text-align: center; }
      .uops-batch-checkbox {
        display: inline-flex;
        align-items: center;
        gap: 8px;
        color: #475467;
        font-weight: 750;
      }
      @media (max-width: 720px) {
        .uops-batch-preview-row { grid-template-columns: 1fr; }
        .uops-batch-head { align-items: flex-start; }
      }
    `;
    document.head.appendChild(style);
  }

  function escapeHtml(value) {
    return String(value || "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll("\"", "&quot;")
      .replaceAll("'", "&#039;");
  }

  function ensureModal() {
    let backdrop = document.getElementById(MODAL_ID);
    if (backdrop) return backdrop;
    ensureStyle();
    backdrop = document.createElement("div");
    backdrop.id = MODAL_ID;
    backdrop.className = "uops-batch-backdrop";
    backdrop.innerHTML = `
      <section class="uops-batch-modal" role="dialog" aria-modal="true" aria-labelledby="batch-send-title">
        <div class="uops-batch-head">
          <h3 id="batch-send-title">标准私信群发组件 <span class="uops-batch-badge">复用 User Ops Batch Send</span></h3>
          <button id="close-batch-send-btn" class="uops-batch-btn ghost" type="button">关闭</button>
        </div>
        <div class="uops-batch-body">
          <p id="batch-send-status" class="uops-batch-status">先填写内容，再做发送预览。</p>
          <div class="uops-batch-field">
            <label>目标来源</label>
            <div id="batch-target-label" class="uops-batch-codebox">AI 人群包</div>
          </div>
          <div class="uops-batch-field">
            <label for="batch-send-text">群发内容</label>
            <textarea id="batch-send-text" class="uops-batch-textarea" placeholder="填写要发送的私信内容"></textarea>
          </div>
          <label class="uops-batch-checkbox">
            <input id="include-dnd-toggle" type="checkbox">
            <span>包含免打扰用户</span>
          </label>
          <label id="include-dnd-confirm-line" class="uops-batch-checkbox" style="display:none;margin-left:18px">
            <input id="include-dnd-confirm-toggle" type="checkbox">
            <span>我确认本次群发包含免打扰用户</span>
          </label>
          <div class="uops-batch-note">此浮窗复用 /api/admin/user-ops/batch-send/preview 和 /execute，并透传 target_source=ai_audience_package。</div>
          <div class="uops-batch-preview" aria-label="发送预览">
            <div class="uops-batch-preview-head">
              <span>最终可发送名单</span>
              <span>可发人数 <strong id="preview-eligible-count">0</strong></span>
            </div>
            <div id="preview-target-body" class="uops-batch-preview-list">
              <div class="uops-batch-empty">还没有预览结果</div>
            </div>
          </div>
        </div>
        <div class="uops-batch-actions">
          <button id="preview-batch-send-btn" class="uops-batch-btn" type="button">预览发送人数</button>
          <button id="execute-batch-send-btn" class="uops-batch-btn primary" type="button">确认创建群发任务</button>
        </div>
      </section>
    `;
    document.body.appendChild(backdrop);
    document.getElementById("close-batch-send-btn").addEventListener("click", close);
    document.getElementById("preview-batch-send-btn").addEventListener("click", () => {
      preview().catch((error) => setStatus(error.message || "预览失败", "error"));
    });
    document.getElementById("execute-batch-send-btn").addEventListener("click", () => {
      execute().catch((error) => setStatus(error.message || "群发失败", "error"));
    });
    document.getElementById("include-dnd-toggle").addEventListener("change", (event) => {
      document.getElementById("include-dnd-confirm-line").style.display = event.target.checked ? "inline-flex" : "none";
      if (!event.target.checked) {
        document.getElementById("include-dnd-confirm-toggle").checked = false;
      }
    });
    return backdrop;
  }

  function setStatus(text, tone) {
    const el = document.getElementById("batch-send-status");
    if (!el) return;
    el.textContent = text;
    el.className = tone ? `uops-batch-status ${tone}` : "uops-batch-status";
  }

  async function postJson(url, payload) {
    const response = await fetch(url, {
      method: "POST",
      credentials: "same-origin",
      cache: "no-store",
      headers: { "Accept": "application/json", "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok || data.ok === false) {
      throw new Error(data.error || data.detail || `HTTP ${response.status}`);
    }
    return data;
  }

  function buildRequest(confirm) {
    const content = document.getElementById("batch-send-text").value.trim();
    const includeDnd = document.getElementById("include-dnd-toggle").checked;
    if (!content) {
      throw new Error("请先填写群发内容");
    }
    if (confirm && includeDnd && !document.getElementById("include-dnd-confirm-toggle").checked) {
      throw new Error("包含免打扰用户时，需要再次确认");
    }
    return {
      target_source: state.targetSource,
      target_source_id: state.targetSourceId,
      selection_mode: "all_filtered",
      filters: {},
      selected_ids: [],
      excluded_ids: [],
      content,
      images: [],
      attachments: [],
      include_do_not_disturb: includeDnd,
      confirm: Boolean(confirm),
      operator: state.operator || "admin"
    };
  }

  function renderPreview(payload) {
    const eligibleCount = payload.eligible_count || 0;
    const targets = payload.final_targets || [];
    document.getElementById("preview-eligible-count").textContent = String(eligibleCount);
    document.getElementById("preview-target-body").innerHTML = targets.length
      ? targets.slice(0, 50).map((item) => `
        <div class="uops-batch-preview-row">
          <div>${escapeHtml(item.customer_name || "-")}</div>
          <div>${escapeHtml(item.owner_display_name || item.owner_userid || "-")}</div>
          <div class="uops-batch-mono">${escapeHtml(item.external_userid || "-")}</div>
        </div>
      `).join("")
      : '<div class="uops-batch-empty">当前预览没有可发送目标</div>';
  }

  async function preview() {
    setStatus("预览计算中...");
    const payload = await postJson(state.previewUrl, buildRequest(false));
    renderPreview(payload);
    setStatus("预览已更新", "success");
  }

  async function execute() {
    setStatus("群发执行中...");
    const payload = await postJson(state.executeUrl, buildRequest(true));
    setStatus(`群发任务已创建，记录 #${payload.record_id || "-"}`, "success");
  }

  function open(options) {
    state = {
      targetSource: options.targetSource || "",
      targetSourceId: options.targetSourceId,
      targetLabel: options.targetLabel || "AI 人群包",
      previewUrl: options.previewUrl || DEFAULT_PREVIEW_URL,
      executeUrl: options.executeUrl || DEFAULT_EXECUTE_URL,
      operator: options.operator || "admin"
    };
    const backdrop = ensureModal();
    document.getElementById("batch-target-label").textContent = state.targetLabel;
    document.getElementById("batch-send-text").value = "";
    document.getElementById("include-dnd-toggle").checked = false;
    document.getElementById("include-dnd-confirm-toggle").checked = false;
    document.getElementById("include-dnd-confirm-line").style.display = "none";
    document.getElementById("preview-eligible-count").textContent = "0";
    document.getElementById("preview-target-body").innerHTML = '<div class="uops-batch-empty">还没有预览结果</div>';
    setStatus("先填写内容，再做发送预览。");
    backdrop.classList.add("show");
  }

  function close() {
    const backdrop = document.getElementById(MODAL_ID);
    if (backdrop) backdrop.classList.remove("show");
  }

  window.UserOpsBatchSendModal = { open, close };
})();
