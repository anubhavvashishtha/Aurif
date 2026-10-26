(() => {
  "use strict";

  const state = {
    token: localStorage.getItem("aurif_owner_token") || "",
    user: null,
    sites: [],
    siteId: localStorage.getItem("aurif_site_id") || "",
    activity: [],
  };

  const $ = (id) => document.getElementById(id);

  async function api(path, options = {}) {
    const headers = {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    };
    if (state.token) headers["X-Aurif-Owner"] = state.token;
    const res = await fetch(path, { ...options, headers });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      const err = new Error(data.error || res.statusText);
      err.status = res.status;
      err.data = data;
      throw err;
    }
    return data;
  }

  function currentSite() {
    return state.sites.find((s) => s.id === state.siteId) || state.sites[0];
  }

  function showAuth() {
    $("view-auth").classList.remove("hidden");
    $("view-app").classList.add("hidden");
  }

  function showApp() {
    $("view-auth").classList.add("hidden");
    $("view-app").classList.remove("hidden");
    $("user-email").textContent = state.user?.email || "";
    renderSiteSelect();
    renderAll();
  }

  function renderSiteSelect() {
    const sel = $("site-select");
    sel.innerHTML = state.sites
      .map(
        (s) =>
          `<option value="${s.id}" ${s.id === state.siteId ? "selected" : ""}>${escapeHtml(
            s.name
          )}</option>`
      )
      .join("");
    if (!state.siteId && state.sites[0]) {
      state.siteId = state.sites[0].id;
      localStorage.setItem("aurif_site_id", state.siteId);
      sel.value = state.siteId;
    }
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function fmtTime(ts) {
    try {
      return new Date(ts * 1000).toLocaleString();
    } catch {
      return String(ts);
    }
  }

  function renderOverview() {
    const site = currentSite();
    if (!site) return;
    const events = state.activity;
    const agents = new Set(events.map((e) => e.agent_id).filter(Boolean));
    const pages = events.filter((e) => e.kind === "page").length;
    const actions = events.filter((e) => e.kind === "action").length;
    const blocked = events.filter((e) =>
      String(e.kind).includes("blocked")
    ).length;
    const openEndpoints = (site.endpoints || []).filter((e) => e.agent_access)
      .length;

    $("stats").innerHTML = `
      <div class="stat"><div class="n">${agents.size}</div><div class="l">Agents seen</div></div>
      <div class="stat"><div class="n">${pages}</div><div class="l">Page reads</div></div>
      <div class="stat"><div class="n">${actions}</div><div class="l">Button/actions</div></div>
      <div class="stat"><div class="n">${blocked}</div><div class="l">Blocked attempts</div></div>
      <div class="stat"><div class="n">${openEndpoints}/${(site.endpoints || []).length}</div><div class="l">Endpoints open</div></div>
    `;
    $("overview-meta").textContent = `${site.name} · ${site.url} · key ${site.site_key.slice(
      0,
      8
    )}…`;
  }

  function renderActivity() {
    const body = $("activity-body");
    if (!state.activity.length) {
      body.innerHTML =
        '<tr><td colspan="4" class="mono">No agent activity yet. Run the agent demo.</td></tr>';
      return;
    }
    body.innerHTML = state.activity
      .map((e) => {
        const target =
          e.path ||
          e.action_id ||
          (e.detail && e.detail.purpose) ||
          "—";
        const kindClass = String(e.kind).includes("blocked") ? "off" : "";
        return `<tr>
          <td class="mono">${escapeHtml(fmtTime(e.ts))}</td>
          <td class="mono">${escapeHtml(e.agent_id || "—")}</td>
          <td><span class="badge ${kindClass}">${escapeHtml(e.kind)}</span></td>
          <td class="mono">${escapeHtml(String(target))}</td>
        </tr>`;
      })
      .join("");
  }

  function renderEndpoints() {
    const site = currentSite();
    if (!site) return;
    const list = $("endpoint-list");
    list.innerHTML = (site.endpoints || [])
      .map((ep) => {
        const meta =
          ep.kind === "page"
            ? `page ${ep.path}`
            : `action ${ep.action_id}`;
        return `<div class="endpoint-row">
          <div>
            <strong>${escapeHtml(ep.label)}</strong>
            <div class="mono">${escapeHtml(meta)}</div>
          </div>
          <label class="switch" title="Agent access">
            <input type="checkbox" data-endpoint="${escapeHtml(ep.id)}" ${
          ep.agent_access ? "checked" : ""
        } />
            <span></span>
          </label>
        </div>`;
      })
      .join("");

    list.querySelectorAll("input[data-endpoint]").forEach((input) => {
      input.addEventListener("change", async () => {
        const endpointId = input.getAttribute("data-endpoint");
        try {
          const data = await api(
            `/api/sites/${site.id}/endpoints/${encodeURIComponent(endpointId)}`,
            {
              method: "PUT",
              body: JSON.stringify({ agent_access: input.checked }),
            }
          );
          replaceSite(data.site);
          renderOverview();
        } catch (err) {
          input.checked = !input.checked;
          alert(err.message);
        }
      });
    });
  }

  function renderSettings() {
    const site = currentSite();
    if (!site) return;
    $("set-name").value = site.name || "";
    $("set-url").value = site.url || "";
    $("set-welcome").value = site.agent_welcome || "";
    $("set-blocked").value = (site.blocked_agents || []).join(", ");
    $("set-key").textContent = site.site_key;
  }

  function replaceSite(site) {
    state.sites = state.sites.map((s) => (s.id === site.id ? site : s));
    renderEndpoints();
    renderSettings();
    renderOverview();
  }

  async function loadActivity() {
    const site = currentSite();
    if (!site) return;
    const data = await api(`/api/sites/${site.id}/activity`);
    state.activity = data.events || [];
    renderActivity();
    renderOverview();
  }

  function renderAll() {
    renderOverview();
    renderEndpoints();
    renderSettings();
    loadActivity().catch(() => {});
  }

  async function bootstrap() {
    if (!state.token) {
      showAuth();
      return;
    }
    try {
      const data = await api("/api/auth/me");
      state.user = data.user;
      state.sites = data.sites || [];
      if (!state.sites.find((s) => s.id === state.siteId) && state.sites[0]) {
        state.siteId = state.sites[0].id;
        localStorage.setItem("aurif_site_id", state.siteId);
      }
      showApp();
    } catch {
      state.token = "";
      localStorage.removeItem("aurif_owner_token");
      showAuth();
    }
  }

  // Auth tabs
  $("tab-login").onclick = () => {
    $("form-login").classList.remove("hidden");
    $("form-signup").classList.add("hidden");
    $("tab-login").className = "btn";
    $("tab-signup").className = "btn btn-ghost";
  };
  $("tab-signup").onclick = () => {
    $("form-signup").classList.remove("hidden");
    $("form-login").classList.add("hidden");
    $("tab-signup").className = "btn";
    $("tab-login").className = "btn btn-ghost";
  };

  $("form-login").onsubmit = async (e) => {
    e.preventDefault();
    $("login-error").classList.add("hidden");
    try {
      const data = await api("/api/auth/login", {
        method: "POST",
        body: JSON.stringify({
          email: $("login-email").value,
          password: $("login-password").value,
        }),
      });
      state.token = data.token;
      localStorage.setItem("aurif_owner_token", data.token);
      await bootstrap();
    } catch (err) {
      $("login-error").textContent = err.message;
      $("login-error").classList.remove("hidden");
    }
  };

  $("form-signup").onsubmit = async (e) => {
    e.preventDefault();
    $("signup-error").classList.add("hidden");
    try {
      const data = await api("/api/auth/signup", {
        method: "POST",
        body: JSON.stringify({
          name: $("signup-name").value,
          email: $("signup-email").value,
          password: $("signup-password").value,
        }),
      });
      state.token = data.token;
      localStorage.setItem("aurif_owner_token", data.token);
      // New owners start with no sites — create a default one
      await api("/api/sites", {
        method: "POST",
        body: JSON.stringify({
          name: "My website",
          url: location.origin,
        }),
      });
      await bootstrap();
    } catch (err) {
      $("signup-error").textContent = err.message;
      $("signup-error").classList.remove("hidden");
    }
  };

  $("btn-logout").onclick = async () => {
    try {
      await api("/api/auth/logout", { method: "POST" });
    } catch {
      /* ignore */
    }
    state.token = "";
    localStorage.removeItem("aurif_owner_token");
    showAuth();
  };

  $("site-select").onchange = () => {
    state.siteId = $("site-select").value;
    localStorage.setItem("aurif_site_id", state.siteId);
    renderAll();
  };

  document.querySelectorAll(".side button[data-tab]").forEach((btn) => {
    btn.onclick = () => {
      document
        .querySelectorAll(".side button")
        .forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      document
        .querySelectorAll(".tab")
        .forEach((t) => t.classList.add("hidden"));
      $("tab-" + btn.getAttribute("data-tab")).classList.remove("hidden");
    };
  });

  $("btn-refresh-activity").onclick = () => loadActivity();

  $("form-settings").onsubmit = async (e) => {
    e.preventDefault();
    const site = currentSite();
    if (!site) return;
    const msg = $("settings-msg");
    msg.classList.add("hidden");
    try {
      const blocked = $("set-blocked")
        .value.split(",")
        .map((s) => s.trim())
        .filter(Boolean);
      const data = await api(`/api/sites/${site.id}`, {
        method: "PATCH",
        body: JSON.stringify({
          name: $("set-name").value,
          url: $("set-url").value,
          agent_welcome: $("set-welcome").value,
          blocked_agents: blocked,
        }),
      });
      replaceSite(data.site);
      msg.textContent = "Saved. Agents will see the new welcome on next page read.";
      msg.style.color = "var(--accent-ink)";
      msg.classList.remove("hidden");
    } catch (err) {
      msg.textContent = err.message;
      msg.style.color = "var(--danger)";
      msg.classList.remove("hidden");
    }
  };

  $("btn-rotate-key").onclick = async () => {
    const site = currentSite();
    if (!site) return;
    if (!confirm("Rotate site key? Agents sending the old key will be rejected.")) {
      return;
    }
    const data = await api(`/api/sites/${site.id}`, {
      method: "PATCH",
      body: JSON.stringify({ rotate_site_key: true }),
    });
    replaceSite(data.site);
  };

  bootstrap();
})();
