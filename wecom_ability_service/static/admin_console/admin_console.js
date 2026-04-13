function updateShellStatus(payload) {
  if (!payload || !payload.shell_status) {
    return;
  }

  const shellStatus = payload.shell_status;
  const envNode = document.querySelector("[data-shell-env]");
  const releaseNode = document.querySelector("[data-shell-release]");
  const healthNode = document.querySelector("[data-shell-health]");
  const healthDetailNode = document.querySelector("[data-shell-health-detail]");

  if (envNode && shellStatus.environment) {
    envNode.textContent = shellStatus.environment.label || "UNKNOWN";
    envNode.className = `admin-chip admin-chip--${shellStatus.environment.tone || "unknown"}`;
  }
  if (releaseNode) {
    releaseNode.textContent = `当前版本 ${shellStatus.release_sha || "local"}`;
  }
  if (healthNode && shellStatus.health) {
    healthNode.textContent = shellStatus.health.label || "UNKNOWN";
    healthNode.className = `admin-chip admin-chip--${shellStatus.health.state || "unknown"}`;
  }
  if (healthDetailNode && shellStatus.health) {
    healthDetailNode.textContent = shellStatus.health.detail || "status unavailable";
  }
}

function bootShellStatusPolling() {
  const root = document.body;
  const contextUrl = root.getAttribute("data-shell-context-url");
  if (!contextUrl) {
    return;
  }

  const refresh = () => {
    fetch(contextUrl, { headers: { Accept: "application/json" } })
      .then((response) => response.ok ? response.json() : null)
      .then((payload) => updateShellStatus(payload))
      .catch(() => {});
  };

  refresh();
  window.setInterval(refresh, 60000);
}

function bootLegacyFrames() {
  document.querySelectorAll("[data-legacy-shell]").forEach((shell) => {
    const frame = shell.querySelector("[data-legacy-frame]");
    const state = shell.querySelector("[data-legacy-state]");
    if (!frame || !state) {
      return;
    }

    let loaded = false;
    const ready = () => {
      if (loaded) {
        return;
      }
      loaded = true;
      shell.querySelector(".admin-legacy-frame-wrap")?.classList.add("is-ready");
    };

    frame.addEventListener("load", ready, { once: true });
    window.setTimeout(() => {
    if (loaded) {
      return;
    }
    state.classList.remove("admin-state--loading");
    state.classList.add("admin-state--error");
    state.innerHTML = [
        "<strong>页面加载超时</strong>",
        "<span>当前页面没有按预期完成加载，请稍后重试。</span>",
    ].join("");
  }, 15000);
  });
}

function bootOutputModal() {
  const backdrop = document.querySelector("[data-output-modal-backdrop]");
  if (!backdrop) {
    return;
  }

  const closeUrl = backdrop.getAttribute("data-close-url") || "";
  const closeModal = () => {
    if (!closeUrl) {
      return;
    }
    window.location.href = closeUrl;
  };

  backdrop.addEventListener("click", (event) => {
    if (event.target === backdrop) {
      closeModal();
    }
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      closeModal();
    }
  });

  backdrop.querySelectorAll("[data-output-modal-close]").forEach((node) => {
    node.addEventListener("click", (event) => {
      if (!closeUrl) {
        return;
      }
      event.preventDefault();
      closeModal();
    });
  });
}

function bootCopyButtons() {
  document.querySelectorAll("[data-copy-text]").forEach((button) => {
    button.addEventListener("click", async () => {
      const text = button.getAttribute("data-copy-text") || "";
      const defaultLabel = button.getAttribute("data-copy-label-default") || button.textContent || "复制";
      const successLabel = button.getAttribute("data-copy-label-success") || "已复制";
      const errorLabel = button.getAttribute("data-copy-label-error") || "复制失败";
      try {
        await navigator.clipboard.writeText(text);
        button.textContent = successLabel;
      } catch (error) {
        button.textContent = errorLabel;
      }
      window.setTimeout(() => {
        button.textContent = defaultLabel;
      }, 1500);
    });
  });
}

document.addEventListener("DOMContentLoaded", () => {
  bootShellStatusPolling();
  bootLegacyFrames();
  bootOutputModal();
  bootCopyButtons();
});
