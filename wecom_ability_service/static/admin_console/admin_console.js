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
    releaseNode.textContent = `release ${shellStatus.release_sha || "local"}`;
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
        "<strong>legacy 页面载入超时</strong>",
        "<span>壳层已经就绪，但内部 legacy 页面没有按预期完成加载。</span>",
      ].join("");
    }, 15000);
  });
}

document.addEventListener("DOMContentLoaded", () => {
  bootShellStatusPolling();
  bootLegacyFrames();
});
