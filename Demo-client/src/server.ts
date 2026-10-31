import "./lib/error-capture";

import { consumeLastCapturedError } from "./lib/error-capture";
import { renderErrorPage } from "./lib/error-page";

type ServerEntry = {
  fetch: (request: Request, env: unknown, ctx: unknown) => Promise<Response> | Response;
};

let serverEntryPromise: Promise<ServerEntry> | undefined;

const API_BASE =
  process.env.AURIF_API_URL || process.env.VITE_AURIF_API || "http://127.0.0.1:8787";

const BOT_UA_HINTS = [
  "curl/",
  "wget/",
  "python-requests",
  "python-urllib",
  "httpx",
  "aiohttp",
  "scrapy",
  "go-http-client",
  "headlesschrome",
  "headless",
  "playwright",
  "puppeteer",
  "selenium",
  "gptbot",
  "chatgpt",
  "claudebot",
  "anthropic",
  "openai",
  "bytespider",
  "ccbot",
  "perplexitybot",
  "node-fetch",
  "undici",
];

function looksLikeAnonymousAgent(request: Request): boolean {
  if (request.headers.get("x-demo-as-agent") === "1") return true;
  if (request.headers.get("x-aurif-agent") && !request.headers.get("x-aurif-session")) {
    return true;
  }
  const ua = (request.headers.get("user-agent") || "").toLowerCase();
  if (!ua) return true;
  return BOT_UA_HINTS.some((h) => ua.includes(h));
}

function agentBlockedPage(siteName: string): Response {
  const html = `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>AI access blocked — ${siteName}</title>
  <style>
    body { font-family: ui-sans-serif, system-ui, sans-serif; background:#fafaf9; color:#1c1917;
      display:grid; place-items:center; min-height:100vh; margin:0; padding:2rem; }
    main { max-width:34rem; }
    h1 { font-size:1.75rem; margin:0 0 .75rem; }
    p { color:#57534e; line-height:1.5; }
    code { font-family: ui-monospace, monospace; font-size:.85rem; background:#e7e5e4; padding:.1rem .35rem; border-radius:.25rem; }
    ol { color:#57534e; line-height:1.6; }
  </style>
</head>
<body>
  <main>
    <h1>Automated agents are blocked here</h1>
    <p>
      <strong>${siteName}</strong> does not allow anonymous AI scrapers on the human storefront.
      Identify through Aurif, then use the machine endpoints.
    </p>
    <ol>
      <li><code>GET ${API_BASE}/.well-known/aurif.json</code></li>
      <li><code>POST ${API_BASE}/ai/handshake</code></li>
      <li><code>GET ${API_BASE}/ai/page</code> / <code>POST ${API_BASE}/ai/actions</code></li>
    </ol>
    <p>Humans can keep shopping in a normal browser. This page is for bots and agent runtimes only.</p>
  </main>
</body>
</html>`;
  return new Response(html, {
    status: 403,
    headers: {
      "content-type": "text/html; charset=utf-8",
      "x-aurif-gate": "anonymous_agent_blocked",
    },
  });
}

async function shouldBlockAnonymousAgents(): Promise<boolean> {
  try {
    const res = await fetch(`${API_BASE}/api/public/gate`, {
      headers: { Accept: "application/json" },
    });
    if (!res.ok) return true;
    const data = (await res.json()) as { block_anonymous_agents?: boolean };
    return data.block_anonymous_agents !== false;
  } catch {
    // Fail closed for agent-like traffic if the API is unreachable.
    return true;
  }
}

async function getServerEntry(): Promise<ServerEntry> {
  if (!serverEntryPromise) {
    serverEntryPromise = import("@tanstack/react-start/server-entry").then(
      (m) => (m.default ?? m) as ServerEntry,
    );
  }
  return serverEntryPromise;
}

async function normalizeCatastrophicSsrResponse(response: Response): Promise<Response> {
  if (response.status < 500) return response;
  const contentType = response.headers.get("content-type") ?? "";
  if (!contentType.includes("application/json")) return response;

  const body = await response.clone().text();
  if (!isH3SwallowedErrorBody(body)) return response;

  console.error(consumeLastCapturedError() ?? new Error(`h3 swallowed SSR error: ${body}`));
  return new Response(renderErrorPage(), {
    status: 500,
    headers: { "content-type": "text/html; charset=utf-8" },
  });
}

function isH3SwallowedErrorBody(body: string): boolean {
  try {
    const payload = JSON.parse(body) as { unhandled?: unknown; message?: unknown };
    return payload.unhandled === true && payload.message === "HTTPError";
  } catch {
    return false;
  }
}

export default {
  async fetch(request: Request, env: unknown, ctx: unknown) {
    try {
      const url = new URL(request.url);
      // Let Vite/assets through; gate document navigations and data-ish paths.
      const isAsset =
        url.pathname.startsWith("/@") ||
        url.pathname.startsWith("/src/") ||
        url.pathname.startsWith("/node_modules/") ||
        url.pathname.startsWith("/assets/") ||
        /\.(js|css|map|ico|png|jpg|jpeg|svg|webp|woff2?)$/i.test(url.pathname);

      if (!isAsset && looksLikeAnonymousAgent(request)) {
        // Valid Aurif agent session may pass (rare on human site; mainly for demos).
        if (!request.headers.get("x-aurif-session") && (await shouldBlockAnonymousAgents())) {
          let siteName = "Northline Goods";
          try {
            const gate = await fetch(`${API_BASE}/api/public/gate`).then((r) => r.json()) as {
              site_name?: string;
            };
            siteName = gate.site_name || siteName;
          } catch {
            /* keep default */
          }
          return agentBlockedPage(siteName);
        }
      }

      const handler = await getServerEntry();
      const response = await handler.fetch(request, env, ctx);
      return await normalizeCatastrophicSsrResponse(response);
    } catch (error) {
      console.error(error);
      return new Response(renderErrorPage(), {
        status: 500,
        headers: { "content-type": "text/html; charset=utf-8" },
      });
    }
  },
};
