// Cloudflare Worker: receives a seed keyword from the SEO suite dashboard
// and triggers the GitHub Actions keyword-research workflow.
//
// Required secrets (set in Cloudflare dashboard → Workers & Pages → your worker → Settings → Variables):
//   GITHUB_TOKEN   - fine-grained PAT with Actions:write on the repo
//   RESEARCH_KEY   - shared secret; must match the KR_WORKER_KEY used at build time
//   GITHUB_OWNER   - e.g. Milton-Talukdar
//   GITHUB_REPO    - e.g. seo_tools
//
// Optional environment variable:
//   DASHBOARD_ORIGIN - e.g. https://milton-talukdar.github.io (for CORS)

const WORKFLOW_FILE = "keyword-research.yml";

function json(body, status = 200, extra = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      "Content-Type": "application/json",
      ...extra,
    },
  });
}

function corsHeaders(origin) {
  const allow = origin || "*";
  return {
    "Access-Control-Allow-Origin": allow,
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, X-Research-Key",
  };
}

export default {
  async fetch(request, env) {
    const origin = env.DASHBOARD_ORIGIN || request.headers.get("Origin") || "*";
    const cors = corsHeaders(origin);

    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: cors });
    }

    if (request.method !== "POST") {
      return json({ ok: false, error: "Method not allowed" }, 405, cors);
    }

    // Validate shared key (not bulletproof because it's in the HTML, but stops casual abuse)
    const key = request.headers.get("X-Research-Key") || "";
    if (!env.RESEARCH_KEY || key !== env.RESEARCH_KEY) {
      return json({ ok: false, error: "Unauthorized" }, 401, cors);
    }

    let body;
    try {
      body = await request.json();
    } catch (e) {
      return json({ ok: false, error: "Invalid JSON" }, 400, cors);
    }

    const seed = String(body.seed || "").trim();
    const limit = String(body.limit || "100").trim();
    if (!seed) {
      return json({ ok: false, error: "seed is required" }, 400, cors);
    }

    const owner = env.GITHUB_OWNER;
    const repo = env.GITHUB_REPO;
    const token = env.GITHUB_TOKEN;
    const missing = [
      !owner && "GITHUB_OWNER",
      !repo && "GITHUB_REPO",
      !token && "GITHUB_TOKEN",
    ].filter(Boolean);
    if (missing.length) {
      return json({ ok: false, error: `Worker not configured: ${missing.join(", ")}` }, 500, cors);
    }

    const url = `https://api.github.com/repos/${owner}/${repo}/actions/workflows/${WORKFLOW_FILE}/dispatches`;
    try {
      const gh = await fetch(url, {
        method: "POST",
        headers: {
          Accept: "application/vnd.github+json",
          Authorization: `Bearer ${token}`,
          "X-GitHub-Api-Version": "2022-11-28",
          "Content-Type": "application/json",
          "User-Agent": "seo-suite-research-worker",
        },
        body: JSON.stringify({
          ref: "main",
          inputs: { seed, limit },
        }),
      });

      if (!gh.ok) {
        const text = await gh.text();
        return json({ ok: false, error: `GitHub ${gh.status}: ${text}` }, 502, cors);
      }

      return json({ ok: true, message: "Keyword research started" }, 200, cors);
    } catch (e) {
      return json({ ok: false, error: e.message }, 500, cors);
    }
  },
};
