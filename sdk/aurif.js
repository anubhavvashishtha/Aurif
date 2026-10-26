/**
 * Aurif site / agent SDK (MVP)
 * Permissioned AI browsing for the open web.
 *
 * Site usage:
 *   <script src="/sdk/aurif.js" data-aurif-site="my-site"></script>
 *
 * Agent usage (browser console or agent runtime):
 *   const session = await Aurif.handshake({ agent_id: "demo-agent", requested_scopes: ["view","act"] })
 *   const page = await Aurif.getPage("/")
 *   await Aurif.act("product.add:widget")
 */
(function (global) {
  "use strict";

  const PROTOCOL = "aurif-1";
  const scriptEl =
    typeof document !== "undefined"
      ? document.currentScript ||
        document.querySelector("script[data-aurif-site]")
      : null;

  const config = {
    siteId:
      (scriptEl && scriptEl.getAttribute("data-aurif-site")) || "default",
    baseUrl:
      (scriptEl && scriptEl.getAttribute("data-aurif-base")) ||
      (typeof location !== "undefined" ? location.origin : ""),
    protocol: PROTOCOL,
  };

  let sessionToken = null;
  let grantedScopes = [];

  function headers(extra) {
    const h = {
      "Content-Type": "application/json",
      "X-Aurif-Protocol": PROTOCOL,
      ...(extra || {}),
    };
    if (sessionToken) {
      h["X-Aurif-Session"] = sessionToken;
    }
    return h;
  }

  async function request(path, options) {
    const url = config.baseUrl.replace(/\/$/, "") + path;
    const res = await fetch(url, options);
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      const err = new Error(data.error || res.statusText || "Aurif request failed");
      err.status = res.status;
      err.data = data;
      throw err;
    }
    return data;
  }

  const Aurif = {
    version: "0.1.0",
    protocol: PROTOCOL,
    config,

    /** Discovery document */
    async discover() {
      return request("/.well-known/aurif.json", {
        method: "GET",
        headers: headers(),
      });
    },

    /**
     * Handshake: identify as an AI agent and receive a scoped session.
     * @param {{ agent_id: string, agent_version?: string, requested_scopes?: string[], purpose?: string }} opts
     */
    async handshake(opts) {
      const body = {
        agent_id: opts.agent_id || "anonymous-agent",
        agent_version: opts.agent_version || "0.0.0",
        requested_scopes: opts.requested_scopes || ["view"],
        purpose: opts.purpose || "",
      };
      if (opts.site_key) body.site_key = opts.site_key;
      const data = await request("/ai/handshake", {
        method: "POST",
        headers: headers({
          "X-Aurif-Agent": body.agent_id + "/" + body.agent_version,
          ...(opts.site_key ? { "X-Aurif-Site-Key": opts.site_key } : {}),
        }),
        body: JSON.stringify(body),
      });
      sessionToken = data.session_token;
      grantedScopes = data.granted_scopes || [];
      return data;
    },

    getSession() {
      return { sessionToken, grantedScopes: grantedScopes.slice() };
    },

    setSession(token, scopes) {
      sessionToken = token;
      grantedScopes = scopes || [];
    },

    /** Structured page snapshot for agents */
    async getPage(path) {
      const q = encodeURIComponent(path || "/");
      return request("/ai/page?path=" + q, {
        method: "GET",
        headers: headers(),
      });
    },

    /** Invoke a declared action by action_id */
    async act(actionId, args) {
      return request("/ai/actions", {
        method: "POST",
        headers: headers(),
        body: JSON.stringify({
          action_id: actionId,
          args: args || {},
        }),
      });
    },

    async audit() {
      return request("/ai/audit", {
        method: "GET",
        headers: headers(),
      });
    },

    /**
     * Collect local data-aurif-action hooks (for sites that annotate the DOM).
     * Does not replace the server AI surface; useful for progressive enhancement.
     */
    listLocalActions() {
      if (typeof document === "undefined") return [];
      return Array.from(document.querySelectorAll("[data-aurif-action]")).map(
        (el) => ({
          action_id: el.getAttribute("data-aurif-action"),
          type: el.tagName.toLowerCase(),
          label: (el.getAttribute("aria-label") || el.textContent || "")
            .trim()
            .slice(0, 120),
        })
      );
    },

    /** Mark document as Aurif-enabled for tooling */
    announce() {
      if (typeof document === "undefined") return;
      document.documentElement.setAttribute("data-aurif", "ready");
      document.documentElement.setAttribute("data-aurif-site", config.siteId);
      document.documentElement.setAttribute("data-aurif-protocol", PROTOCOL);
    },
  };

  Aurif.announce();
  global.Aurif = Aurif;
})(typeof window !== "undefined" ? window : globalThis);
